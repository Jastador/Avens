import sounddevice as sd
import numpy as np
from utils.mic_check import get_active_mic

class AudioLevel:
    def __init__(self):
        self.wave = np.zeros(512)
        self.tts_level = 0
        self.stream = None
        mic_id = get_active_mic()
        try:
            self.stream = sd.InputStream(
                device=mic_id,  # 🔥 Explicitly force the working mic
                samplerate=16000,
                channels=1,
                blocksize=512,
                callback=self.callback
            )
            self.stream.start()
        except Exception as e:
            print(f"⚠️ Visualizer Warning: {e}")

    def callback(self, indata, frames, time, status):
        if status:
            return
        audio = indata[:, 0]
        self.wave = audio.copy()

    def get_wave(self):
        return self.wave

    def set_tts_level(self, value):
        self.tts_level = value

    def get_combined_level(self):
        mic_level = np.mean(np.abs(self.wave))
        return mic_level + self.tts_level

# 🔥 SINGLE SHARED INSTANCE
audio_instance = AudioLevel()