import sounddevice as sd

def get_active_mic():
    try:
        devices = sd.query_devices()
        valid_mics = []

        # Find real microphones (ignore virtual stereos/speakers)
        for i, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                name = dev['name'].lower()
                if "speaker" in name or "stereo mix" in name or "midi" in name:
                    continue
                valid_mics.append(i)

        if not valid_mics:
            return None

        # Safely grab the most stable Windows drivers (MME or WASAPI)
        for i in valid_mics:
            try:
                hostapi = sd.query_hostapis(devices[i]['hostapi'])['name']
                if "MME" in hostapi or "WASAPI" in hostapi:
                    return i
            except: pass

        # Safe fallback
        return valid_mics[0] 
        
    except Exception as e:
        print(f"⚠️ Mic Scanner Error: {e}")
        return None