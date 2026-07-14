print("APP FILE STARTED")

import os
import sys
import time

APP_PROCESS_STARTED_AT = time.perf_counter()

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

# Faster-Whisper selects its CTranslate2 device in core/stt.py.
# Do not hide CUDA globally here.

# Prevent OpenMP thread collisions.
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["CT2_VERBOSE"] = "0"

import threading
from datetime import datetime
import re
import base64
import requests
import io
import webbrowser
import pyautogui
from PIL import Image

# IMPORTANT: Load STT first. Do not import TTS, wake_word, brain, or UI before this.
from core.stt import listen, init_model
from core.performance import performance
from core.streamed_response_session import (
    StreamedResponseSession,
)
from core.barge_runtime import (
    consume_queued_barge_action,
    queue_barge_resolution,
    wait_for_barge_resolution,
)

# These will be loaded after STT is initialized.
speak = None
get_response = None
execute_command = None
listen_for_wake_word = None

# ==========================================
# UI AND ORCHESTRATION BELOW
# ==========================================

def run_ui(shared_state, boot_trace_id=None):
    ui_import_started_at = time.perf_counter()

    from PyQt5.QtWidgets import QApplication
    from ui.orb import Orb

    performance.record_stage(
        "boot_ui_import_seconds",
        time.perf_counter() - ui_import_started_at,
        boot_trace_id,
    )

    qt_application_started_at = time.perf_counter()

    app = QApplication(sys.argv)

    performance.record_stage(
        "boot_qt_application_create_seconds",
        time.perf_counter() - qt_application_started_at,
        boot_trace_id,
    )

    orb_started_at = time.perf_counter()

    orb = Orb(shared_state)

    performance.record_stage(
        "boot_orb_create_seconds",
        time.perf_counter() - orb_started_at,
        boot_trace_id,
    )

    ui_show_started_at = time.perf_counter()

    orb.show()

    performance.record_stage(
        "boot_ui_show_request_seconds",
        time.perf_counter() - ui_show_started_at,
        boot_trace_id,
    )

    performance.mark(
        "boot_ui_show_requested",
        boot_trace_id,
        only_once=True,
    )

    if boot_trace_id is not None:
        performance.finish(
            boot_trace_id,
            outcome="ui_shown",
        )

    sys.exit(app.exec_())

def load_runtime_modules(boot_trace_id=None):
    global speak, get_response, execute_command, listen_for_wake_word

    tts_import_started_at = time.perf_counter()

    from core.tts import speak as _speak

    performance.record_stage(
        "boot_tts_module_import_seconds",
        time.perf_counter() - tts_import_started_at,
        boot_trace_id,
    )

    brain_import_started_at = time.perf_counter()

    from core.brain import get_response as _get_response

    performance.record_stage(
        "boot_brain_module_import_seconds",
        time.perf_counter() - brain_import_started_at,
        boot_trace_id,
    )

    commands_import_started_at = time.perf_counter()

    from automation.commands import execute_command as _execute_command

    performance.record_stage(
        "boot_commands_module_import_seconds",
        time.perf_counter() - commands_import_started_at,
        boot_trace_id,
    )

    wake_import_started_at = time.perf_counter()

    from core.wake_word import (
        listen_for_wake_word as _listen_for_wake_word,
    )

    performance.record_stage(
        "boot_wake_module_import_seconds",
        time.perf_counter() - wake_import_started_at,
        boot_trace_id,
    )

    speak = _speak
    get_response = _get_response
    execute_command = _execute_command
    listen_for_wake_word = _listen_for_wake_word

# ==========================================
# SHARED RUNTIME STATE
# ==========================================

shared_state = {
    "state": "idle",
    "interrupt": False,
    "stop_interrupt_listener": False,
    "visible": True,
    "current_spoken_text": "",
    "paused_response": "",

    # Classified speech-barge state.
    "barge_in_transcript": "",
    "barge_in_intent": "",
    "barge_in_reason": "",
    "barge_in_confidence": 0.0,
    "barge_in_ready": False,
    "barge_in_status": "idle",
    "barge_in_allow_transcription": False,

    # Action queued for the following voice-loop iteration.
    "pending_barge_input": "",
    "auto_resume_paused_response": False,
    "last_barge_action": "",
    "last_barge_intent": "",
}

# After Avens responds, follow-up speech is treated as intended for Avens
# for this many seconds.
conversation_until = 0
CONVERSATION_TIMEOUT = 8

# How long the user must hold an object inside the scan box.
LENS_CAPTURE_HOLD_SECONDS = 1.6

def is_tool_allowed_for_prompt(tag, user_input):
    tag_l = tag.lower()
    prompt_l = user_input.lower()

    # App launching now belongs only to deterministic local skills.
    # Never let an LLM-generated OPEN tag reach legacy automation.
    if tag_l.startswith("<open:"):
        print(f"🚫 Legacy app-launch tag blocked: {tag}")
        return False

    # Research only if user asks for live/latest/current/web/news/price
    if tag_l.startswith("<research:") or tag_l.startswith("<finance:") or tag_l.startswith("<fetch:"):
        return any(w in prompt_l for w in ["latest", "current", "today", "news", "price", "search", "find", "look up", "web"])

    # Accept canonical and legacy memory tags, but only if the user asked to save a fact.
    if tag_l.startswith(("<memory:", "<remember:", "<save:", "<learn:")):
        return any(w in prompt_l for w in ["remember", "save", "note", "learn"])

    retired_reminder_prefixes = (
        "<remind:",
    )

    if tag_l.startswith(retired_reminder_prefixes):
        print(
            f"🚫 Retired legacy reminder tag blocked: {tag}"
        )
        return False

    retired_system_control_prefixes = (
        "<cmd: set_vol",
        "<cmd: set_bright",
        "<cmd: reading_mode",
        "<cmd: mute",
        "<cmd: silence_notifs",
        "<cmd: nox",
        "<cmd: lumus",
    )

    if tag_l.startswith(retired_system_control_prefixes):
        print(
            f"🚫 Retired legacy system-control tag blocked: {tag}"
        )
        return False

    # Remaining legacy commands are allowed only for their matching
    # non-system-control requests.
    if tag_l.startswith("<cmd:"):
        return any(
            word in prompt_l
            for word in (
                "screen",
                "time",
                "date",
                "screenshot",
                "hide",
                "show",
                "vision",
                "camera",
            )
        )

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
    """Return True only for a standalone request to abandon paused speech.

    A substring check made commands such as ``stop vision`` cancel a paused
    answer instead of reaching the Vision command router.
    """
    normalized = " ".join(text.casefold().split())
    return normalized in {
        "no",
        "nope",
        "stop",
        "stop it",
        "leave it",
        "forget it",
        "never mind",
        "drop it",
        "not now",
        "don't continue",
        "do not continue",
    }

