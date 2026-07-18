from __future__ import annotations

import json
import os
import time

import requests
from dotenv import load_dotenv

from config import OLLAMA_MODEL
from core.generation_cancel import (
    GenerationCancellationToken,
)
from core.memory import load_memory
from core.mode_controller import mode_controller
from core.profile import load_user_profile
from core.performance import performance


load_dotenv()

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"

MAX_HISTORY_MESSAGES = 10
LOCAL_BRAIN_KEEP_ALIVE = (
    os.getenv("AVENS_LOCAL_BRAIN_KEEP_ALIVE", "5m").strip()
    or "5m"
)

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


def _env_flag(name: str, default: bool = False) -> bool:
    """Read one true/false environment setting safely."""
    default_text = "true" if default else "false"

    return os.getenv(name, default_text).strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def is_online_context_sharing_enabled() -> bool:
    """Return whether profile, memories, and prior chat may leave the laptop."""
    return _env_flag("AVENS_SHARE_LOCAL_CONTEXT_ONLINE", default=False)


def get_system_prompt(
    dynamic_memories: str = "",
    include_private_context: bool = True,
) -> str:
    """Build Avens instructions for either local or remote providers."""
    if include_private_context:
        user_profile = load_user_profile()
        memories = dynamic_memories or "No relevant memories found."
    else:
        user_profile = (
            "Not shared with online providers. "
            "Answer without assuming private user details."
        )
        memories = (
            "Not shared with online providers. "
            "Use only the current conversation."
        )

    return f"""You are Avens, a desktop AI assistant.
Your personality is a subtle mix of TARS from Interstellar and JARVIS.

--- USER PROFILE ---
{user_profile}

--- RELEVANT CONTEXTUAL MEMORIES ---
{memories}

PERSONALITY RULES:
- Be direct first. Use occasional dry wit, not constant roasting.
- Keep answers concise unless detail is genuinely useful.
- Never pretend to know something you do not know.

COMMAND RULES:
- Output tags only when PC interaction is actually required.
- App launching and supported system controls are handled by deterministic local skills before this brain runs. Never output OPEN, LAUNCH, START, APP, volume, brightness, mute, reading-setup, or Night Light tags.
- Answer normally when a question does not need an action.
- Never use TRANSLATE, EXPLAIN, CALCULATE, TIME, MEMORY, REMEMBER, SAVE, or LEARN tags.
- Explain, calculate, translate, and answer ordinary questions using plain text.
- A request to explain something is always a plain-text response, never a tag.
- Never add extra parameters, server names, or invented syntax to tags.
- For multiple requested actions, output separate tags.
- For ordinary conversation, questions about Avens, user profile, preferences, hobbies, identity, or free-time questions, reply in plain text.
- Never research user preferences, profile information, identity, hobbies, or free-time questions.
- Remember, save, note, and learn requests are handled directly by the app. Never output MEMORY, REMEMBER, SAVE, or LEARN tags.
- Never use wrappers such as <PLAIN_TEXT: ...>. Write normal text directly.
- Never output a tool tag as the only response to a conversational question.

Available Tags:
<RESEARCH: Query>
<SEARCH: Query>
<PLAY: Song or Video>
<CMD: ANALYZE_SCREEN>
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
    {
        "role": "system",
        "content": get_system_prompt(),
    }
]


def manage_memory(role: str, text: str) -> None:
    """Store recent conversation while keeping the system prompt intact."""
    chat_history.append(
        {
            "role": role,
            "content": text,
        }
    )

    while len(chat_history) > MAX_HISTORY_MESSAGES + 1:
        chat_history.pop(1)


def _remove_last_user_turn(prompt: str) -> None:
    """Undo a failed online turn before falling back to local Ollama."""
    if not chat_history:
        return

    last_item = chat_history[-1]

    if (
        last_item.get("role") == "user"
        and last_item.get("content") == prompt
    ):
        chat_history.pop()


def _history_without_system() -> list[dict[str, str]]:
    """Return clean user/assistant history for cloud providers."""
    messages: list[dict[str, str]] = []

    for item in chat_history[1:]:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()

        if role not in {"user", "assistant"} or not content:
            continue

        messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    return messages


def _prepare_online_turn(
    prompt: str,
) -> tuple[str, list[dict[str, str]]]:
    """Build one remote request while respecting privacy settings."""
    share_context = is_online_context_sharing_enabled()

    dynamic_memories = (
        load_memory(current_query=prompt)
        if share_context
        else ""
    )

    system_prompt = get_system_prompt(
        dynamic_memories,
        include_private_context=share_context,
    )

    manage_memory("user", prompt)

    if not share_context:
        return (
            system_prompt,
            [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

    return system_prompt, _history_without_system()


def _format_gemini_input(
    messages: list[dict[str, str]],
) -> str:
    """Convert local history into a plain transcript for Gemini."""
    lines = [
        "Conversation transcript:",
    ]

    for message in messages:
        speaker = (
            "USER"
            if message["role"] == "user"
            else "AVENS"
        )

        lines.append(f"{speaker}: {message['content']}")

    return "\n\n".join(lines)


def _yield_complete_reply(reply: str):
    """Split a completed cloud reply into text and command-tag events."""
    text_buffer = ""
    tag_buffer = ""
    in_tag = False

    for character in reply:
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


def _generation_is_cancelled(
    cancellation_token: (
        GenerationCancellationToken | None
    ),
) -> bool:
    """Return whether the current brain generation was cancelled."""

    return (
        cancellation_token is not None
        and cancellation_token.is_cancelled
    )

def _iter_cancellable_lines(
    response,
    cancellation_token: (
        GenerationCancellationToken | None
    ) = None,
):
    """Yield Ollama response lines until cancellation is requested."""

    for line in response.iter_lines():
        if _generation_is_cancelled(
            cancellation_token
        ):
            return

        yield line

def _fallback_to_local(
    prompt: str,
    reason: str,
):
    """Explain remote failure briefly, then return to the local brain."""
    print(f"⚠️ Online brain fallback: {reason}")

    _remove_last_user_turn(prompt)

    yield (
        "text",
        "The online brain is unavailable. Returning to local processing, sir.",
    )

    yield from offline_ai(prompt)


def gpt_ai(prompt: str):
    """Use OpenAI only after an explicit online GPT mode selection."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        yield (
            "text",
            "GPT mode is selected, but the OpenAI API key is missing. "
            "Returning to local processing, sir.",
        )
        yield from offline_ai(prompt)
        return

    try:
        from openai import OpenAI

        system_prompt, messages = _prepare_online_turn(prompt)

        model_name = (
            os.getenv(
                "AVENS_OPENAI_MODEL",
                DEFAULT_OPENAI_MODEL,
            ).strip()
            or DEFAULT_OPENAI_MODEL
        )

        print(f"🌐 Using GPT brain ({model_name})...")

        client = OpenAI(api_key=api_key)

        response = client.responses.create(
            model=model_name,
            instructions=system_prompt,
            input=messages,
            max_output_tokens=500,
            store=False,
        )

        reply = str(response.output_text or "").strip()

        if not reply:
            raise RuntimeError("GPT returned an empty response.")

        manage_memory("assistant", reply)

        yield from _yield_complete_reply(reply)

    except Exception as error:
        yield from _fallback_to_local(prompt, str(error))


