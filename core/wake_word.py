import json
from pathlib import Path

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

from config import BASE_PATH


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


def get_wake_model() -> Model:
    """Load the Vosk model once, then reuse it."""
    global _vosk_model

    if _vosk_model is not None:
        return _vosk_model

    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            "Vosk model folder not found:\n"
            f"{MODEL_DIR}"
        )

    SetLogLevel(-1)

    print("Loading Vosk wake model...")
    _vosk_model = Model(str(MODEL_DIR))

    return _vosk_model


def listen_for_wake_word(shared_state=None, as_interrupt=False) -> bool:
    """
    Wait for “Hey Avens”.

    Normal mode:
        Called before Avens says “Yes Sir?”

    Interrupt mode:
        Called in the background while Avens is speaking.
        It sets shared_state['interrupt'] = True when you say the wake phrase.
    """
    model = get_wake_model()

    recognizer = KaldiRecognizer(
        model,
        SAMPLE_RATE,
        json.dumps(GRAMMAR),
    )

    if as_interrupt:
        print("🎙️ Listening for interruption: Hey Avens")
    else:
        print("🟡 Listening for: Hey Avens")

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            dtype="int16",
            channels=1,
        ) as stream:
            while True:
                # During speech, the app tells this listener to stop
                # once TTS has ended naturally.
                if (
                    as_interrupt
                    and shared_state is not None
                    and shared_state.get("stop_interrupt_listener", False)
                ):
                    return False

                audio_data, overflowed = stream.read(BLOCK_SIZE)

                if overflowed:
                    print("⚠️ Wake listener audio overflow.")

                if not recognizer.AcceptWaveform(bytes(audio_data)):
                    continue

                result = json.loads(recognizer.Result())
                heard = result.get("text", "").strip().lower()

                if heard != TARGET_ALIAS:
                    continue

                if as_interrupt and shared_state is not None:
                    shared_state["interrupt"] = True
                    print("🛑 Avens interrupted by wake phrase.")
                else:
                    print("🟢 Hey Avens detected.")

                return True

    except Exception as error:
        print(f"⚠️ Vosk wake listener error: {error}")
        raise