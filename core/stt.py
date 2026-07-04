import threading
import queue
import time

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from utils.mic_check import get_active_mic
from utils.microphone_lock import microphone_lock
from core.performance import performance


model = None
audio_queue = queue.Queue()


def audio_callback(indata, frames, time_info, status):
    if status:
        pass
    audio_queue.put(indata.copy())


def init_model():
    global model

    if model is not None:
        print("✅ Faster-Whisper already initialized.")
        return

    print("🧠 Initializing Faster-Whisper Engine...")
    try:
        model = WhisperModel(
            "distil-small.en",
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
        )
        print("✅ Success: Faster-Whisper Engine Online on CPU.")
    except Exception as error:
        print(f"⚠️ CPU Primary Initialization failed: {error}. Trying fallback...")
        try:
            model = WhisperModel(
                "tiny.en",
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
            )
            print("✅ Success: Faster-Whisper Fallback Engine Online on CPU.")
        except Exception as fallback_error:
            print(f"❌ CRITICAL: Faster-Whisper failed entirely. {fallback_error}")


def listen(silence_limit=1.8, max_duration=15):
    global model

    trace_id = performance.current_trace_id()
    owns_trace = trace_id is None

    if owns_trace:
        trace_id = performance.begin(
            "stt_listen",
            metadata={
                "backend": "faster_whisper",
                "silence_limit_seconds": silence_limit,
                "max_duration_seconds": max_duration,
            },
        )

    listen_started_at = time.perf_counter()
    outcome = "ok"

    try:
        if model is None:
            model_init_started_at = time.perf_counter()

            init_model()

            performance.record_stage(
                "stt_model_init_seconds",
                time.perf_counter() - model_init_started_at,
                trace_id,
            )

            if model is None:
                outcome = "model_unavailable"
                return ""

        print("🎤 Listening...")
        time.sleep(0.1)

        # Flush audio left over from a prior recording stream.
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break

        sample_rate = 16000
        # Smaller chunks let Avens detect the end of speech more precisely.
        # Keep the same silence_limit policy for now.
        chunk_duration = 0.25

        chunk_samples = int(sample_rate * chunk_duration)
        energy_threshold = 0.015

        recorded_chunks = []
        has_spoken = False
        mic_id = get_active_mic()

        capture_started_at = None
        last_voice_at = None

        performance.add_metadata(
            {
                "sample_rate": sample_rate,
                "chunk_duration_seconds": chunk_duration,
                "energy_threshold": energy_threshold,
                "microphone_id": mic_id,
            },
            trace_id,
        )

        try:
            lock_wait_started_at = time.perf_counter()

            # Wake word and barge-in share this microphone lock.
            with microphone_lock:
                performance.record_stage(
                    "stt_microphone_lock_wait_seconds",
                    time.perf_counter() - lock_wait_started_at,
                    trace_id,
                )

                with sd.InputStream(
                    device=mic_id,
                    samplerate=sample_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=chunk_samples,
                    callback=audio_callback,
                ):
                    capture_started_at = time.perf_counter()
                    performance.mark(
                        "stt_capture_started",
                        trace_id,
                        only_once=True,
                    )

                    while True:
                        try:
                            chunk = audio_queue.get(timeout=2.0)
                        except queue.Empty:
                            print("⚠️ Mic timeout.")
                            outcome = "mic_timeout"
                            break

                        recorded_chunks.append(chunk)
                        energy = np.sqrt(np.mean(chunk ** 2))
                        now = time.perf_counter()

                        if energy > energy_threshold:
                            if not has_spoken:
                                has_spoken = True
                                performance.mark(
                                    "user_speech_started",
                                    trace_id,
                                    only_once=True,
                                )

                            last_voice_at = now

                            # This is overwritten each time speech is detected,
                            # leaving the final real voice chunk as speech end.
                            performance.mark(
                                "user_speech_end",
                                trace_id,
                            )

                        elif has_spoken and last_voice_at is not None:
                            silence_elapsed = now - last_voice_at

                            if silence_elapsed >= silence_limit:
                                break

                        if (
                            len(recorded_chunks) * chunk_duration
                            > max_duration
                        ):
                            outcome = "max_duration_reached"
                            break

        except sd.PortAudioError as error:
            print(f"⚠️ Recording audio error: {error}")
            outcome = "recording_error"
            return ""

        except Exception as error:
            print(f"❌ Recording pipeline failure: {error}")
            outcome = "recording_error"
            return ""

        finally:
            if capture_started_at is not None:
                capture_finished_at = time.perf_counter()

                performance.record_stage(
                    "stt_audio_capture_seconds",
                    capture_finished_at - capture_started_at,
                    trace_id,
                )

                performance.mark(
                    "stt_capture_finished",
                    trace_id,
                )

                if last_voice_at is not None:
                    performance.record_stage(
                        "stt_silence_tail_seconds",
                        capture_finished_at - last_voice_at,
                        trace_id,
                    )

        if not recorded_chunks:
            outcome = "no_audio"
            return ""

        audio_data = np.concatenate(recorded_chunks).flatten()

        performance.add_metric(
            "stt_audio_duration_seconds",
            len(audio_data) / sample_rate,
            trace_id,
        )

        print("Transcribing...")

        transcription_started_at = time.perf_counter()
        performance.mark(
            "stt_decode_started",
            trace_id,
            only_once=True,
        )

        try:
            segments, _ = model.transcribe(
                audio_data,
                beam_size=5,
                vad_filter=True,
            )

            text = "".join(
                segment.text
                for segment in segments
            ).strip()

        except Exception as error:
            print(f"⚠️ Transcription inference failed: {error}")
            text = ""
            outcome = "transcription_error"

        finally:
            performance.record_stage(
                "stt_decode_seconds",
                time.perf_counter() - transcription_started_at,
                trace_id,
            )

            performance.mark(
                "stt_decode_finished",
                trace_id,
            )

        if not text and outcome == "ok":
            outcome = "empty_transcript"

        performance.add_metric(
            "transcript_characters",
            len(text),
            trace_id,
        )

        print("You said:", text)
        return text

    finally:
        performance.record_stage(
            "stt_listen_total_seconds",
            time.perf_counter() - listen_started_at,
            trace_id,
        )

        performance.mark(
            "stt_listen_finished",
            trace_id,
        )

        if owns_trace:
            performance.finish(
                trace_id,
                outcome=outcome,
            )