def is_minimal_vision_request(text: str) -> bool:
    """Recognise natural requests for a cleaner camera view."""
    normalised = " ".join(text.casefold().split())

    phrases = (
        "minimal vision",
        "minimal vision mode",
        "minimal camera",
        "minimal camera mode",
        "hide vision hud",
        "hide the vision hud",
        "clean vision mode",
        "make the camera minimal",
        "make camera minimal",
        "make the camera a bit minimal",
        "make camera a bit minimal",
        "make the camera cleaner",
        "make camera cleaner",
        "remove additional info from the camera",
        "remove the additional info from the camera",
        "remove extra info from the camera",
        "remove the extra info from the camera",
        "hide camera info",
        "hide the camera info",
        "hide camera overlay",
        "remove camera overlay",
        "make it less cluttered",
    )

    return any(phrase in normalised for phrase in phrases)


def is_standard_vision_request(text: str) -> bool:
    """Recognise natural requests to restore the detailed camera view."""
    normalised = " ".join(text.casefold().split())

    phrases = (
        "show vision hud",
        "show the vision hud",
        "standard vision",
        "standard vision mode",
        "detailed vision mode",
        "make the camera normal",
        "make camera normal",
        "make it normal again",
        "bring back camera info",
        "bring back the camera info",
        "bring back additional info",
        "show additional info on the camera",
        "show extra info on the camera",
        "show camera information",
        "show the camera overlay",
        "bring back the overlay",
    )

    return any(phrase in normalised for phrase in phrases)

def is_lens_scan_request(text: str) -> bool:
    """Recognise explicit requests for online Google Lens lookup."""
    normalised = " ".join(text.casefold().split())

    phrases = (
        "what am i holding",
        "what i'm holding",
        "what im holding",
        "what i’m holding",
        "identify this online",
        "identify what i'm holding online",
        "identify what i am holding online",
        "search this online",
        "scan this online",
        "google lens this",
        "search this with lens",
        "find this online",
    )

    return any(phrase in normalised for phrase in phrases)

def normalise_mode_phrase(text: str) -> str:
    """Normalise short voice-mode replies before exact matching."""
    return re.sub(
        r"[^a-z0-9 ]+",
        "",
        " ".join(text.casefold().split()),
    ).strip()

def get_local_time_reply(text: str) -> str | None:
    """Return the Windows local time for clear time requests."""
    normalised = normalise_mode_phrase(text)

    time_phrases = {
        "what time is it",
        "what is the time",
        "whats the time",
        "whats the current time",
        "what is the current time",
        "tell me the time",
        "tell me what time it is",
        "tell me the current time",
        "current time",
        "the current time",
        "time please",
    }

    if normalised not in time_phrases:
        return None

    now = datetime.now().astimezone()

    hour = now.hour % 12 or 12
    period = "AM" if now.hour < 12 else "PM"

    return f"It is {hour}:{now.minute:02d} {period}, sir."

def get_acknowledgement_reply(text: str) -> str | None:
    """Handle short conversational acknowledgements without Ollama."""
    normalised = normalise_mode_phrase(text)

    replies = {
        "yeah": "Understood, sir.",
        "yes": "Understood, sir.",
        "yep": "Understood, sir.",
        "okay": "Alright, sir.",
        "ok": "Alright, sir.",
        "alright": "Alright, sir.",
        "got it": "Good.",
        "cool": "Noted, sir.",
        "thanks": "You're welcome, sir.",
        "thank you": "You're welcome, sir.",
    }

    return replies.get(normalised)

def is_short_mode_reply(
    normalised: str,
    choices: set[str],
) -> bool:
    """Match a short mode reply while tolerating extra trailing words."""
    if normalised in choices:
        return True

    return any(
        normalised.startswith(f"{choice} ")
        or normalised.endswith(f" {choice}")
        for choice in choices
    )

def get_mode_change_target(text: str) -> str | None:
    """Recognise an explicit request to change Avens online/offline mode."""
    normalised = normalise_mode_phrase(text)

    online_phrases = {
        "go online",
        "switch online",
        "switch to online",
        "turn online",
        "go into online mode",
    }

    offline_phrases = {
        "go offline",
        "switch offline",
        "switch to offline",
        "turn offline",
        "go local",
        "switch to local",
        "go into offline mode",
    }

    if any(phrase in normalised for phrase in online_phrases):
        return "online"

    if any(phrase in normalised for phrase in offline_phrases):
        return "offline"

    return None

def get_mode_scope_choice(text: str) -> str | None:
    """Map a short follow-up to brain, camera, or both."""
    normalised = normalise_mode_phrase(text)

    brain_choices = {
        "brain",
        "the brain",
        "ai brain",
        "assistant brain",
    }

    camera_choices = {
        "camera",
        "the camera",
        "vision",
        "camera mode",
    }

    both_choices = {
        "both",
        "both systems",
        "everything",
        "all",
    }

    if is_short_mode_reply(normalised, brain_choices):
        return "brain"

    if is_short_mode_reply(normalised, camera_choices):
        return "camera"

    if is_short_mode_reply(normalised, both_choices):
        return "both"

    return None

def get_brain_provider_choice(text: str) -> str | None:
    """Map a short spoken follow-up to one online brain provider."""
    normalised = normalise_mode_phrase(text)

    gpt_choices = {
        "gpt",
        "g p t",
        "openai",
        "chatgpt",
        "chat gpt",
        "use gpt",
        "use openai",
    }

    gemini_choices = {
        "gemini",
        "gemini ai",
        "gemini please",
        "use gemini",
        "jim and i",
        "geminy",
    }

    if is_short_mode_reply(normalised, gpt_choices):
        return "gpt"

    if is_short_mode_reply(normalised, gemini_choices):
        return "gemini"

    return None

