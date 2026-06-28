print("APP FILE STARTED")

import os
import sys

from dotenv import load_dotenv


BASE_PATH = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_PATH, ".env"), override=False)

# Keep model caches local to this clone unless AVENS_HF_HOME overrides it.
os.environ["HF_HOME"] = os.getenv(
    "AVENS_HF_HOME",
    os.path.join(BASE_PATH, "models", "huggingface"),
)

offline_mode = os.getenv(
    "AVENS_OFFLINE_MODE",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}

# New public installs may download required model files once.
# Existing private installs can keep AVENS_OFFLINE_MODE=true in .env.
for variable in (
    "HF_HUB_OFFLINE",
    "HF_DATASETS_OFFLINE",
    "TRANSFORMERS_OFFLINE",
):
    os.environ[variable] = "1" if offline_mode else "0"

# Force CPU, avoid CUDA/cuDNN drama.
os.environ["CUDA_VISIBLE_DEVICES"] = ""

# Prevent OpenMP thread collisions.
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["CT2_VERBOSE"] = "0"

import threading
import time
import re
import base64
import requests
import io
import webbrowser
import pyautogui
from PIL import Image

# IMPORTANT: Load STT first. Do not import TTS, wake_word, brain, or UI before this.
from core.stt import listen, init_model

# These will be loaded after STT is initialized.
speak = None
get_response = None
execute_command = None
listen_for_wake_word = None

# ==========================================
# UI AND ORCHESTRATION BELOW
# ==========================================

def run_ui(shared_state):
    from PyQt5.QtWidgets import QApplication
    from ui.orb import Orb

    app = QApplication(sys.argv)
    orb = Orb(shared_state)
    orb.show()
    sys.exit(app.exec_())

# SHARED STATE (with UI Visibility included)
shared_state = {
    "state": "idle",
    "interrupt": False,
    "stop_interrupt_listener": False,
    "visible": True,
    "current_spoken_text": "",
    "paused_response": ""
}

# Conversation attention window.
# After Avens responds, follow-up speech is treated as intended for Avens for this many seconds.
conversation_until = 0
CONVERSATION_TIMEOUT = 8

def load_runtime_modules():
    global speak, get_response, execute_command, listen_for_wake_word

    from core.tts import speak as _speak
    from core.brain import get_response as _get_response
    from automation.commands import execute_command as _execute_command
    from core.wake_word import listen_for_wake_word as _listen_for_wake_word

    speak = _speak
    get_response = _get_response
    execute_command = _execute_command
    listen_for_wake_word = _listen_for_wake_word

def is_tool_allowed_for_prompt(tag, user_input):
    tag_l = tag.lower()
    prompt_l = user_input.lower()

    # Open app only if user actually asked to open/launch/start something
    if tag_l.startswith("<open:"):
        return any(w in prompt_l for w in ["open", "launch", "start", "run"])

    # Research only if user asks for live/latest/current/web/news/price
    if tag_l.startswith("<research:") or tag_l.startswith("<finance:") or tag_l.startswith("<fetch:"):
        return any(w in prompt_l for w in ["latest", "current", "today", "news", "price", "search", "find", "look up", "web"])

    # Accept canonical and legacy memory tags, but only if the user asked to save a fact.
    if tag_l.startswith(("<memory:", "<remember:", "<save:", "<learn:")):
        return any(w in prompt_l for w in ["remember", "save", "note", "learn"])

    # Reminders only if user asks remind/timer/alarm
    if tag_l.startswith("<remind:"):
        return any(w in prompt_l for w in ["remind", "timer", "alarm"])

    # Commands allowed only if prompt asks for control/action
    if tag_l.startswith("<cmd:"):
        return any(w in prompt_l for w in ["volume", "brightness", "mute", "screen", "time", "date", "screenshot", "hide", "show", "vision", "camera"])

    # Play/search allowed only if user asks
    if tag_l.startswith("<play:") or tag_l.startswith("<search:"):
        return any(w in prompt_l for w in ["play", "search", "youtube", "song", "video", "find"])

    if tag_l.startswith("<analyze_screen"):
        return any(w in prompt_l for w in [
            "screen", "look at", "read my screen", "what am i looking",
            "see my screen", "analyze screen"
        ])
    print(f"🚫 Unknown tool tag blocked by default: {tag}")
    return False


