import threading
import queue
import time
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from utils.mic_check import get_active_mic

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
        # 🔥 THE FIX: 'default' compute type prevents AVX instruction crashes on CPU.
        # cpu_threads=4 prevents it from fighting PyTorch (Kokoro) for processor control.
        model = WhisperModel(
            "distil-small.en", 
            device="cpu", 
            compute_type="int8", 
            cpu_threads=4
        )
        print("✅ Success: Faster-Whisper Engine Online on CPU.")
    except Exception as e:
        print(f"⚠️ CPU Primary Initialization failed: {e}. Trying fallback...")
        try:
            model = WhisperModel(
                "tiny.en", 
                device="cpu", 
                compute_type="int8", 
                cpu_threads=4
            )
            print("✅ Success: Faster-Whisper Fallback Engine Online on CPU.")
        except Exception as e2:
            print(f"❌ CRITICAL: Faster-Whisper failed entirely. {e2}")

def listen(silence_limit=1.8, max_duration=15):
    global model
    if model is None:
        init_model()
        if model is None:
            return ""
            
    print("🎤 Listening...")
    time.sleep(0.1)
    
    # Flush any stale data left in the queue
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break
            
    fs = 16000
    chunk_duration = 0.5  
    chunk_samples = int(fs * chunk_duration)
    # Give yourself time to pause and think mid-sentence  
    energy_threshold = 0.015
    recorded_chunks = []
    silence_counter = 0
    has_spoken = False
    mic_id = get_active_mic()
    
    try:
        with sd.InputStream(device=mic_id, samplerate=fs, channels=1, dtype='float32',
                            blocksize=chunk_samples, callback=audio_callback):
            while True:
                try:
                    chunk = audio_queue.get(timeout=2.0)
                except queue.Empty:
                    print("⚠️ Mic timeout.")
                    break
                    
                recorded_chunks.append(chunk)
                energy = np.sqrt(np.mean(chunk**2))
                
                if energy > energy_threshold:
                    has_spoken = True
                    silence_counter = 0
                elif has_spoken:
                    silence_counter += chunk_duration
                    
                if has_spoken and silence_counter >= silence_limit:
                    break
                if len(recorded_chunks) * chunk_duration > max_duration:
                    break
    except Exception as e:
        print(f"❌ Recording pipeline failure: {e}")
        return ""
        
    if not recorded_chunks:
        return ""
        
    # Flatten into a 1D float32 numpy array
    audio_data = np.concatenate(recorded_chunks).flatten()
    print("Transcribing...")
    try:
        # Pass the raw RAM buffer directly to the CPU/GPU
        segments, _ = model.transcribe(audio_data, beam_size=5, vad_filter=True)
        text = "".join([segment.text for segment in segments]).strip()
    except Exception as e:
        print(f"⚠️ Transcription inference failed: {e}")
        text = ""
        
    print("You said:", text)
    return text