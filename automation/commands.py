import webbrowser
import datetime
import pyautogui
import time
import pygetwindow as gw
import ctypes
import re
from core.memory import save_memory
from core.researcher import research_and_summarize
from core.butler import set_reminder
from skills.app_launcher import launch_catalog_app
import screen_brightness_control as sbc

# pycaw for precise Windows volume control
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

def force_volume_change(action, steps=5):
    # Fallback for relative volume control
    vk_code = 0xAE # Volume Down
    if action == "up": vk_code = 0xAF
    elif action == "mute": vk_code = 0xAD
    for _ in range(steps):
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)

def set_exact_volume(level):
    """Set the Windows master volume and report whether it was precise."""
    scalar = max(0.0, min(1.0, float(level) / 100.0))
    com_initialized = False

    try:
        import pythoncom

        pythoncom.CoInitialize()
        com_initialized = True

        device = AudioUtilities.GetSpeakers()
        volume = device.EndpointVolume
        volume.SetMasterVolumeLevelScalar(scalar, None)
        return True

    except Exception as error:
        print(f"⚠️ Precise volume API error: {error}")

        # Approximate fallback only, not a fake “exact” success.
        force_volume_change("down", 50)
        force_volume_change("up", round(level / 2))
        return False

    finally:
        if com_initialized:
            pythoncom.CoUninitialize()