MEMORY_REQUEST_PATTERN = re.compile(
    r"^\s*(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:remember|save|note|learn)\b(?:\s+that)?\s*(.*?)\s*$",
    re.IGNORECASE,
)


def extract_memory_fact(text):
    match = MEMORY_REQUEST_PATTERN.match(text.strip())
    if not match:
        return None

    fact = " ".join(match.group(1).split()).strip(" .!?")

    if not fact or fact.lower() in {"it", "this", "that"}:
        return None

    if fact.lower().startswith(("what ", "when ", "where ", "why ", "how ")):
        return None

    return fact


def is_memory_request(text):
    return bool(MEMORY_REQUEST_PATTERN.match(text.strip()))



def is_preference_memory_lookup(text):
    normalized = " ".join(text.casefold().split())

    phrases = (
        "how do i like my answers",
        "how do i prefer my answers",
        "what are my answer preferences",
        "what answer style do i prefer",
    )

    return any(phrase in normalized for phrase in phrases)


def is_resume_request(text):
    t = text.lower().strip()
    return bool(re.search(
        r"\b(yes|yeah|yep|continue|go on|resume|carry on|as you were|what were you saying|you can continue|continue please)\b",
        t
    ))

def is_cancel_resume(text):
    t = text.lower().strip()
    return bool(re.search(
        r"\b(no|stop|leave it|forget it|never mind|drop it|not now)\b",
        t
    ))

def speak_with_barge(text, pause_text=None):
    global conversation_until

    from core.barge_in import listen_for_speech_interrupt

    shared_state["interrupt"] = False
    shared_state["stop_interrupt_listener"] = False
    shared_state["state"] = "speaking"

    interrupt_thread = threading.Thread(
        target=listen_for_speech_interrupt,
        args=(shared_state,),
        daemon=True
    )
    interrupt_thread.start()

    completed = speak(text, shared_state)

    shared_state["stop_interrupt_listener"] = True

    if completed is False or shared_state.get("interrupt"):
        print("⚠️ Resume speech interrupted by user.")

        if isinstance(pause_text, str) and pause_text.strip():
            shared_state["paused_response"] = pause_text.strip()
            print(f"⏸️ Paused response kept: {pause_text.strip()}")
        conversation_until = time.time() + CONVERSATION_TIMEOUT
        return False

    return True

