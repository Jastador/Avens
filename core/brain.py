from __future__ import annotations

import json
import os

import requests
from dotenv import load_dotenv

from config import OLLAMA_MODEL, USE_ONLINE_AI
from core.memory import load_memory
from core.profile import load_user_profile
from utils.internet_check import is_internet_available


load_dotenv()

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
MAX_HISTORY_MESSAGES = 10


def get_system_prompt(dynamic_memories: str = "") -> str:
    user_profile = load_user_profile()

    return f"""You are Avens, a local desktop AI assistant.
Your personality is a subtle mix of TARS from Interstellar and JARVIS.

--- LOCAL USER PROFILE ---
{user_profile}

--- RELEVANT PAST CONTEXTUAL MEMORIES ---
{dynamic_memories}

PERSONALITY RULES:
- Be direct first. Use occasional dry wit, not constant roasting.
- Keep answers concise unless detail is genuinely useful.
- Never pretend to know something you do not know.

COMMAND RULES:
- Output tags only when PC interaction is actually required.
- Answer normally when a question does not need an action.
- Never use TRANSLATE, EXPLAIN, or CALCULATE tags unless the action is explicitly requested and needed.
- Never add extra parameters, server names, or invented syntax to tags.
- For multiple requested actions, output separate tags.
- For ordinary conversation, questions about Avens, user profile, preferences, hobbies, identity, or free-time questions, reply in plain text.
- Never research user preferences, profile information, identity, hobbies, or free-time questions.
- Remember, save, note, and learn requests are handled directly by the app. Never output MEMORY, REMEMBER, SAVE, or LEARN tags.
- Never use wrappers such as <PLAIN_TEXT: ...>. Write normal text directly.
- Never output a tool tag as the only response to a conversational question.

Available Tags:
<RESEARCH: Query>
<REMIND: Seconds | Task>
<OPEN: AppName>
<MACRO: JOIN_ILLUMINATI_VC>
<SEARCH: Query>
<PLAY: Song or Video>
<TRANSLATE: Lang | Text>
<EXPLAIN: Concept>
<CALCULATE: Math>
<CMD: SET_VOL | 50>
<CMD: SET_BRIGHT | 50>
<CMD: READING_MODE>
<CMD: ANALYZE_SCREEN>
<CMD: TIME>
<CMD: MUTE>
<CMD: SILENCE_NOTIFS>
<CMD: VISION_ON>
<CMD: VISION_OFF>

Examples:
User: How is the market looking?
Avens: Volatile, sir. I will pull current information. <RESEARCH: stock market India>

User: Can you see me?
Avens: Activating optical sensors, sir. <CMD: VISION_ON>

User: Stop looking at me.
Avens: Deactivating optical sensors, sir. <CMD: VISION_OFF>
"""


chat_history = [
    {"role": "system", "content": get_system_prompt()}
]


def manage_memory(role: str, text: str) -> None:
    """Store recent conversation while keeping the system prompt intact."""
    chat_history.append({"role": role, "content": text})

    while len(chat_history) > MAX_HISTORY_MESSAGES + 1:
        chat_history.pop(1)


def online_ai(prompt: str):
    """Use OpenAI only when explicitly enabled and configured."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OpenAI key is unavailable, switching to local Ollama.")
        yield from offline_ai(prompt)
        return

    try:
        from openai import OpenAI

        chat_history[0]["content"] = get_system_prompt()
        manage_memory("user", prompt)

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=chat_history,
        )

        reply = response.choices[0].message.content or ""
        manage_memory("assistant", reply)
        yield ("text", reply)

    except Exception as error:
        print(f"⚠️ Online AI failed ({error}), switching to local Ollama.")

        if chat_history and chat_history[-1].get("role") == "user":
            chat_history.pop()

        yield from offline_ai(prompt)


def offline_ai(prompt: str):
    """Stream a response from the local Ollama model."""
    print(f"🧠 Contacting local Ollama ({OLLAMA_MODEL})...")

    past_context = load_memory(current_query=prompt)
    chat_history[0]["content"] = get_system_prompt(past_context)
    manage_memory("user", prompt)

    payload = {
        "model": OLLAMA_MODEL,
        "keep_alive": -1,
        "messages": chat_history,
        "stream": True,
        "options": {
            "num_ctx": 2048,
            "temperature": 0.3,
            "top_p": 0.9,
        },
    }

    full_reply = ""
    text_buffer = ""
    tag_buffer = ""
    in_tag = False

    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json=payload,
            stream=True,
            timeout=(5, 180),
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue

            try:
                chunk = json.loads(line).get("message", {}).get("content", "")
            except json.JSONDecodeError:
                continue

            full_reply += chunk

            for character in chunk:
                if character == "<" and not in_tag:
                    in_tag = True
                    tag_buffer = "<"

                    if text_buffer.strip():
                        yield ("text", text_buffer.strip())
                        text_buffer = ""

                elif in_tag:
                    tag_buffer += character

                    if character == ">":
                        in_tag = False
                        yield ("tag", tag_buffer)
                        tag_buffer = ""

                else:
                    text_buffer += character

                    if character in ".!?":
                        if text_buffer.strip():
                            yield ("text", text_buffer.strip())
                        text_buffer = ""

        if in_tag and tag_buffer:
            text_buffer += tag_buffer

        if text_buffer.strip():
            yield ("text", text_buffer.strip())

        manage_memory("assistant", full_reply)

    except requests.RequestException as error:
        print(f"⚠️ Ollama connection error: {error}")
        yield ("text", "My local brain is unavailable, sir. Check that Ollama is running.")

    except Exception as error:
        print(f"⚠️ Brain error: {error}")
        yield ("text", "My local brain is struggling, sir.")


def get_response(prompt: str):
    """Choose online mode only when enabled and internet is available."""
    if USE_ONLINE_AI and is_internet_available():
        print("🌐 Using Online AI")
        return online_ai(prompt)

    print("📴 Using Offline AI")
    return offline_ai(prompt)