def execute_command(ai_tag, shared_state):
    vol_msg = ""
    tag = ai_tag.strip().upper()

    try:
        from core.brain import chat_history
        user_prompt = chat_history[-1]["content"].lower()
    except Exception:
        user_prompt = ""

    # ==========================================
    # 1. DISCORD MACRO
    # ==========================================
    if ("join" in user_prompt and "discord" in user_prompt) or any(word in tag for word in ["DISCORD", "JOIN", "VOICE", "NAME", "ROOM"]):
        match = re.search(r'join (?:the )?([a-z0-9\s]+?)(?:\s+channel|\s+voice|\s+in discord|$)', user_prompt)
        channel_name = match.group(1).strip() if match else "music"

        discord_windows = gw.getWindowsWithTitle("Discord")
        if discord_windows:
            win = discord_windows[0]
            if win.isMinimized: win.restore()
            try: win.activate()
            except: pass
            time.sleep(1)
        else:
            launch_result = launch_catalog_app("Discord")

            if not launch_result.success:
                return launch_result.message

            time.sleep(9)

        pyautogui.hotkey('ctrl', 'k')
        time.sleep(0.5)
        pyautogui.write(f'!{channel_name}', interval=0.05)
        time.sleep(1)
        pyautogui.press('enter')
        return f"Joining the {channel_name.title()} voice channel, sir."

    # ==========================================
    # 2. EXACT SYSTEM CONTROLS (Bulletproof Regex)
    # ==========================================
    elif tag == "<CMD: NOX>":
        try: sbc.set_brightness(0)
        except: pass
        return "Nox. The screen is black. Unfortunately, Acer's NitroSense firmware refuses to let me extinguish your keyboard lights, so you'll have to press Fn and F9 yourself like a peasant."

    elif tag == "<CMD: LUMUS>":
        try: sbc.set_brightness(100)
        except: pass
        return "Lumus. Maximum screen illumination, sir."

    elif tag == "<CMD: READING_MODE>":
        try: sbc.set_brightness(20)
        except: pass
        return "Reading mode engaged. Brightness lowered to reduce eye strain, sir."

    elif any(w in tag for w in ["BRIGHT", "SCREEN", "DISPLAY"]):
        match = re.search(r'\d+', tag)
        if match:
            level = min(100, max(0, int(match.group()))) # Caps at 100 so "250" doesn't break it
            try: sbc.set_brightness(level)
            except: pass
            return f"Display brightness set to {level} percent, sir."

    elif any(w in tag for w in ["VOL", "AUDIO", "SOUND", "LEVEL", "MUTE"]):
        match = re.search(r'\d+', tag)
        if match:
            level = min(100, max(0, int(match.group())))
            precise = set_exact_volume(level)

            if precise:
                return f"Audio locked to {level} percent, sir."

            return (
                f"Precise volume control failed, sir. "
                f"I adjusted it approximately to {level} percent."
            )
        # Fallback if no number is given
        if any(w in user_prompt for w in ["mute", "silence", "off"]):
            force_volume_change("mute", 1)
            return "System audio muted, sir."
        elif any(w in user_prompt for w in ["down", "lower", "quiet", "decrease", "bit"]):
            force_volume_change("down", 8)
            return "Turning the volume down, sir."
        else:
            force_volume_change("up", 8)
            return "Turning the volume up, sir."

    # ==========================================
    # 2.5 DYNAMIC VECTOR MEMORY HOOKS (Bulletproof Catch-All)
    # ==========================================
    elif any(tag.startswith(f"<{w}") for w in ["MEMORY", "REMEMBER", "SAVE", "LEARN"]):
        try:
            # Safely grab the text after the colon, no matter what tag he hallucinated
            fact_to_save = ai_tag.split(":", 1)[1].replace(">", "").strip()
            save_memory(fact_to_save)
            return f"Fact successfully indexed into long-term cognitive storage, sir."
        except Exception as e:
            return f"I encountered an indexing issue attempting to save that memory, sir."

    # ==========================================
    # 4. AUTONOMOUS WEB RESEARCHER
    # ==========================================
    elif any(t in tag for t in ["<RESEARCH", "<FINANCE", "<FETCH", "<RUN"]):
        query = tag.split(":", 1)[1].replace(">", "").replace("|", " ").replace("_", " ").strip()
        if "price" in user_prompt or "rate" in user_prompt or "stock" in user_prompt:
            query = f"{query} current stock price today market summary"
        if shared_state: shared_state["state"] = "thinking"
        return research_and_summarize(query)

    # ==========================================
    # 5. GHOST THREAD REMINDERS
    # ==========================================
    elif any(w in tag for w in ["REMIND", "TIMER", "DELAY", "WAIT"]):
        try:
            total_seconds = 0
            hr_match, min_match, sec_match = re.search(r'(\d+)\s*hour', user_prompt), re.search(r'(\d+)\s*minute', user_prompt), re.search(r'(\d+)\s*second', user_prompt)
            if hr_match: total_seconds += int(hr_match.group(1)) * 3600
            if min_match: total_seconds += int(min_match.group(1)) * 60
            if sec_match: total_seconds += int(sec_match.group(1))
            if total_seconds == 0:
                first_num = re.search(r'\d+', user_prompt)
                total_seconds = int(first_num.group()) if first_num else 5
            set_reminder(total_seconds, "your requested task")
            return f"Timer set for {total_seconds} seconds."
        except Exception as e:
            return "I encountered an error setting that timer, sir."

    # ==========================================
    # 6. UTILITIES & MEDIA
    # ==========================================
    elif tag == "<CMD: ANALYZE_SCREEN>" or any(phrase in user_prompt for phrase in ["look at my screen", "what am i looking", "read my screen", "what's on my screen", "see my screen"]):
        try:
            import base64
            import requests
            # 1. Take a silent screenshot
            filepath = "temp_screen.png"
            pyautogui.screenshot(filepath)
            # 2. Convert image to base64 so Ollama can read it
            with open(filepath, "rb") as img_file:
                img_b64 = base64.b64encode(img_file.read()).decode("utf-8")
            # 3. Ping the dedicated Moondream vision model
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": "moondream",
                "prompt": "You are a sarcastic AI assistant named Avens. Briefly describe what you see on this computer screen in 2 sentences. If it's a trading chart, mock the user's financial choices. If it's code, mock their programming skills.",
                "images": [img_b64],
                "stream": False
            }
            response = requests.post(url, json=payload, timeout=60)
            if response.status_code == 200:
                analysis = response.json().get("response", "I see pixels, sir.")
                return f"Processing visual data... {analysis}"
            else:
                return "My visual cortex failed to process the screen data, sir."
        except Exception as e:
            print(f"⚠️ Screen Analysis Error: {e}")
            return "I am unable to link with the Moondream visual node, sir."

    elif tag.startswith("<PLAY:") or tag.startswith("<STREAM:"):
        query = tag.split(":")[1].replace(">", "").strip()
        webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
        return f"Searching YouTube for {query}, sir."

    elif tag.startswith("<SET_WALLPAPER:"):
        query = tag.split(":")[1].replace(">", "").strip().replace(".png", "").replace("_", " ")
        webbrowser.open(f"https://www.google.com/search?tbm=isch&q={query}+4k+wallpaper")
        return "I have opened high-resolution options for your wallpaper, sir."
        
    elif tag == "<CMD: SILENCE_NOTIFS>":
        force_volume_change("mute", 1)
        return "System silenced, sir. You are alone with your P&L."

    elif "TIME" in tag and "TIMER" not in tag:
        return f"It is currently {datetime.datetime.now().strftime('%I:%M %p')}, sir."
        
    elif "DATE" in tag:
        return f"Today is {datetime.datetime.now().strftime('%B %d, %Y')}."
        
    elif "SCREENSHOT" in tag:
        pyautogui.screenshot(f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        return "Screenshot saved."
        
    elif tag == "<CMD: VISION_ON>":
        from core.vision import start_vision
        start_vision()
        return "Activating optical sensors. I can see you sir."
        
    elif tag == "<CMD: VISION_OFF>":
        from core.vision import stop_vision
        stop_vision()
        return "Optical sensors deactivated. Going blind, sir."    
        
    elif tag == "<CMD: HIDE>":
        shared_state["visible"] = False
        return "Going dark, sir."
        
    elif tag == "<CMD: SHOW>":
        shared_state["visible"] = True
        return "I am back online."

    return None