def is_mode_status_request(text: str) -> bool:
    """Recognise requests to report the active brain and camera modes."""
    normalised = normalise_mode_phrase(text)

    phrases = {
        "mode status",
        "what mode are you in",
        "what modes are active",
        "what is online",
        "what is offline",
        "system mode",
        "system status",
    }

    return normalised in phrases

def get_camera_intelligence_request(text: str) -> str | None:
    """Map clear spoken requests to one approved camera-analysis mode."""
    normalised = " ".join(text.casefold().split())

    read_phrases = (
        "read this",
        "can you read this",
        "could you read this",
        "read what i'm holding",
        "read what i am holding",
        "what does this say",
        "read the text",
        "read this for me",
    )

    identify_phrases = (
        "what am i holding",
        "what i am holding",
        "what is this",
        "what am i showing you",
        "what i am showing you",
        "what is in my hand",
        "what's in my hand",
        "identify this",
        "identify what i'm holding",
        "identify what i am holding",
    )

    describe_phrases = (
        "describe this",
        "describe what you see",
        "what do you see",
        "can you see this",
        "look at this",
        "describe the camera view",
    )

    if any(phrase in normalised for phrase in read_phrases):
        return "read"

    if any(phrase in normalised for phrase in identify_phrases):
        return "identify"

    if any(phrase in normalised for phrase in describe_phrases):
        return "describe"

    return None

def capture_requested_camera_frame(
    hold_seconds: float = 0.0,
    on_progress=None,
):
    """Get one settled camera frame, optionally holding for a scan countdown."""
    from core.live_frame_buffer import live_frame_buffer
    from core.vision import (
        is_vision_requested,
        start_vision,
        stop_vision,
    )

    trace_id = performance.current_trace_id()
    owns_trace = trace_id is None

    if owns_trace:
        trace_id = performance.begin(
            "camera_frame_capture",
            metadata={
                "hold_target_seconds": hold_seconds,
            },
        )

    span_id = performance.begin_span(
        "camera_frame_capture",
        trace_id,
        metadata={
            "hold_target_seconds": hold_seconds,
        },
    )

    capture_started_at = time.perf_counter()
    hold_started_at = None
    outcome = "ok"

    vision_was_already_running = is_vision_requested()
    requested_at = time.monotonic()

    performance.add_metadata(
        {
            "camera_vision_already_running": vision_was_already_running,
        },
        trace_id,
    )

    if not vision_was_already_running:
        vision_start_started_at = time.perf_counter()

        print("📷 Starting Vision for one requested analysis frame.")
        start_vision()

        performance.record_stage(
            "camera_vision_start_request_seconds",
            time.perf_counter() - vision_start_started_at,
            trace_id,
        )

    try:
        fresh_frame_wait_started_at = time.perf_counter()

        first_frame = live_frame_buffer.wait_for_frame(
            timeout_seconds=6.0,
            newer_than=requested_at,
        )

        performance.record_stage(
            "camera_wait_for_fresh_frame_seconds",
            time.perf_counter() - fresh_frame_wait_started_at,
            trace_id,
        )

        if first_frame is None:
            outcome = "no_fresh_frame"
            return None

        performance.mark(
            "camera_first_fresh_frame_received",
            trace_id,
            only_once=True,
        )

        autofocus_started_at = time.perf_counter()

        # Let autofocus and exposure stabilise before capturing.
        time.sleep(0.45)

        performance.record_stage(
            "camera_autofocus_settle_seconds",
            time.perf_counter() - autofocus_started_at,
            trace_id,
        )

        if hold_seconds <= 0:
            settled_frame = live_frame_buffer.get_latest(
                max_age_seconds=1.0,
            )

            selected_frame = (
                settled_frame
                if settled_frame is not None
                else first_frame
            )

            height, width = selected_frame.shape[:2]

            performance.add_metric(
                "camera_captured_width",
                width,
                trace_id,
            )

            performance.add_metric(
                "camera_captured_height",
                height,
                trace_id,
            )

            performance.mark(
                "camera_frame_ready",
                trace_id,
                only_once=True,
            )

            return selected_frame

        hold_started_at = time.perf_counter()

        latest_frame = live_frame_buffer.get_latest(
            max_age_seconds=1.0,
        )

        if latest_frame is None:
            latest_frame = first_frame

        while True:
            elapsed = time.perf_counter() - hold_started_at
            progress = min(1.0, elapsed / hold_seconds)

            if on_progress is not None:
                on_progress(progress)

            current_frame = live_frame_buffer.get_latest(
                max_age_seconds=1.0,
            )

            if current_frame is not None:
                latest_frame = current_frame

            if progress >= 1.0:
                height, width = latest_frame.shape[:2]

                performance.add_metric(
                    "camera_captured_width",
                    width,
                    trace_id,
                )

                performance.add_metric(
                    "camera_captured_height",
                    height,
                    trace_id,
                )

                performance.mark(
                    "camera_frame_ready",
                    trace_id,
                    only_once=True,
                )

                return latest_frame

            time.sleep(0.04)

    except Exception:
        outcome = "capture_error"
        raise

    finally:
        if hold_started_at is not None:
            performance.record_stage(
                "camera_hold_seconds",
                time.perf_counter() - hold_started_at,
                trace_id,
            )

        performance.record_stage(
            "camera_total_capture_seconds",
            time.perf_counter() - capture_started_at,
            trace_id,
        )

        performance.finish_span(
            span_id,
            outcome=outcome,
        )

        if not vision_was_already_running:
            print("📷 One-frame capture complete. Stopping Vision.")
            stop_vision()

        if owns_trace:
            performance.finish(
                trace_id,
                outcome=outcome,
            )

def finalize_barge_listener(
    interrupt_thread,
):
    """Finish capture, classification, and runtime queuing."""

    # A triggered recorder must finish capturing even though
    # TTS has stopped. A non-triggered recorder should exit.
    shared_state["stop_interrupt_listener"] = True

    # It is now safe for Faster-Whisper to decode the captured
    # audio because the calling speech/generation stage is done.
    shared_state[
        "barge_in_allow_transcription"
    ] = True

    resolution = wait_for_barge_resolution(
        shared_state,
        interrupt_thread,
        timeout_seconds=12.0,
    )

    queue_barge_resolution(
        shared_state,
        resolution,
    )

    if interrupt_thread.is_alive():
        interrupt_thread.join(timeout=0.5)

    if resolution.has_action:
        print(
            "Barge-in runtime action: "
            f"action={resolution.action.value}, "
            f"intent={(
                resolution.intent.value
                if resolution.intent is not None
                else 'none'
            )}, "
            f"reason={resolution.reason}, "
            f"confidence={resolution.confidence:.2f}, "
            f"transcript={resolution.transcript!r}"
        )

    return resolution


