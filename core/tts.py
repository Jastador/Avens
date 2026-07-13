import os
import time
import sounddevice as sd
import numpy as np
import torch
from kokoro import KPipeline
from config import BASE_PATH
from core.performance import performance
from core.tts_segments import ResumableSpeechPlan

def _read_positive_int_env(
    name: str,
    default: int,
) -> int:
    """Read one positive integer setting safely."""
    try:
        return max(
            1,
            int(os.getenv(name, str(default)).strip()),
        )
    except (TypeError, ValueError):
        return default


TTS_CPU_THREADS = _read_positive_int_env(
    "AVENS_TTS_CPU_THREADS",
    4,
)

try:
    torch.set_num_threads(TTS_CPU_THREADS)
    print(f"🧵 Kokoro CPU threads: {TTS_CPU_THREADS}")
except RuntimeError as error:
    print(f"⚠️ Could not set Kokoro CPU threads: {error}")

# Initialize the pipeline globally
print("🧠 Initializing Kokoro TTS Engine...")
try:
    pipeline = KPipeline(
    lang_code="a",
    repo_id="hexgrad/Kokoro-82M",
    device="cpu"
)
    # 🔥 The 100% Offline Bypass: Load the file directly from your hard drive
    voice_path = os.path.join(BASE_PATH, "voices", "am_adam.pt")
    voicepack = torch.load(voice_path, weights_only=True)
    print("✅ Success: Kokoro TTS Engine Online.")
except Exception as e:
    print(f"❌ CRITICAL: Kokoro TTS failed to load. {e}")
    pipeline = None
    voicepack = None

def speak(
    text,
    shared_state=None,
    performance_label: str | None = None,
):
    clean_text = str(text).replace('"', "").strip()
    speech_plan = ResumableSpeechPlan.from_text(clean_text)

    safe_label = "_".join(
        str(performance_label or "").casefold().split()
    )
    safe_label = "".join(
        character
        for character in safe_label
        if character.isalnum() or character == "_"
    )

    stage_prefix = (
        f"tts_{safe_label}"
        if safe_label
        else "tts"
    )
    span_name = (
        f"tts_speak:{safe_label}"
        if safe_label
        else "tts_speak"
    )

    trace_id = performance.current_trace_id()
    owns_trace = trace_id is None

    if owns_trace:
        trace_id = performance.begin(
            "tts_speak",
            metadata={
                "backend": "kokoro",
                "text_characters": len(clean_text),
                "label": safe_label or "general",
                "segment_count": len(speech_plan.segments),
            },
        )

    span_id = performance.begin_span(
        span_name,
        trace_id,
        metadata={
            "backend": "kokoro",
            "text_characters": len(clean_text),
            "label": safe_label or "general",
            "segment_count": len(speech_plan.segments),
        },
    )

    speak_started_at = time.perf_counter()
    first_audio_ready_at = None

    if safe_label == "brain_response":
        performance.mark(
            "brain_response_tts_started",
            trace_id,
            only_once=True,
        )

    total_playback_seconds = 0.0
    outcome = "ok"

    def remember_remaining_response() -> None:
        if shared_state is None:
            return

        shared_state["current_spoken_text"] = (
            speech_plan.current_segment or ""
        )

        remaining_text = speech_plan.remaining_text.strip()
        if remaining_text:
            shared_state["paused_response"] = remaining_text

    try:
        if pipeline is None:
            print("Avens (Text Only):", clean_text)
            outcome = "pipeline_unavailable"
            return True

        print("Avens:", clean_text)

        if not clean_text:
            outcome = "empty_text"
            return False

        if speech_plan.is_complete:
            outcome = "empty_plan"
            return False

        if (
            shared_state
            and shared_state.get("interrupt", False)
        ):
            print(" Speech Interrupted by User!")
            remember_remaining_response()
            outcome = "interrupted_before_start"
            return False

        performance.mark_span(
            span_id,
            "generator_started",
            only_once=True,
        )

        while not speech_plan.is_complete:
            current_segment = speech_plan.current_segment

            if current_segment is None:
                break

            if shared_state is not None:
                shared_state["current_spoken_text"] = (
                    current_segment
                )

            generator = pipeline(
                current_segment,
                voice=voicepack,
                speed=1.0,
            )

            for _, _, audio_chunk in generator:
                if (
                    shared_state
                    and shared_state.get("interrupt", False)
                ):
                    print(" Speech Interrupted by User!")
                    sd.stop()
                    remember_remaining_response()
                    outcome = "interrupted"
                    return False

                if hasattr(audio_chunk, "cpu"):
                    audio_np = audio_chunk.cpu().numpy()
                else:
                    audio_np = np.array(audio_chunk)

                if len(audio_np) == 0:
                    continue

                is_first_chunk = (
                    first_audio_ready_at is None
                )
                chunk_ready_at = time.perf_counter()

                if is_first_chunk:
                    first_audio_ready_at = chunk_ready_at

                    performance.mark_span(
                        span_id,
                        "first_audio_chunk_ready",
                        only_once=True,
                    )

                    if safe_label == "brain_response":
                        performance.mark(
                            "brain_response_audio_chunk_ready",
                            trace_id,
                            only_once=True,
                        )

                chunk_energy = np.mean(np.abs(audio_np))

                try:
                    from ui.visualizer import audio_instance

                    audio_instance.set_tts_level(
                        chunk_energy * 1.5
                    )
                except Exception:
                    pass

                sd.play(audio_np, samplerate=24000)

                if is_first_chunk:
                    performance.mark_span(
                        span_id,
                        "first_playback_queued",
                        only_once=True,
                    )

                    # First assistant audio in the entire voice turn.
                    performance.mark(
                        "first_answer_audio",
                        trace_id,
                        only_once=True,
                    )

                    # Specific result-audio marker for camera/Lens
                    # benchmarks.
                    if safe_label:
                        performance.mark(
                            f"{safe_label}_first_audio",
                            trace_id,
                            only_once=True,
                        )

                duration = len(audio_np) / 24000.0
                total_playback_seconds += duration

                elapsed = 0.0
                while elapsed < duration:
                    if (
                        shared_state
                        and shared_state.get(
                            "interrupt",
                            False,
                        )
                    ):
                        print(" Speech Interrupted by User!")
                        sd.stop()
                        remember_remaining_response()
                        outcome = "interrupted"
                        return False

                    time.sleep(0.05)
                    elapsed += 0.05

            speech_plan.mark_current_complete()

        if shared_state is not None:
            shared_state["current_spoken_text"] = ""

        if first_audio_ready_at is None:
            outcome = "no_audio"
            return True

        return True

    except Exception as error:
        print(f"⚠️ TTS Error: {error}")
        outcome = "tts_error"
        return True

    finally:
        if first_audio_ready_at is not None:
            performance.record_stage(
                f"{stage_prefix}_time_to_first_audio_seconds",
                first_audio_ready_at - speak_started_at,
                trace_id,
            )
            performance.record_stage(
                f"{stage_prefix}_playback_seconds",
                total_playback_seconds,
                trace_id,
            )
            performance.record_stage(
                f"{stage_prefix}_total_seconds",
                time.perf_counter() - speak_started_at,
                trace_id,
            )
            performance.add_metric(
                f"{stage_prefix}_audio_seconds",
                total_playback_seconds,
                trace_id,
            )

        performance.finish_span(
            span_id,
            outcome=outcome,
        )

        try:
            from ui.visualizer import audio_instance

            audio_instance.set_tts_level(0)
        except Exception:
            pass

        if owns_trace:
            performance.finish(
                trace_id,
                outcome=outcome,
            )