def avens_loop():
    global conversation_until

    try:
        speak("Avens is now online.")
        print("Loop running...")
        just_interrupted = False
        while True:
            # Reset interrupt flag at the start of a new listening cycle
            shared_state["interrupt"] = False

            was_interrupted = just_interrupted
            just_interrupted = False

            # Important:
            # We decide whether this turn is active BEFORE listen() starts,
            # not after transcription finishes.
            started_in_active_window = was_interrupted or (time.time() <= conversation_until)

            # If no active session exists, require wake word
            if not started_in_active_window:
                shared_state["state"] = "listening"
                listen_for_wake_word()

                # Wake word grants an active conversation window
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                started_in_active_window = True

                shared_state["state"] = "speaking"
                speak("Yes Sir?", shared_state)
            else:
                print("🟡 Follow-up window active. Listening without wake word...")

            shared_state["state"] = "listening"

            # If Avens was interrupted mid-speech, wait until user stops for 3 seconds
            if was_interrupted:
                if shared_state.get("paused_response"):
                    shared_state["state"] = "speaking"
                    speak_with_barge("Uhh. Shall I continue, sir?")

                    shared_state["interrupt"] = False
                    shared_state["stop_interrupt_listener"] = True

                shared_state["state"] = "listening"
                user_input = listen(silence_limit=3.0, max_duration=20)
            else:
                user_input = listen(silence_limit=1.8, max_duration=15)

            print("DEBUG USER INPUT:", user_input)

            if not user_input:
                print("⚠️ Empty input")

                # Keep listening during the active window instead of asking for wake word again
                if time.time() <= conversation_until:
                    continue

                shared_state["state"] = "idle"
                continue

            from core.attention import is_probably_talking_to_avens

            conversation_active = started_in_active_window or (time.time() <= conversation_until)

            if not is_probably_talking_to_avens(user_input, conversation_active=conversation_active):
                print("🟠 Side conversation detected. Ignoring:", user_input)

                # Still keep the active window alive briefly after side-talk
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            # Valid user input extends the active conversation window
            conversation_until = time.time() + CONVERSATION_TIMEOUT

            lower_input = user_input.lower().strip()
            paused_raw = shared_state.get("paused_response", "")

            if not isinstance(paused_raw, str):
                print(f"⚠️ Invalid paused_response type cleared: {type(paused_raw)}")
                shared_state["paused_response"] = ""
                paused = ""
            else:
                paused = paused_raw.strip()

            if paused and is_resume_request(lower_input):
                completed = speak_with_barge(
                    f"As I was saying, {paused}",
                    pause_text=paused
                )

                if completed:
                    shared_state["paused_response"] = ""
                    shared_state["current_spoken_text"] = ""
                else:
                    just_interrupted = True

                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            if paused and is_cancel_resume(lower_input):
                shared_state["state"] = "speaking"
                speak("Understood. Dropping that thought, sir.")

                shared_state["paused_response"] = ""
                shared_state["current_spoken_text"] = ""
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            # If you ask a new real question instead of saying yes/continue,
            # abandon the paused sentence and answer the new thing.
            if paused and len(lower_input.split()) > 3:
                shared_state["paused_response"] = ""
                shared_state["current_spoken_text"] = ""


            # Block non-English Whisper hallucinations (Telugu, Russian, etc.)
            if not user_input.isascii():
                print("⚠️ Non-English or gibberish detected. Ignoring.")
                shared_state["state"] = "speaking"
                speak("I didn't quite catch that, sir.", shared_state)
                shared_state["state"] = "idle"
                continue

            # Deterministic local-memory routing.
            # Save the spoken fact directly. Do not ask Ollama to rewrite it.
            memory_fact = extract_memory_fact(user_input)

            if memory_fact is not None:
                from core.memory import save_memory

                result = save_memory(memory_fact)
                shared_state["state"] = "speaking"

                if result is False:
                    speak("I could not save that memory, sir.", shared_state)
                else:
                    speak(
                        "Fact successfully indexed into long-term cognitive storage, sir.",
                        shared_state,
                    )

                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            if is_memory_request(user_input):
                shared_state["state"] = "speaking"
                speak(
                    "Tell me the exact fact you want me to remember, sir.",
                    shared_state,
                )
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            # Preference-memory lookup.
            if is_preference_memory_lookup(lower_input):
                from core.memory import load_memory

                remembered = load_memory(current_query=user_input, n_results=1)

                if remembered.startswith("- No ") or remembered.startswith("- Long-term"):
                    reply = "I do not have a saved preference for that yet, sir."
                else:
                    fact = remembered.splitlines()[0].removeprefix("- ").strip()
                    reply = f"From what I remember, {fact.rstrip(".!?")}, sir."

                shared_state["state"] = "speaking"
                speak(reply, shared_state)
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            # ---------------------------------------------
            # INSTANT INTENT ROUTING (Bypass the AI)
            # ---------------------------------------------

            # 1. GLOBAL SHUTDOWN (Instantly kills UI, threads, and vision)
            if any(phrase in lower_input for phrase in ["exit", "shut down", "goodbye", "good bye", "time to sleep", "go to sleep", "turn off completely"]):
                shared_state["state"] = "speaking"
                speak("Powering down all systems. Goodbye, sir.", shared_state)
                os._exit(0) # 🔥 This forces Windows to terminate the entire Python process instantly

            # 2. HIDE / SHOW ROUTER (Controls Orb AND Vision simultaneously)
            elif any(phrase in lower_input for phrase in ["hide yourself", "hide please", "go dark", "hide ui", "hide the orb"]):
                from core.vision import stop_vision
                stop_vision() # Automatically cut the camera feed if you hide the UI
                shared_state["visible"] = False
                shared_state["state"] = "speaking"
                speak("Going dark, sir. I am still listening in the background.", shared_state)
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue
            elif any(phrase in lower_input for phrase in ["show yourself", "come back online", "unhide", "reveal yourself", "show the orb"]):
                shared_state["visible"] = True
                shared_state["state"] = "speaking"
                speak("I am back on your screen, sir.", shared_state)
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            # 3. THE VISION ROUTER
            elif any(phrase in lower_input for phrase in ["can you see me", "watch me", "check me out", "turn on camera", "start vision", "open your eyes"]):
                from core.vision import start_vision
                start_vision()
                shared_state["state"] = "speaking"
                speak("Activating optical sensors. I can see you, sir.", shared_state)
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue
            elif any(phrase in lower_input for phrase in ["stop looking", "turn off camera", "go blind", "stop vision", "close your eyes", "stop watching me", "close the cam"]):
                from core.vision import stop_vision
                stop_vision()
                shared_state["state"] = "speaking"
                speak("Optical sensors deactivated. Going blind, sir.", shared_state)
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            # 2. INSTANT GOOGLE SEARCH ROUTER
            search_match = re.search(r'(?:search for|google|look up|search)\s+(.+)', lower_input)
            if search_match:
                query = search_match.group(1).strip()
                webbrowser.open(f"https://www.google.com/search?q={query}")
                shared_state["state"] = "speaking"
                speak(f"Opening Google to search for {query}, sir.", shared_state)
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue # 🛑 THIS STOPS THE AI FROM RUNNING

            # 3. INSTANT SCREEN ANALYSIS ROUTER (Bypasses the hallucinating brain entirely)
            if any(phrase in lower_input for phrase in ["look at my screen", "what am i looking", "read my screen", "what's on my screen", "see my screen"]):
                shared_state["state"] = "speaking"
                speak("Scanning your display now, sir...", shared_state)
                shared_state["state"] = "thinking"
                try:
                    # 1. Take screenshot and shrink it so the tiny GPU model doesn't choke
                    img = pyautogui.screenshot()
                    img.thumbnail((800, 800)) # Compress the resolution
                    # 2. Convert to a lightweight JPEG directly in RAM (no temp files!)
                    buffered = io.BytesIO()
                    img.save(buffered, format="JPEG", quality=80)
                    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    # 3. Ask Moondream a dead-simple question it can actually understand
                    url = "http://localhost:11434/api/generate"
                    payload = {
                        "model": "moondream",
                        "prompt": "Describe the main content of this computer screen in plain English. Do not read the raw text, URLs, or code strings.",
                        "images": [img_b64],
                        "stream": False
                    }
                    response = requests.post(url, json=payload, timeout=60)
                    if response.status_code == 200:
                        analysis = response.json().get("response", "").strip()
                        if analysis:
                            shared_state["state"] = "speaking"
                            # Wrap Moondream's literal observation in Avens' sarcasm
                            speak(f"It appears you are looking at {analysis.lower()} I highly doubt this is a productive use of your time, sir.", shared_state)
                        else:
                            shared_state["state"] = "speaking"
                            speak("I am looking at it, but my visual cortex is rendering blanks, sir.", shared_state)
                    else:
                        shared_state["state"] = "speaking"
                        speak("My visual cortex failed to process the screen data, sir.", shared_state)
                except Exception as e:
                    print(f"⚠️ Screen Analysis Error: {e}")
                    shared_state["state"] = "speaking"
                    speak("I am unable to link with the Moondream visual node, sir.", shared_state)
                shared_state["state"] = "idle"
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                continue # 🛑 THIS CRITICAL LINE STOPS AVENS FROM HALLUCINATING

            # ---------------------------------------------
            # REAL-TIME STREAMING & COMMAND EXECUTION LOGIC
            # ---------------------------------------------
            shared_state["state"] = "thinking"
            shared_state["interrupt"] = False
            shared_state["stop_interrupt_listener"] = False

            # Start the background thread to listen for interruptions immediately

            from core.barge_in import listen_for_speech_interrupt
            interrupt_thread = threading.Thread(
                target=listen_for_speech_interrupt,
                args=(shared_state,),
                daemon=True
            )
            interrupt_thread.start()

            has_spoken_anything = False
            blocked_tool_tag_seen = False
            # Catch sentences and tool tags from brain.py on the fly

            for item_type, content in get_response(user_input):
                # Check if you yelled "Avens" to interrupt mid-sentence
                if shared_state.get("interrupt"):
                    print("⚠️ Thought Process Interrupted by User!")
                    just_interrupted = True
                    # Keep mic active after interruption so Avens listens to what you were saying
                    conversation_until = time.time() + CONVERSATION_TIMEOUT
                    break

                # --- CASE 1: HANDLE SYSTEM COMMAND TAGS ---
                if item_type == "tag":
                    raw_tag = content.strip()

                    # Extract valid full tags only, like <OPEN: discord>
                    tags = re.findall(r"<[^<>]+>", raw_tag)
                    if not tags:
                        print(f"⚠️ Ignoring malformed tag: {raw_tag}")
                        continue

                    for fixed_tag in tags:
                        if not is_tool_allowed_for_prompt(fixed_tag, user_input):
                            print(f"🚫 Blocked hallucinated tool tag: {fixed_tag}")
                            blocked_tool_tag_seen = True
                            continue

                        print(f"⚙️ EXECUTING LIVE TAG: {fixed_tag}")
                        action_result = execute_command(fixed_tag, shared_state)

                        if not action_result:
                            continue

                        shared_state["state"] = "speaking"

                        if "time" in fixed_tag.lower() and not any(w in fixed_tag.lower() for w in ["timer", "delay", "wait"]):
                            speak(action_result, shared_state)
                        elif any(t in fixed_tag for t in ["<RESEARCH", "<FINANCE", "<FETCH", "<RUN"]):
                            speak(f"Let me check the live data, sir. {action_result}", shared_state)
                        else:
                            speak(action_result, shared_state)

                        shared_state["state"] = "thinking"
                        has_spoken_anything = True

                # --- CASE 2: HANDLE SARCASTIC / INTELLIGENT SPEECH ---
                elif item_type == "text":
                    clean_sentence = content.strip()

                    if clean_sentence.casefold().startswith("<plain_text:"):
                        clean_sentence = clean_sentence.split(":", 1)[1].strip()
                        clean_sentence = clean_sentence.rstrip("> ").strip()
                    # Apply your Arrow Trap fix inline
                    clean_sentence = clean_sentence.replace("->", " TO ")
                    # 🔥 Kill template bleed if the fine-tune tries to expose its prompt engineering
                    if "Below is an instruction" in clean_sentence:
                        clean_sentence = clean_sentence.split("Below is an instruction")[0].strip()
                    if "Write a response that appropriately" in clean_sentence:
                        clean_sentence = clean_sentence.split("Write a response that appropriately")[0].strip()
                    if clean_sentence:
                        shared_state["state"] = "speaking"
                        shared_state["current_spoken_text"] = clean_sentence

                        completed = speak(clean_sentence, shared_state)

                        if completed is False or shared_state.get("interrupt"):
                            shared_state["paused_response"] = clean_sentence
                            print(f"⏸️ Paused response stored: {clean_sentence}")
                            just_interrupted = True
                            conversation_until = time.time() + CONVERSATION_TIMEOUT
                            break

                        shared_state["current_spoken_text"] = ""
                        shared_state["state"] = "thinking"
                        has_spoken_anything = True

            if shared_state.get("interrupt"):
                print("⚠️ Speech was interrupted by user.")
                just_interrupted = True
                conversation_until = time.time() + CONVERSATION_TIMEOUT

            # Stop tracking the interruption state for this turn
            shared_state["stop_interrupt_listener"] = True

            # Fallback if the generator finished but didn't actually produce output or tags
            if not has_spoken_anything and not just_interrupted:
                shared_state["state"] = "speaking"
                if blocked_tool_tag_seen:
                    speak(
                        "I misread that as a command, sir. Please ask it again normally.",
                        shared_state,
                    )
                else:
                    speak("I did not generate a usable response, sir.", shared_state)
            if just_interrupted:
                time.sleep(0.5)
                continue
            conversation_until = time.time() + CONVERSATION_TIMEOUT
            shared_state["state"] = "idle"
    except Exception as e:
        print("🔥 THREAD CRASHED:", e)
        import traceback
        traceback.print_exc()

def main():
    print("Starting Avens...")

    # Initialize Faster-Whisper before Kokoro, Vosk, ChromaDB, PyQt, etc.
    init_model()

    # Now load the rest of the runtime modules.
    load_runtime_modules()

    threading.Thread(target=avens_loop, daemon=True).start()

    print("Launching UI...")
    run_ui(shared_state)

if __name__ == "__main__":
    main()