def speak_with_barge(text, pause_text=None):
    global conversation_until

    from core.barge_in import (
        listen_for_speech_interrupt,
    )

    shared_state["interrupt"] = False
    shared_state["stop_interrupt_listener"] = False
    shared_state[
        "barge_in_allow_transcription"
    ] = False
    shared_state["state"] = "speaking"
    shared_state["current_spoken_text"] = text

    interrupt_thread = threading.Thread(
        target=listen_for_speech_interrupt,
        args=(shared_state,),
        daemon=True,
    )
    interrupt_thread.start()

    completed = speak(
        text,
        shared_state,
    )

    resolution = finalize_barge_listener(
        interrupt_thread
    )

    shared_state["current_spoken_text"] = ""

    if (
        completed is False
        or resolution.has_action
    ):
        print(
            "⚠️ Resumable speech paused by "
            "classified barge-in."
        )

        stored_remaining = shared_state.get(
            "paused_response",
            "",
        )

        if (
            isinstance(stored_remaining, str)
            and stored_remaining.strip()
        ):
            print(
                "⏸️ Precise paused response kept: "
                f"{stored_remaining.strip()}"
            )

        elif (
            isinstance(pause_text, str)
            and pause_text.strip()
        ):
            shared_state["paused_response"] = (
                pause_text.strip()
            )

            print(
                "⏸️ Fallback paused response kept: "
                f"{pause_text.strip()}"
            )

        conversation_until = (
            time.time() + CONVERSATION_TIMEOUT
        )
        return False

    return True

