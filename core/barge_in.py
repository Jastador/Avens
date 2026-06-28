import time
import numpy as np
import sounddevice as sd
from utils.mic_check import get_active_mic

def listen_for_speech_interrupt(shared_state, threshold=0.012, required_hits=3):
    """
    Detects if the user starts speaking while Avens is talking.
    This is a simple energy-based barge-in detector.

    Warning:
    If using speakers instead of headphones, Avens' own voice may trigger this.
    """
    mic_id = get_active_mic()
    hits = 0

    def callback(indata, frames, time_info, status):
        nonlocal hits

        if shared_state.get("stop_interrupt_listener", False):
            return

        # Only detect barge-in while Avens is actually speaking.
        # Otherwise random mic noise during "thinking" can fake an interrupt.
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
        with sd.InputStream(
            device=mic_id,
            samplerate=16000,
            channels=1,
            dtype="float32",
            blocksize=800,
            callback=callback
        ):
            while not shared_state.get("stop_interrupt_listener", False):
                if shared_state.get("interrupt", False):
                    break
                time.sleep(0.05)

    except Exception as e:
        print(f"⚠️ Barge-in listener failed: {e}")