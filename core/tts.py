import os
import time
import sounddevice as sd
import numpy as np
import torch
from kokoro import KPipeline
from config import BASE_PATH

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

def speak(text, shared_state=None):
    if pipeline is None:
        print("Avens (Text Only):", text)
        return True
        
    print("Avens:", text)
    text = text.replace('"', '').strip()
    if not text:
        return False
        
    # Check for immediate wake-word interruption before starting
    if shared_state and shared_state.get("interrupt", False):
        print("🛑 Speech Interrupted by User!")
        return False
        
    try:
        # Generate the audio stream
        generator = pipeline(text, voice=voicepack, speed=1.0)
        for gs, ps, audio_chunk in generator:
            # 🛑 Check mid-sentence for instant user interruption
            if shared_state and shared_state.get("interrupt", False):
                print("🛑 Speech Interrupted by User!")
                sd.stop()
                try:
                    from ui.visualizer import audio_instance
                    audio_instance.set_tts_level(0)
                except: pass
                return False
                
            if hasattr(audio_chunk, 'cpu'):
                audio_np = audio_chunk.cpu().numpy()
            else:
                audio_np = np.array(audio_chunk)
                
            if len(audio_np) > 0:
                # 🎨 DYNAMIC ORB AMPLITUDE: Calculate energy per chunk
                chunk_energy = np.mean(np.abs(audio_np))
                try:
                    from ui.visualizer import audio_instance
                    audio_instance.set_tts_level(chunk_energy * 1.5)  
                except: pass
                
                # Stream directly to speakers
                sd.play(audio_np, samplerate=24000)
                
                # 🔥 FIX: Replaced sd.wait() with a non-blocking check loop!
                # This checks the interrupt flag 20 times a second while speaking
                duration = len(audio_np) / 24000.0
                elapsed = 0.0
                while elapsed < duration:
                    if shared_state and shared_state.get("interrupt", False):
                        print("🛑 Speech Interrupted by User!")
                        sd.stop()
                        try:
                            from ui.visualizer import audio_instance
                            audio_instance.set_tts_level(0)
                        except: 
                            pass
                        return False  # Speech was interrupted
                    time.sleep(0.05)
                    elapsed += 0.05
    except Exception as e:
        print(f"⚠️ TTS Error: {e}")
        
    # Clear visualizer level when sentence concludes
    try:
        from ui.visualizer import audio_instance
        audio_instance.set_tts_level(0)
    except: pass
    return True