def avens_loop():
    global conversation_until

    from skills.reminder_delivery import (
        deliver_due_reminders,
    )
    from skills.reminder_scheduler import (
        reminder_scheduler,
    )

    try:
        if reminder_scheduler.start():
            print("⏰ Local reminder scheduler started.")
        speak("Avens is now online.")
        print("Loop running...")
        just_interrupted = False
        while True:
            due_reminders = reminder_scheduler.drain_deliveries()

            if due_reminders:
                shared_state["state"] = "speaking"

                deliver_due_reminders(
                    due_reminders,
                    announce=lambda message: speak(
                        message,
                        shared_state,
                        performance_label="reminder_alert",
                    ),
                )

                # Due reminders are unsolicited. Return to wake-word mode
                # instead of keeping any old conversation window alive.
                conversation_until = 0

                shared_state["state"] = "idle"
                continue

            previous_turn_trace_id = performance.current_trace_id()

            if previous_turn_trace_id is not None:
                performance.finish(
                    previous_turn_trace_id,
                    outcome="ok",
                )
            queued_barge = consume_queued_barge_action(
                shared_state
            )

            # Reset the raw trigger before beginning the next turn.
            shared_state["interrupt"] = False

            was_interrupted = just_interrupted
            just_interrupted = False

            captured_barge_input = (
                queued_barge.transcript
            )
            input_from_barge = bool(
                captured_barge_input
            )

            # Background speech, echo, acknowledgements, and unclear
            # audio resume automatically without another prompt.
            if queued_barge.auto_resume:
                paused_for_resume = str(
                    shared_state.get(
                        "paused_response",
                        "",
                    )
                ).strip()

                if paused_for_resume:
                    print(
                        "▶️ Automatically resuming after "
                        "non-directed barge-in."
                    )

                    completed = speak_with_barge(
                        paused_for_resume,
                        pause_text=paused_for_resume,
                    )

                    if completed:
                        shared_state[
                            "paused_response"
                        ] = ""
                        shared_state[
                            "current_spoken_text"
                        ] = ""
                    else:
                        just_interrupted = True

                conversation_until = (
                    time.time() + CONVERSATION_TIMEOUT
                )
                shared_state["state"] = "idle"
                continue

            started_in_active_window = (
                input_from_barge
                or was_interrupted
                or (
                    time.time()
                    <= conversation_until
                )
            )

            if input_from_barge:
                print(
                    "🎯 Processing directed barge-in: "
                    f"{captured_barge_input}"
                )

                # This first runtime version treats a directed
                # interruption as replacing the previous answer.
                if shared_state.get(
                    "paused_response"
                ):
                    print(
                        "🗑️ Directed interruption replaced "
                        "the previous paused response."
                    )

                shared_state["paused_response"] = ""
                shared_state[
                    "current_spoken_text"
                ] = ""
                shared_state["state"] = "listening"

                listen_silence_limit = 0.0
                listen_max_duration = 0.0

            else:
                # If no active session exists, require wake word.
                if not started_in_active_window:
                    shared_state["state"] = "listening"

                    wake_detected = listen_for_wake_word(
                        should_stop=(
                            reminder_scheduler
                            .has_queued_deliveries
                        ),
                    )

                    if not wake_detected:
                        if (
                            reminder_scheduler
                            .has_queued_deliveries()
                        ):
                            continue

                        shared_state["state"] = "idle"
                        time.sleep(0.25)
                        continue

                    conversation_until = (
                        time.time()
                        + CONVERSATION_TIMEOUT
                    )
                    started_in_active_window = True

                    shared_state["state"] = "speaking"
                    speak(
                        "Yes Sir?",
                        shared_state,
                    )

                    conversation_until = (
                        time.time()
                        + CONVERSATION_TIMEOUT
                    )

                else:
                    print(
                        "🟡 Follow-up window active. "
                        "Listening without wake word..."
                    )

                shared_state["state"] = "listening"

                if was_interrupted:
                    if shared_state.get(
                        "paused_response"
                    ):
                        paused_before_prompt = str(
                            shared_state[
                                "paused_response"
                            ]
                        ).strip()

                        shared_state[
                            "state"
                        ] = "speaking"
                        shared_state[
                            "interrupt"
                        ] = False

                        speak(
                            "Should I continue, sir?",
                            shared_state,
                            performance_label=(
                                "resume_prompt"
                            ),
                        )

                        shared_state[
                            "paused_response"
                        ] = paused_before_prompt
                        shared_state[
                            "interrupt"
                        ] = False
                        shared_state[
                            "stop_interrupt_listener"
                        ] = True

                    shared_state[
                        "state"
                    ] = "listening"
                    listen_silence_limit = 3.0
                    listen_max_duration = 20

                else:
                    listen_silence_limit = 1.5

                    remaining_follow_up_seconds = max(
                        1.0,
                        conversation_until
                        - time.time(),
                    )

                    listen_max_duration = min(
                        15.0,
                        remaining_follow_up_seconds,
                    )

            turn_trace_id = performance.begin(
                "voice_turn",
                metadata={
                    "follow_up_turn": (
                        started_in_active_window
                    ),
                    "after_interruption": (
                        was_interrupted
                    ),
                    "silence_limit_seconds": (
                        listen_silence_limit
                    ),
                    "input_source": (
                        "barge_in"
                        if input_from_barge
                        else "microphone"
                    ),
                },
            )

            if input_from_barge:
                user_input = captured_barge_input

                performance.mark(
                    "transcript_received",
                    turn_trace_id,
                    only_once=True,
                )

            else:
                performance.mark(
                    "turn_listen_requested",
                    turn_trace_id,
                    only_once=True,
                )

                user_input = listen(
                    silence_limit=(
                        listen_silence_limit
                    ),
                    max_duration=(
                        listen_max_duration
                    ),
                )

                performance.mark(
                    "transcript_received",
                    turn_trace_id,
                    only_once=True,
                )

            performance.add_prompt_metadata(
                user_input,
                turn_trace_id,
            )

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

            if (
                not input_from_barge
                and not is_probably_talking_to_avens(
                    user_input,
                    conversation_active=(
                        conversation_active
                    ),
                )
            ):
                print("🟠 Side conversation detected. Ignoring:", user_input)

                # Still keep the active window alive briefly after side-talk
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            # Valid user input extends the active conversation window
            conversation_until = time.time() + CONVERSATION_TIMEOUT

            lower_input = user_input.lower().strip()
            routing_started_at = time.perf_counter()

            performance.mark(
                "intent_routing_started",
                turn_trace_id,
                only_once=True,
            )
            paused_raw = shared_state.get("paused_response", "")

            if not isinstance(paused_raw, str):
                print(f"⚠️ Invalid paused_response type cleared: {type(paused_raw)}")
                shared_state["paused_response"] = ""
                paused = ""
            else:
                paused = paused_raw.strip()

            if paused and is_resume_request(lower_input):
                shared_state["state"] = "speaking"

                # Speak the bridge separately so it never becomes part
                # of the resumable response text.
                speak(
                    "As I was saying.",
                    shared_state,
                    performance_label="resume_bridge",
                )

                # The preserved content must contain only the answer,
                # never the presentation bridge above.
                shared_state["paused_response"] = paused
                shared_state["interrupt"] = False

                completed = speak_with_barge(
                    paused,
                    pause_text=paused,
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
            # RUNTIME MODE CONTROLLER
            # ---------------------------------------------
            from core.mode_controller import mode_controller

            mode_state = mode_controller.snapshot()

            if mode_state.pending_choice != "none":
                cancel_phrases = {
                    "cancel",
                    "cancel that",
                    "never mind",
                    "forget it",
                    "not now",
                }

                if lower_input in cancel_phrases:
                    mode_controller.cancel_pending_change()

                    shared_state["state"] = "speaking"
                    speak(
                        "Mode change cancelled. Staying with the current configuration, sir.",
                        shared_state,
                    )

                    conversation_until = time.time() + CONVERSATION_TIMEOUT
                    shared_state["state"] = "idle"
                    continue

                if mode_state.pending_choice == "choose_scope":
                    scope = get_mode_scope_choice(lower_input)

                    if scope is None:
                        shared_state["state"] = "speaking"
                        speak(
                            "Choose brain, camera, or both, sir.",
                            shared_state,
                        )

                        conversation_until = (
                            time.time() + CONVERSATION_TIMEOUT
                        )
                        shared_state["state"] = "idle"
                        continue

                    try:
                        needs_provider = mode_controller.choose_scope(scope)
                    except (RuntimeError, ValueError) as error:
                        print(f"⚠️ Mode scope error: {error}")

                        shared_state["state"] = "speaking"
                        speak(
                            "That mode change did not complete. Please try again, sir.",
                            shared_state,
                        )

                        conversation_until = (
                            time.time() + CONVERSATION_TIMEOUT
                        )
                        shared_state["state"] = "idle"
                        continue

                    if needs_provider:
                        shared_state["state"] = "speaking"
                        speak(
                            "For the online brain, choose GPT or Gemini, sir.",
                            shared_state,
                        )

                    else:
                        updated_state = mode_controller.snapshot()

                        shared_state["state"] = "speaking"
                        speak(
                            mode_controller.get_status_text(),
                            shared_state,
                        )

                    conversation_until = time.time() + CONVERSATION_TIMEOUT
                    shared_state["state"] = "idle"
                    continue

                if mode_state.pending_choice == "choose_provider":
                    provider = get_brain_provider_choice(lower_input)

                    if provider is None:
                        shared_state["state"] = "speaking"
                        speak(
                            "Choose GPT or Gemini for the online brain, sir.",
                            shared_state,
                        )

                        conversation_until = (
                            time.time() + CONVERSATION_TIMEOUT
                        )
                        shared_state["state"] = "idle"
                        continue

                    try:
                        mode_controller.choose_brain_provider(provider)
                    except (RuntimeError, ValueError) as error:
                        print(f"⚠️ Brain provider error: {error}")

                        shared_state["state"] = "speaking"
                        speak(
                            "That provider change did not complete. Please try again, sir.",
                            shared_state,
                        )

                        conversation_until = (
                            time.time() + CONVERSATION_TIMEOUT
                        )
                        shared_state["state"] = "idle"
                        continue

                    shared_state["state"] = "speaking"
                    speak(
                        mode_controller.get_status_text(),
                        shared_state,
                    )

                    conversation_until = time.time() + CONVERSATION_TIMEOUT
                    shared_state["state"] = "idle"
                    continue

            if is_mode_status_request(lower_input):
                shared_state["state"] = "speaking"
                speak(
                    mode_controller.get_status_text(),
                    shared_state,
                )

                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            target_mode = get_mode_change_target(lower_input)

            if target_mode is not None:
                mode_controller.begin_mode_change(target_mode)

                shared_state["state"] = "speaking"
                speak(
                    f"Which system should go {target_mode}: brain, camera, or both?",
                    shared_state,
                )

                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            local_time_reply = get_local_time_reply(lower_input)

            if local_time_reply is not None:
                print("⏰ Using local Windows clock.")

                performance.record_stage(
                    "intent_routing_seconds",
                    time.perf_counter() - routing_started_at,
                    turn_trace_id,
                )

                performance.mark(
                    "instant_time_route",
                    turn_trace_id,
                    only_once=True,
                )

                shared_state["state"] = "speaking"
                speak(
                    local_time_reply,
                    shared_state,
                    performance_label="local_time",
                )

                conversation_until = (
                    time.time() + CONVERSATION_TIMEOUT
                )
                shared_state["state"] = "idle"
                continue

            acknowledgement_reply = get_acknowledgement_reply(
                lower_input,
            )

            if acknowledgement_reply is not None:
                print("💬 Using local acknowledgement route.")

                performance.record_stage(
                    "intent_routing_seconds",
                    time.perf_counter() - routing_started_at,
                    turn_trace_id,
                )

                performance.mark(
                    "instant_acknowledgement_route",
                    turn_trace_id,
                    only_once=True,
                )

                shared_state["state"] = "speaking"
                speak(
                    acknowledgement_reply,
                    shared_state,
                    performance_label="acknowledgement",
                )

                # A brief window is enough after “yeah” or “thanks.”
                conversation_until = time.time() + 4
                shared_state["state"] = "idle"
                continue

            # ---------------------------------------------
            # DETERMINISTIC LOCAL SKILLS
            # ---------------------------------------------
            from skills.router import route_local_skill

            local_skill_result = route_local_skill(user_input)

            if (
                local_skill_result is not None
                and local_skill_result.handled
            ):
                print(
                    "🧩 Deterministic local skill handled: "
                    f"{local_skill_result.skill_name}"
                )

                performance.record_stage(
                    "intent_routing_seconds",
                    time.perf_counter() - routing_started_at,
                    turn_trace_id,
                )

                performance.mark(
                    "local_skill_route",
                    turn_trace_id,
                    only_once=True,
                )

                shared_state["state"] = "speaking"
                speak(
                    local_skill_result.message,
                    shared_state,
                    performance_label=(
                        f"skill_{local_skill_result.skill_name}"
                    ),
                )

                conversation_until = (
                    time.time() + CONVERSATION_TIMEOUT
                )
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

            camera_request = get_camera_intelligence_request(lower_input)
            camera_mode = mode_controller.snapshot().camera_mode

            use_local_camera = (
                camera_request in {"describe", "read"}
                or (
                    camera_request == "identify"
                    and camera_mode == "offline"
                )
            )

            if use_local_camera:
                from core.camera_intelligence import analyze_camera_frame
                from core.vision import (
                    clear_latest_vision_result,
                    is_vision_requested,
                    set_latest_vision_result,
                    set_vision_scan_state,
                    start_vision,
                    stop_vision,
                )

                scan_label = {
                    "identify": "LOCAL IDENTIFY",
                    "describe": "LOCAL DESCRIBE",
                    "read": "LOCAL READ",
                }[camera_request]

                frame = None
                vision_was_running = is_vision_requested()
                started_vision_for_local_scan = False

                try:
                    clear_latest_vision_result()

                    if not vision_was_running:
                        start_vision()
                        started_vision_for_local_scan = True

                    set_vision_scan_state(f"{scan_label}: READY")

                    shared_state["state"] = "speaking"
                    speak(
                        "Center it in the yellow box and hold still.",
                        shared_state,
                        performance_label="camera_instruction",
                    )

                    def update_local_capture_progress(
                        progress: float,
                    ) -> None:
                        set_vision_scan_state(
                            f"{scan_label}: HOLD STILL",
                            progress,
                        )

                    set_vision_scan_state(
                        f"{scan_label}: HOLD STILL",
                        0.0,
                    )

                    shared_state["state"] = "thinking"
                    frame = capture_requested_camera_frame(
                        hold_seconds=LENS_CAPTURE_HOLD_SECONDS,
                        on_progress=update_local_capture_progress,
                    )

                    if frame is None:
                        raise RuntimeError(
                            "I could not capture a fresh camera frame in time."
                        )

                    set_vision_scan_state(
                        f"{scan_label}: CAPTURED",
                        1.0,
                    )

                    time.sleep(0.65)

                    set_vision_scan_state(
                        f"{scan_label}: ANALYZING OFFLINE",
                    )

                    print(
                        "🔒 Running local camera analysis "
                        f"({camera_request})."
                    )

                    answer = str(
                        analyze_camera_frame(
                            frame,
                            camera_request,
                        )
                    ).strip()

                    if not answer:
                        raise RuntimeError(
                            "The local vision model returned no answer."
                        )

                    set_latest_vision_result(
                        kind=f"local_{camera_request}",
                        text=answer,
                    )

                    shared_state["state"] = "speaking"
                    speak(
                        answer,
                        shared_state,
                        performance_label="camera_result",
                    )
                except Exception as error:
                    print(f"⚠️ Local camera analysis error: {error}")

                    shared_state["state"] = "speaking"
                    speak(
                        "Local camera analysis failed. "
                        "Make sure Ollama is running, sir.",
                        shared_state,
                        performance_label="camera_error",
                    )

                finally:
                    frame = None
                    set_vision_scan_state("")

                    if started_vision_for_local_scan:
                        stop_vision()

                    conversation_until = (
                        time.time() + CONVERSATION_TIMEOUT
                    )
                    shared_state["state"] = "idle"

                continue

            if (
                camera_mode == "online"
                and (
                    camera_request == "identify"
                    or is_lens_scan_request(lower_input)
                )
            ):
                from core.lens_scan import (
                    LensScanError,
                    format_lens_match_for_speech,
                    scan_frame_with_google_lens,
                )
                from core.vision import (
                    clear_latest_vision_result,
                    is_vision_requested,
                    set_latest_vision_result,
                    set_vision_scan_state,
                    start_vision,
                    stop_vision,
                )

                frame = None
                vision_was_running = is_vision_requested()
                started_vision_for_lens = False

                try:
                    clear_latest_vision_result()

                    # Start Vision before speaking so the yellow scan box is visible.
                    if not vision_was_running:
                        start_vision()
                        started_vision_for_lens = True

                    set_vision_scan_state("LENS SCAN: READY")

                    shared_state["state"] = "speaking"
                    speak(
                        "Center it in the yellow box and hold still.",
                        shared_state,
                        performance_label="lens_error",
                    )

                    def update_lens_capture_progress(progress: float) -> None:
                        set_vision_scan_state(
                            "LENS SCAN: HOLD STILL",
                            progress,
                        )

                    set_vision_scan_state(
                        "LENS SCAN: HOLD STILL",
                        0.0,
                    )

                    shared_state["state"] = "thinking"
                    frame = capture_requested_camera_frame(
                        hold_seconds=LENS_CAPTURE_HOLD_SECONDS,
                        on_progress=update_lens_capture_progress,
                    )

                    if frame is None:
                        raise LensScanError(
                            "I could not capture a fresh camera frame in time."
                        )

                    set_vision_scan_state(
                        "CAPTURED - YOU CAN LOWER IT",
                        1.0,
                    )

                    time.sleep(0.65)

                    set_vision_scan_state("LENS SCAN: SEARCHING ONLINE")

                    print("🔎 Running one online Google Lens search.")
                    match = scan_frame_with_google_lens(frame)

                    set_latest_vision_result(
                        kind="online_google_lens",
                        text=match.title,
                        detail=match.source,
                    )

                    shared_state["state"] = "speaking"
                    speak(
                        format_lens_match_for_speech(match),
                        shared_state,
                        performance_label="lens_error",
                    )

                except LensScanError as error:
                    print(f"⚠️ Lens Scan error: {error}")

                    shared_state["state"] = "speaking"
                    speak(
                        f"Online Lens Scan failed. {error}",
                        shared_state,
                    )

                except Exception as error:
                    print(f"⚠️ Unexpected Lens Scan error: {error}")

                    shared_state["state"] = "speaking"
                    speak(
                        "The online Lens Scan failed unexpectedly, sir.",
                        shared_state,
                    )

                finally:
                    frame = None
                    set_vision_scan_state("")

                    if started_vision_for_lens:
                        stop_vision()

                    conversation_until = time.time() + CONVERSATION_TIMEOUT
                    shared_state["state"] = "idle"

                continue

            elif is_minimal_vision_request(lower_input):
                from core.vision import set_vision_hud_mode

                set_vision_hud_mode("MINIMAL")

                shared_state["state"] = "speaking"
                speak("Cleaning up the camera feed, sir.", shared_state)
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            elif is_standard_vision_request(lower_input):
                from core.vision import set_vision_hud_mode

                set_vision_hud_mode("STANDARD")

                shared_state["state"] = "speaking"
                speak("Bringing the full camera interface back, sir.", shared_state)
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            elif any(
                phrase in lower_input
                for phrase in [
                    "hide gesture guide",
                    "hide the gesture guide",
                    "hide vision guide",
                    "remove gesture guide",
                ]
            ):
                from core.vision import set_vision_guide_visible

                set_vision_guide_visible(False)

                shared_state["state"] = "speaking"
                speak("Gesture guide hidden, sir.", shared_state)
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            elif any(
                phrase in lower_input
                for phrase in [
                    "show gesture guide",
                    "show the gesture guide",
                    "show vision guide",
                ]
            ):
                from core.vision import set_vision_guide_visible

                set_vision_guide_visible(True)

                shared_state["state"] = "speaking"
                speak("Gesture guide restored, sir.", shared_state)
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            elif any(
                phrase in lower_input
                for phrase in [
                    "full screen camera",
                    "fullscreen camera",
                    "full screen webcam",
                    "fullscreen webcam",
                    "full screen vision",
                    "fullscreen vision",
                    "maximize vision",
                    "maximize camera",
                    "expand camera",
                ]
            ):
                from core.vision import request_vision_fullscreen

                request_vision_fullscreen()

                shared_state["state"] = "speaking"
                speak(
                    "Expanding the camera feed. The orb is stepping aside, sir.",
                    shared_state,
                )
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

            elif any(
                phrase in lower_input
                for phrase in [
                    "normal vision",
                    "normal camera",
                    "restore vision",
                    "restore camera",
                    "exit full screen",
                    "exit fullscreen",
                    "leave full screen",
                    "leave fullscreen",
                    "shrink camera",
                    "back to normal",
                    "back to normal please",
                ]
            ):
                from core.vision import restore_vision_layout

                restore_vision_layout()

                shared_state["state"] = "speaking"
                speak(
                    "Restoring the normal vision layout, sir.",
                    shared_state,
                )
                conversation_until = time.time() + CONVERSATION_TIMEOUT
                shared_state["state"] = "idle"
                continue

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
            search_match = re.fullmatch(
                r"\s*"
                r"(?:(?:can|could|would|will)\s+you\s+)?"
                r"(?:please\s+)?"
                r"(?:search(?:\s+for)?|google|look\s+up)\s+"
                r"(?P<query>.+?)"
                r"\s*[.!?]*\s*",
                lower_input,
            )
            if search_match:
                query = search_match.group("query").strip()
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

            performance.record_stage(
                "intent_routing_seconds",
                time.perf_counter() - routing_started_at,
                turn_trace_id,
            )

            performance.mark(
                "brain_dispatch_started",
                turn_trace_id,
                only_once=True,
            )
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

            response_session = StreamedResponseSession()

            # A new brain response must not inherit an older paused answer.
            shared_state["paused_response"] = ""
            shared_state["current_spoken_text"] = ""

            brain_stream = get_response(user_input)

            # Catch sentences and tool tags from brain.py on the fly.
            for item_type, content in brain_stream:
                if (
                    shared_state.get("interrupt")
                    and not response_session.interrupted
                ):
                    precise_remaining = shared_state.get(
                        "paused_response",
                        "",
                    )

                    if (
                        response_session.current_segment
                        is not None
                    ):
                        response_session.mark_current_interrupted(
                            precise_remaining
                        )
                    else:
                        response_session.mark_interrupted()

                    print(
                        "⚠️ Streamed response interrupted. "
                        "Draining remaining text safely."
                    )
                    just_interrupted = True
                    conversation_until = (
                        time.time() + CONVERSATION_TIMEOUT
                    )

                # --- CASE 1: HANDLE SYSTEM COMMAND TAGS ---
                if item_type == "tag":
                    raw_tag = content.strip()

                    if (
                        not response_session
                        .can_execute_generated_actions
                    ):
                        print(
                            "🚫 Generated tool tag discarded "
                            "after response interruption: "
                            f"{raw_tag}"
                        )
                        blocked_tool_tag_seen = True
                        continue

                    # Extract complete command tags only,
                    # such as <CMD: HIDE>.
                    tags = re.findall(
                        r"<[^<>]+>",
                        raw_tag,
                    )

                    if not tags:
                        print(
                            f"⚠️ Ignoring malformed tag: {raw_tag}"
                        )
                        continue

                    for fixed_tag in tags:
                        if not is_tool_allowed_for_prompt(
                            fixed_tag,
                            user_input,
                        ):
                            print(
                                "🚫 Blocked hallucinated tool tag: "
                                f"{fixed_tag}"
                            )
                            blocked_tool_tag_seen = True
                            continue

                        print(
                            f"⚙️ EXECUTING LIVE TAG: {fixed_tag}"
                        )

                        action_result = execute_command(
                            fixed_tag,
                            shared_state,
                        )

                        if not action_result:
                            continue

                        shared_state["state"] = "speaking"

                        if (
                            "time" in fixed_tag.lower()
                            and not any(
                                word in fixed_tag.lower()
                                for word in (
                                    "timer",
                                    "delay",
                                    "wait",
                                )
                            )
                        ):
                            speak(
                                action_result,
                                shared_state,
                            )

                        elif any(
                            tag_type in fixed_tag
                            for tag_type in (
                                "<RESEARCH",
                                "<FINANCE",
                                "<FETCH",
                                "<RUN",
                            )
                        ):
                            speak(
                                "Let me check the live data, sir. "
                                f"{action_result}",
                                shared_state,
                            )

                        else:
                            speak(
                                action_result,
                                shared_state,
                            )

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
                        response_session.append_text(
                            clean_sentence
                        )

                        # After interruption, retain later generated text
                        # without speaking it.
                        if response_session.interrupted:
                            continue

                        active_segment = (
                            response_session
                            .begin_next_segment()
                        )

                        if active_segment is None:
                            continue

                        shared_state["state"] = "speaking"
                        shared_state["current_spoken_text"] = (
                            active_segment
                        )

                        completed = speak(
                            active_segment,
                            shared_state,
                            performance_label="brain_response",
                        )

                        if (
                            completed is False
                            or shared_state.get("interrupt")
                        ):
                            precise_remaining = (
                                shared_state.get(
                                    "paused_response",
                                    "",
                                )
                            )

                            response_session.mark_current_interrupted(
                                precise_remaining
                            )

                            shared_state["paused_response"] = (
                                response_session.remaining_text
                            )

                            print(
                                "⏸️ Initial streamed remainder: "
                                f"{response_session.remaining_text}"
                            )

                            just_interrupted = True
                            conversation_until = (
                                time.time()
                                + CONVERSATION_TIMEOUT
                            )
                            shared_state[
                                "current_spoken_text"
                            ] = ""
                            shared_state["state"] = "thinking"

                            # Continue draining later brain events.
                            continue

                        response_session.mark_current_complete()

                        shared_state[
                            "current_spoken_text"
                        ] = ""
                        shared_state["state"] = "thinking"
                        has_spoken_anything = True

            if (
                shared_state.get("interrupt")
                and not response_session.interrupted
            ):
                response_session.mark_interrupted()
                just_interrupted = True
                conversation_until = (
                    time.time() + CONVERSATION_TIMEOUT
                )

            response_session.mark_generation_complete()

            if response_session.interrupted:
                final_remaining = (
                    response_session.remaining_text.strip()
                )

                shared_state["paused_response"] = (
                    final_remaining
                )
                shared_state["current_spoken_text"] = ""

                print(
                    "⏸️ Final streamed response remainder: "
                    f"{final_remaining or '[empty]'}"
                )

            resolution = finalize_barge_listener(
                interrupt_thread
            )

            if resolution.has_action:
                just_interrupted = True
                conversation_until = (
                    time.time()
                    + CONVERSATION_TIMEOUT
                )

            # Fallback if the generator produced no usable output.
            if (
                not has_spoken_anything
                and not just_interrupted
            ):
                shared_state["state"] = "speaking"

                if blocked_tool_tag_seen:
                    speak(
                        "I misread that as a command, sir. "
                        "Please ask it again normally.",
                        shared_state,
                    )
                else:
                    speak(
                        "I did not generate a usable response, sir.",
                        shared_state,
                    )

            if just_interrupted:
                time.sleep(0.5)
                continue

            conversation_until = (
                time.time() + CONVERSATION_TIMEOUT
            )
            shared_state["state"] = "idle"
    except Exception as e:
        print("🔥 THREAD CRASHED:", e)
        import traceback
        traceback.print_exc()
    finally:
        reminder_scheduler.stop()

def main():
    boot_trace_id = performance.begin(
        "app_boot",
        metadata={
            "boundary": "module_import_to_ui_shown",
        },
    )

    performance.record_stage(
        "boot_module_import_to_main_seconds",
        time.perf_counter() - APP_PROCESS_STARTED_AT,
        boot_trace_id,
    )

    print("Starting Avens...")

    stt_init_started_at = time.perf_counter()

    # Initialize Faster-Whisper before Kokoro, Vosk, ChromaDB, PyQt, etc.
    init_model()

    performance.record_stage(
        "boot_stt_model_init_seconds",
        time.perf_counter() - stt_init_started_at,
        boot_trace_id,
    )

    runtime_modules_started_at = time.perf_counter()

    # Now load the rest of the runtime modules.
    load_runtime_modules(boot_trace_id)

    performance.record_stage(
        "boot_runtime_modules_seconds",
        time.perf_counter() - runtime_modules_started_at,
        boot_trace_id,
    )

    loop_thread_started_at = time.perf_counter()

    loop_thread = threading.Thread(
        target=avens_loop,
        daemon=True,
    )

    loop_thread.start()

    performance.record_stage(
        "boot_loop_thread_start_seconds",
        time.perf_counter() - loop_thread_started_at,
        boot_trace_id,
    )

    performance.mark(
        "boot_loop_thread_started",
        boot_trace_id,
        only_once=True,
    )

    print("Launching UI...")
    run_ui(shared_state, boot_trace_id)

if __name__ == "__main__":
    main()