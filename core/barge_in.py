import time

import numpy as np
import sounddevice as sd

from utils.mic_check import get_active_mic
from utils.microphone_lock import microphone_lock


def listen_for_speech_interrupt(shared_state, threshold=0.012, required_hits=3):
    """Detect speech while Avens is speaking.

    This listener always releases the shared microphone before normal speech
    recognition or the wake-word listener starts.
    """
    mic_id = get_active_mic()
    hits = 0

    def callback(indata, frames, time_info, status):
        nonlocal hits

        if shared_state.get("stop_interrupt_listener", False):
            return

        # Only detect barge-in while Avens is actually speaking.
        if shared_state.get("state") != "speaking":
            hits = 0
            return

        audio = indata[:, 0]
        energy = float(np.sqrt(np.mean(audio ** 2)))

        if energy > 0.006:
            print(f"🎙️ Barge energy: {energy:.4f}")

        if energy > threshold:
            hits += 1
        else:
            hits = max(0, hits - 1)

        if hits >= required_hits:
            print(f"🛑 Speech barge-in detected. Energy={energy:.4f}")
            shared_state["interrupt"] = True

    try:
        with microphone_lock:
            # The main loop may have finished speaking while this background
            # thread was waiting for the microphone lock.
            if shared_state.get("stop_interrupt_listener", False):
                return

            with sd.InputStream(
                device=mic_id,
                samplerate=16000,
                channels=1,
                dtype="float32",
                blocksize=800,
                callback=callback,
            ):
                while not shared_state.get("stop_interrupt_listener", False):
                    if shared_state.get("interrupt", False):
                        break
                    time.sleep(0.05)

    except sd.PortAudioError as error:
        print(f"⚠️ Barge-in audio error: {error}")
    except Exception as error:
        print(f"⚠️ Barge-in listener failed: {error}")
