import json
from collections.abc import Callable
import time
from pathlib import Path

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

from config import BASE_PATH
from utils.mic_check import get_active_mic
from utils.microphone_lock import microphone_lock
from core.performance import performance


SAMPLE_RATE = 16000
BLOCK_SIZE = 8000  # 0.5 seconds

# Public phrase: “Hey Avens”
# Vosk's internal spelling for how your pronunciation is recognized:
TARGET_ALIAS = "hey evans"

# Restrict recognition to the target sound or unknown speech.
GRAMMAR = [
    TARGET_ALIAS,
    "[unk]",
]

MODEL_DIR = Path(BASE_PATH) / "models" / "vosk-model-small-en-us-0.15"

_vosk_model = None

def _should_stop_wait(
    should_stop: Callable[[], bool] | None,
) -> bool:
    """Safely check whether another app task needs the wake loop."""
    if should_stop is None:
        return False

    try:
        return bool(should_stop())
    except Exception as error:
        print(
            "⚠️ Wake listener stop check error: "
            f"{error}. Continuing safely."
        )
        return False

def get_wake_model(
    trace_id: str | None = None,
) -> Model:
    """Load the Vosk model once, then reuse it."""
    global _vosk_model

    if _vosk_model is not None:
        performance.add_metric(
            "wake_model_was_cached",
            True,
            trace_id,
        )

        return _vosk_model

    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            "Vosk model folder not found:\n"
            f"{MODEL_DIR}"
        )

    SetLogLevel(-1)

    print("Loading Vosk wake model...")

    model_load_started_at = time.perf_counter()

    try:
        _vosk_model = Model(str(MODEL_DIR))

        return _vosk_model

    finally:
        performance.record_stage(
            "wake_model_load_seconds",
            time.perf_counter() - model_load_started_at,
            trace_id,
        )

        performance.add_metric(
            "wake_model_was_cached",
            False,
            trace_id,
        )


def listen_for_wake_word(
    shared_state=None,
    as_interrupt=False,
    should_stop: Callable[[], bool] | None = None,
) -> bool:
    """
    Wait for “Hey Avens”.

    Normal mode creates one wake-word trace.
    Interrupt mode remains quiet so every TTS response does not flood logs.
    """
    trace_id = None
    owns_trace = not as_interrupt

    if owns_trace:
        trace_id = performance.begin(
            "wake_word_wait",
            metadata={
                "target_alias": TARGET_ALIAS,
                "sample_rate": SAMPLE_RATE,
                "block_size_samples": BLOCK_SIZE,
                "block_duration_seconds": (
                    BLOCK_SIZE / SAMPLE_RATE
                ),
            },
        )

    wait_started_at = time.perf_counter()
    stream_ready_at = None
    outcome = "waiting"

    try:
        if _should_stop_wait(should_stop):
            outcome = "stopped_for_pending_delivery"
            return False

        model = get_wake_model(trace_id)

        recognizer_started_at = time.perf_counter()

        recognizer = KaldiRecognizer(
            model,
            SAMPLE_RATE,
            json.dumps(GRAMMAR),
        )

        performance.record_stage(
            "wake_recognizer_create_seconds",
            time.perf_counter() - recognizer_started_at,
            trace_id,
        )

        mic_lookup_started_at = time.perf_counter()

        mic_id = get_active_mic()

        performance.record_stage(
            "wake_microphone_lookup_seconds",
            time.perf_counter() - mic_lookup_started_at,
            trace_id,
        )

        performance.add_metadata(
            {
                "wake_microphone_id": mic_id,
                "wake_mode": (
                    "interrupt"
                    if as_interrupt
                    else "normal"
                ),
            },
            trace_id,
        )

        if as_interrupt:
            print("🎙️ Listening for interruption: Hey Avens")
        else:
            print("🟡 Listening for: Hey Avens")

        lock_wait_started_at = time.perf_counter()

        with microphone_lock:
            performance.record_stage(
                "wake_microphone_lock_wait_seconds",
                time.perf_counter() - lock_wait_started_at,
                trace_id,
            )

            if (
                as_interrupt
                and shared_state is not None
                and shared_state.get(
                    "stop_interrupt_listener",
                    False,
                )
            ):
                outcome = "stopped_before_stream"
                return False

            stream_open_started_at = time.perf_counter()

            with sd.RawInputStream(
                device=mic_id,
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                dtype="int16",
                channels=1,
            ) as stream:
                performance.record_stage(
                    "wake_stream_open_seconds",
                    time.perf_counter() - stream_open_started_at,
                    trace_id,
                )

                stream_ready_at = time.perf_counter()

                performance.mark(
                    "wake_stream_ready",
                    trace_id,
                    only_once=True,
                )

                while True:
                    if _should_stop_wait(should_stop):
                        outcome = "stopped_for_pending_delivery"
                        return False

                    if (
                        as_interrupt
                        and shared_state is not None
                        and shared_state.get(
                            "stop_interrupt_listener",
                            False,
                        )
                    ):
                        outcome = "stopped_by_app"
                        return False

                    audio_data, overflowed = stream.read(BLOCK_SIZE)

                    if overflowed:
                        print("⚠️ Wake listener audio overflow.")

                    recognition_started_at = time.perf_counter()

                    accepted = recognizer.AcceptWaveform(
                        bytes(audio_data)
                    )

                    recognition_seconds = (
                        time.perf_counter()
                        - recognition_started_at
                    )

                    if not accepted:
                        continue

                    result = json.loads(
                        recognizer.Result()
                    )

                    heard = result.get(
                        "text",
                        "",
                    ).strip().lower()

                    if heard != TARGET_ALIAS:
                        continue

                    performance.record_stage(
                        "wake_final_block_recognition_seconds",
                        recognition_seconds,
                        trace_id,
                    )

                    if stream_ready_at is not None:
                        performance.record_stage(
                            "wake_stream_to_detection_seconds",
                            time.perf_counter()
                            - stream_ready_at,
                            trace_id,
                        )

                    performance.mark(
                        "wake_detected",
                        trace_id,
                        only_once=True,
                    )

                    if as_interrupt and shared_state is not None:
                        shared_state["interrupt"] = True
                        outcome = "interrupt_detected"
                        print("🛑 Avens interrupted by wake phrase.")
                    else:
                        outcome = "detected"
                        print("🟢 Hey Avens detected.")

                    return True

    except sd.PortAudioError as error:
        print(
            f"⚠️ Wake listener audio error: {error}. "
            "Retrying safely."
        )

        outcome = "audio_error"
        return False

    except Exception as error:
        print(
            f"⚠️ Vosk wake listener error: {error}. "
            "Retrying safely."
        )

        outcome = "unexpected_error"
        return False

    finally:
        performance.record_stage(
            "wake_total_wait_seconds",
            time.perf_counter() - wait_started_at,
            trace_id,
        )

        if owns_trace:
            performance.finish(
                trace_id,
                outcome=outcome,
            )