def gemini_ai(prompt: str):
    """Use Gemini only after an explicit online Gemini mode selection."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        yield (
            "text",
            "Gemini mode is selected, but the Gemini API key is missing. "
            "Returning to local processing, sir.",
        )
        yield from offline_ai(prompt)
        return

    try:
        from google import genai

        system_prompt, messages = _prepare_online_turn(prompt)

        model_name = (
            os.getenv(
                "AVENS_GEMINI_MODEL",
                DEFAULT_GEMINI_MODEL,
            ).strip()
            or DEFAULT_GEMINI_MODEL
        )

        print(f"🌐 Using Gemini brain ({model_name})...")

        client = genai.Client(api_key=api_key)

        interaction = client.interactions.create(
            model=model_name,
            system_instruction=system_prompt,
            input=_format_gemini_input(messages),
            generation_config={
                "temperature": 0.3,
                "thinking_level": "low",
            },
            store=False,
        )

        reply = str(interaction.output_text or "").strip()

        if not reply:
            raise RuntimeError("Gemini returned an empty response.")

        manage_memory("assistant", reply)

        yield from _yield_complete_reply(reply)

    except Exception as error:
        yield from _fallback_to_local(prompt, str(error))


def offline_ai(
    prompt: str,
    *,
    cancellation_token: (
        GenerationCancellationToken | None
    ) = None,
):
    """Stream a cancellable response from local Ollama."""
    trace_id = performance.current_trace_id()
    owns_trace = trace_id is None

    if owns_trace:
        trace_id = performance.begin(
            "brain_response",
            metadata={
                "provider": "local_ollama",
                "model": OLLAMA_MODEL,
            },
        )

    span_id = performance.begin_span(
        "brain_local_ollama",
        trace_id,
        metadata={
            "model": OLLAMA_MODEL,
            "keep_alive": LOCAL_BRAIN_KEEP_ALIVE,
        },
    )

    outcome = "ok"
    request_started_at = None
    response = None
    full_reply = ""
    text_buffer = ""
    tag_buffer = ""
    in_tag = False
    first_token_seen = False
    first_text_event_seen = False

    def record_first_text_event(text: str) -> None:
        """Record when the first real spoken text becomes available."""
        nonlocal first_text_event_seen

        clean_text = text.strip()

        if first_text_event_seen or not clean_text:
            return

        first_text_event_seen = True

        performance.mark(
            "brain_first_text_event",
            trace_id,
            only_once=True,
        )

        if request_started_at is not None:
            performance.record_stage(
                "brain_time_to_first_text_event_seconds",
                time.perf_counter() - request_started_at,
                trace_id,
            )

        performance.add_metric(
            "brain_first_text_characters",
            len(clean_text),
            trace_id,
        )

    try:
        if _generation_is_cancelled(
            cancellation_token
        ):
            outcome = "cancelled"
            return
        print(f"🧠 Using local brain ({OLLAMA_MODEL})...")

        performance.mark(
            "brain_started",
            trace_id,
            only_once=True,
        )

        memory_started_at = time.perf_counter()

        past_context = load_memory(current_query=prompt)

        performance.record_stage(
            "brain_memory_lookup_seconds",
            time.perf_counter() - memory_started_at,
            trace_id,
        )

        prompt_started_at = time.perf_counter()

        chat_history[0]["content"] = get_system_prompt(
            past_context,
            include_private_context=True,
        )

        manage_memory("user", prompt)

        performance.record_stage(
            "brain_prompt_build_seconds",
            time.perf_counter() - prompt_started_at,
            trace_id,
        )

        performance.add_metadata(
            {
                "brain_provider": "local_ollama",
                "brain_model": OLLAMA_MODEL,
                "brain_keep_alive": LOCAL_BRAIN_KEEP_ALIVE,
            },
            trace_id,
        )

        payload = {
            "model": OLLAMA_MODEL,
            "keep_alive": LOCAL_BRAIN_KEEP_ALIVE,
            "messages": chat_history,
            "stream": True,
            "options": {
                "num_ctx": 2048,
                "temperature": 0.3,
                "top_p": 0.9,
            },
        }

        request_started_at = time.perf_counter()

        response = requests.post(
            OLLAMA_CHAT_URL,
            json=payload,
            stream=True,
            timeout=(5, 180),
        )

        performance.record_stage(
            "brain_ollama_request_open_seconds",
            time.perf_counter() - request_started_at,
            trace_id,
        )

        response.raise_for_status()

        for line in _iter_cancellable_lines(
            response,
            cancellation_token,
        ):
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            chunk = data.get("message", {}).get("content", "")

            if chunk and not first_token_seen:
                first_token_seen = True

                performance.record_stage(
                    "brain_time_to_first_token_seconds",
                    time.perf_counter() - request_started_at,
                    trace_id,
                )

                performance.mark(
                    "brain_first_token",
                    trace_id,
                    only_once=True,
                )

            if data.get("done"):
                load_seconds = (
                    data.get("load_duration", 0)
                    / 1_000_000_000
                )

                prompt_seconds = (
                    data.get("prompt_eval_duration", 0)
                    / 1_000_000_000
                )

                answer_seconds = (
                    data.get("eval_duration", 0)
                    / 1_000_000_000
                )

                performance.record_stage(
                    "brain_ollama_model_load_seconds",
                    load_seconds,
                    trace_id,
                )

                performance.record_stage(
                    "brain_ollama_prompt_eval_seconds",
                    prompt_seconds,
                    trace_id,
                )

                performance.record_stage(
                    "brain_ollama_answer_eval_seconds",
                    answer_seconds,
                    trace_id,
                )

                performance.add_metric(
                    "brain_ollama_prompt_tokens",
                    data.get("prompt_eval_count", 0),
                    trace_id,
                )

                performance.add_metric(
                    "brain_ollama_answer_tokens",
                    data.get("eval_count", 0),
                    trace_id,
                )

            for character in chunk:
                if _generation_is_cancelled(
                    cancellation_token
                ):
                    break

                full_reply += character

                if character == "<" and not in_tag:
                    in_tag = True
                    tag_buffer = "<"

                    if text_buffer.strip():
                        text_to_yield = text_buffer.strip()

                        record_first_text_event(text_to_yield)

                        yield ("text", text_to_yield)
                        text_buffer = ""

                elif in_tag:
                    tag_buffer += character

                    if character == ">":
                        in_tag = False

                        performance.mark(
                            "brain_first_tag_event",
                            trace_id,
                            only_once=True,
                        )

                        yield ("tag", tag_buffer)
                        tag_buffer = ""

                else:
                    text_buffer += character

                    if character in ".!?":
                        if text_buffer.strip():
                            text_to_yield = text_buffer.strip()

                            record_first_text_event(text_to_yield)

                            yield ("text", text_to_yield)
                            text_buffer = ""

            if _generation_is_cancelled(
                cancellation_token
            ):
                outcome = "cancelled"

                cancellation_reason = (
                    cancellation_token.reason
                    if cancellation_token is not None
                    else "cancelled"
                )

                print(
                    "🛑 Local brain generation cancelled: "
                    f"reason={cancellation_reason!r}, "
                    f"generated_characters={len(full_reply)}"
                )

                performance.add_metadata(
                    {
                        "brain_generation_cancelled": (
                            True
                        ),
                        "brain_generation_cancel_reason": (
                            cancellation_reason
                        ),
                    },
                    trace_id,
                )

                # Retain text already generated so a clarification can
                # still refer to what Avens actually said.
                if full_reply.strip():
                    manage_memory(
                        "assistant",
                        full_reply.strip(),
                    )
                else:
                    _remove_last_user_turn(prompt)

                return

        if in_tag and tag_buffer:
            text_buffer += tag_buffer

        if text_buffer.strip():
            text_to_yield = text_buffer.strip()
            record_first_text_event(text_to_yield)
            yield ("text", text_to_yield)

        manage_memory("assistant", full_reply)

    except requests.RequestException as error:
        print(f"⚠️ Ollama connection error: {error}")
        outcome = "ollama_connection_error"

        yield (
            "text",
            "My local brain is unavailable, sir. Check that Ollama is running.",
        )

    except Exception as error:
        print(f"⚠️ Brain error: {error}")
        outcome = "brain_error"

        yield (
            "text",
            "My local brain is struggling, sir.",
        )

    finally:
        if response is not None:
            response.close()

        if request_started_at is not None:
            performance.record_stage(
                "brain_ollama_stream_wall_seconds",
                time.perf_counter() - request_started_at,
                trace_id,
            )

        performance.add_metric(
            "brain_reply_characters",
            len(full_reply),
            trace_id,
        )

        performance.finish_span(
            span_id,
            outcome=outcome,
        )

        if owns_trace:
            performance.finish(
                trace_id,
                outcome=outcome,
            )


def get_response(
    prompt: str,
    *,
    cancellation_token: (
        GenerationCancellationToken | None
    ) = None,
):
    """Route one question through the current explicit brain mode."""
    state = mode_controller.snapshot()

    if state.brain_mode != "online":
        return offline_ai(
            prompt,
            cancellation_token=(
                cancellation_token
            ),
        )

    if state.brain_provider == "gpt":
        return gpt_ai(prompt)

    if state.brain_provider == "gemini":
        return gemini_ai(prompt)

    print(
        "⚠️ Invalid online brain provider. "
        "Returning to local Ollama.",
    )

    return offline_ai(
        prompt,
        cancellation_token=(
            cancellation_token
        ),
    )