import threading
import time

def _background_timer(seconds, task):
    time.sleep(seconds)
    # 🔥 Play a loud, repeating Windows alert chime to grab your attention
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(1500, 400) # 1500Hz for 400ms
            time.sleep(0.1)
    except:
        pass

def set_reminder(seconds, task):
    print(f"⏰ Ghost Thread Started: {seconds} seconds for '{task}'")
    t = threading.Thread(target=_background_timer, args=(seconds, task), daemon=True)
    t.start()