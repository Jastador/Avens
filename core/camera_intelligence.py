"""On-demand local camera analysis for Avens.

This module never opens the webcam and never writes images to disk.
It receives one in-memory frame from live_frame_buffer, encodes it temporarily
for the local Ollama/Vision Model request, then discards local references.
"""
from __future__ import annotations

import base64
from typing import Final

import os
import re
import time
import cv2
import numpy as np
import requests
from core.performance import performance

OLLAMA_GENERATE_URL: Final = "http://127.0.0.1:11434/api/generate"
FAST_MODEL_NAME: Final = os.getenv(
    "AVENS_FAST_VISION_MODEL",
    "minicpm-v4.6:1b",
).strip()

DEEP_MODEL_NAME: Final = os.getenv(
    "AVENS_DEEP_VISION_MODEL",
    "qwen2.5vl:3b",
).strip()

FAST_MODEL_KEEP_ALIVE: Final = (
    os.getenv(
        "AVENS_FAST_VISION_KEEP_ALIVE",
        "2m",
    ).strip()
    or "2m"
)

DEEP_MODEL_KEEP_ALIVE: Final = (
    os.getenv(
        "AVENS_DEEP_VISION_KEEP_ALIVE",
        "0",
    ).strip()
    or "0"
)

IMAGE_MAX_SIDE_BY_REQUEST: Final = {
    "identify": 640,
    "describe": 768,
    "read": 960,
}

VISION_CONTEXT_TOKENS: Final = 2048
MAX_RESPONSE_TOKENS_BY_REQUEST: Final = {
    "identify": 32,
    "describe": 64,
    "read": 64,
}
JPEG_QUALITY: Final = 88
REQUEST_TIMEOUT_SECONDS: Final = 90
MAX_RESPONSE_CHARACTERS: Final = 650
FOCUS_CROP_WIDTH_RATIO: Final = 0.72
FOCUS_CROP_HEIGHT_RATIO: Final = 0.86

SUPPORTED_REQUESTS: Final = {
    "describe",
    "identify",
    "read",
}

PROMPTS: Final = {

    "describe": (
        "Describe this single webcam image in concise plain English. "
        "Mention the main visible objects and their rough positions. "
        "Do not identify people or infer sensitive personal traits. "
        "State uncertainty instead of guessing."
    ),

    "identify": (
        "One everyday object is intentionally being held near the centre of this "
        "webcam image. Identify its broad object category only, not a brand or "
        "model. Reply in no more than two short sentences. The first sentence "
        "must start with the object category, for example: 'A computer mouse.' "
        "The second sentence may mention up to two visible details. Do not "
        "describe the hand, person, room, or background. Do not repeat yourself. "
        "Avoid brand or model guesses. If uncertain, begin with 'Uncertain.'"
    ),

    "read": (
    "Transcribe only clearly legible text located near the centre of this "
    "webcam image. Preserve short line breaks where helpful. Do not invent "
    "missing letters or words. If the text is too blurry or small, reply "
    "exactly: I cannot read that clearly."
    ),
}


class CameraIntelligenceError(RuntimeError):
    """Raised when local camera analysis cannot complete."""


def _normalise_request_type(request_type: str) -> str:
    """Validate and normalise one supported local vision request."""
    normalised = " ".join(str(request_type).casefold().split())

    if normalised not in SUPPORTED_REQUESTS:
        raise ValueError(
            "Camera request must be describe, identify, or read."
        )

    return normalised


def get_camera_prompt(request_type: str) -> str:
    """Return the prompt for one approved local vision request."""
    return PROMPTS[_normalise_request_type(request_type)]


def get_camera_model_name(request_type: str) -> str:
    """Choose the local VLM suited to one request type."""
    normalised = _normalise_request_type(request_type)

    if normalised == "identify":
        return FAST_MODEL_NAME

    return DEEP_MODEL_NAME


def get_camera_keep_alive(request_type: str) -> str:
    """Choose how long the selected local model remains loaded."""
    normalised = _normalise_request_type(request_type)

    if normalised == "identify":
        return FAST_MODEL_KEEP_ALIVE

    return DEEP_MODEL_KEEP_ALIVE


def analyze_camera_frame(
    frame: np.ndarray,
    request_type: str,
) -> str:
    """Analyse one in-memory BGR frame through local Ollama/Vision Model."""
    if frame is None or frame.size == 0:
        raise CameraIntelligenceError("No usable camera frame was available.")

    request_kind = _normalise_request_type(request_type)
    prompt = get_camera_prompt(request_kind)
    model_name = get_camera_model_name(request_kind)
    keep_alive = get_camera_keep_alive(request_kind)

    trace_id = performance.current_trace_id()
    owns_trace = trace_id is None

    if owns_trace:
        trace_id = performance.begin(
            "local_camera_analysis",
            metadata={
                "camera_request": request_kind,
                "vision_model": model_name,
            },
        )

    span_id = performance.begin_span(
        "local_camera_analysis",
        trace_id,
        metadata={
            "request": request_kind,
            "model": model_name,
            "keep_alive": keep_alive,
        },
    )

    analysis_started_at = time.perf_counter()
    outcome = "ok"

    prepared_frame = None
    encoded_image = None
    image_base64 = None
    payload = None

    try:
        source_height, source_width = frame.shape[:2]

        performance.add_metadata(
            {
                "local_vision_request": request_kind,
                "local_vision_model": model_name,
                "local_vision_keep_alive": keep_alive,
            },
            trace_id,
        )

        performance.add_metric(
            "local_vision_source_width",
            source_width,
            trace_id,
        )

        performance.add_metric(
            "local_vision_source_height",
            source_height,
            trace_id,
        )

        prepare_started_at = time.perf_counter()

        prepared_frame = _prepare_for_analysis(
            frame,
            request_kind,
        )

        performance.record_stage(
            "local_vision_prepare_seconds",
            time.perf_counter() - prepare_started_at,
            trace_id,
        )

        prepared_height, prepared_width = prepared_frame.shape[:2]

        performance.add_metric(
            "local_vision_prepared_width",
            prepared_width,
            trace_id,
        )

        performance.add_metric(
            "local_vision_prepared_height",
            prepared_height,
            trace_id,
        )

        encode_started_at = time.perf_counter()

        success, encoded_image = cv2.imencode(
            ".jpg",
            prepared_frame,
            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
        )

        if not success:
            raise CameraIntelligenceError(
                "The camera frame could not be encoded."
            )

        image_base64 = base64.b64encode(
            encoded_image.tobytes()
        ).decode("ascii")

        performance.record_stage(
            "local_vision_encode_seconds",
            time.perf_counter() - encode_started_at,
            trace_id,
        )

        performance.add_metric(
            "local_vision_jpeg_bytes",
            int(encoded_image.nbytes),
            trace_id,
        )

        performance.add_metric(
            "local_vision_base64_characters",
            len(image_base64),
            trace_id,
        )

        payload = {
            "model": model_name,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False,
            "keep_alive": keep_alive,
            "options": {
                "temperature": 0,
                "num_ctx": VISION_CONTEXT_TOKENS,
                "num_predict": MAX_RESPONSE_TOKENS_BY_REQUEST[
                    request_kind
                ],
            },
        }

        request_started_at = time.perf_counter()

        print(
            "🧠 Local vision | "
            f"request={request_kind} | "
            f"model={model_name} | "
            f"keep_alive={keep_alive}"
        )

        try:
            response = requests.post(
                OLLAMA_GENERATE_URL,
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.ConnectionError as error:
            raise CameraIntelligenceError(
                "I cannot reach local Ollama. Make sure it is running."
            ) from error
        except requests.Timeout as error:
            raise CameraIntelligenceError(
                "Local Vision Model took too long to analyse the frame."
            ) from error

        performance.record_stage(
            "local_vision_ollama_wall_seconds",
            time.perf_counter() - request_started_at,
            trace_id,
        )

        if response.status_code != 200:
            raise CameraIntelligenceError(
                f"Local Vision Model returned HTTP {response.status_code}."
            )

        try:
            data = response.json()
        except ValueError as error:
            raise CameraIntelligenceError(
                "Local Vision Model returned an unreadable response."
            ) from error

        load_seconds = data.get("load_duration", 0) / 1_000_000_000
        prompt_seconds = (
            data.get("prompt_eval_duration", 0)
            / 1_000_000_000
        )
        answer_seconds = (
            data.get("eval_duration", 0)
            / 1_000_000_000
        )

        performance.record_stage(
            "local_vision_model_load_seconds",
            load_seconds,
            trace_id,
        )

        performance.record_stage(
            "local_vision_image_prompt_seconds",
            prompt_seconds,
            trace_id,
        )

        performance.record_stage(
            "local_vision_answer_eval_seconds",
            answer_seconds,
            trace_id,
        )

        performance.add_metric(
            "local_vision_prompt_tokens",
            data.get("prompt_eval_count", 0),
            trace_id,
        )

        performance.add_metric(
            "local_vision_answer_tokens",
            data.get("eval_count", 0),
            trace_id,
        )

        print(
            "🧠 Vision timing | "
            f"wall={time.perf_counter() - request_started_at:.1f}s | "
            f"load={load_seconds:.1f}s | "
            f"image+prompt={prompt_seconds:.1f}s | "
            f"answer={answer_seconds:.1f}s"
        )

        answer = str(data.get("response", "")).strip()

        if not answer:
            raise CameraIntelligenceError(
                "Local Vision Model did not return an answer."
            )

        cleaned_answer = _clean_answer(
            answer,
            request_kind,
        )

        performance.add_metric(
            "local_vision_answer_characters",
            len(cleaned_answer),
            trace_id,
        )

        return cleaned_answer

    except CameraIntelligenceError:
        outcome = "camera_analysis_error"
        raise

    except Exception:
        outcome = "unexpected_error"
        raise

    finally:
        performance.record_stage(
            "local_vision_total_seconds",
            time.perf_counter() - analysis_started_at,
            trace_id,
        )

        performance.finish_span(
            span_id,
            outcome=outcome,
        )

        payload = None
        image_base64 = None
        encoded_image = None
        prepared_frame = None

        if owns_trace:
            performance.finish(
                trace_id,
                outcome=outcome,
            )

def _prepare_for_analysis(
    frame: np.ndarray,
    request_type: str,
) -> np.ndarray:
    """Zoom into the middle for handheld objects and text."""
    prepared_frame = frame

    if request_type in {"identify", "read"}:
        prepared_frame = _crop_focus_region(frame)

    max_side = IMAGE_MAX_SIDE_BY_REQUEST[request_type]

    return _resize_for_analysis(
        prepared_frame,
        max_side=max_side,
    )


def _crop_focus_region(frame: np.ndarray) -> np.ndarray:
    """Crop the central area where the user is asked to hold an object."""
    height, width = frame.shape[:2]

    crop_width = max(1, int(width * FOCUS_CROP_WIDTH_RATIO))
    crop_height = max(1, int(height * FOCUS_CROP_HEIGHT_RATIO))

    left = max(0, (width - crop_width) // 2)
    top = max(0, (height - crop_height) // 2)

    right = min(width, left + crop_width)
    bottom = min(height, top + crop_height)

    return frame[top:bottom, left:right].copy()

def _resize_for_analysis(
    frame: np.ndarray,
    max_side: int,
) -> np.ndarray:
    """Keep requests small enough for local inference without losing usefulness."""
    height, width = frame.shape[:2]
    longest_side = max(height, width)

    if longest_side <= max_side:
        return frame

    scale = max_side / longest_side

    return cv2.resize(
        frame,
        (
            int(width * scale),
            int(height * scale),
        ),
        interpolation=cv2.INTER_AREA,
    )

def _clean_identify_answer(answer: str) -> str:
    """Keep fast object identification concise and non-repetitive."""
    cleaned = " ".join(answer.split())

    if not cleaned:
        return cleaned

    sentences = re.split(
        r"(?<=[.!?])\s+",
        cleaned,
    )

    selected: list[str] = []
    seen: set[str] = set()

    for sentence in sentences:
        candidate = sentence.strip()

        if not candidate:
            continue

        key = re.sub(
            r"[^a-z0-9]+",
            "",
            candidate.casefold(),
        )

        if not key or key in seen:
            continue

        seen.add(key)
        selected.append(candidate)

        if len(selected) >= 2:
            break

    concise = " ".join(selected) or cleaned

    if len(concise) <= 160:
        return concise

    shortened = concise[:160].rsplit(" ", 1)[0].rstrip(
        " ,;:"
    )

    return f"{shortened}."

def _clean_answer(answer: str, request_type: str) -> str:
    """Keep replies readable and prevent a huge OCR monologue from TTS."""
    if request_type == "identify":
        return _clean_identify_answer(answer)
        
    if request_type == "read":
        lines = [
            " ".join(line.split())
            for line in answer.splitlines()
            if line.strip()
        ]
        cleaned = "\n".join(lines)
    else:
        cleaned = " ".join(answer.split())

    if len(cleaned) <= MAX_RESPONSE_CHARACTERS:
        return cleaned

    shortened = cleaned[:MAX_RESPONSE_CHARACTERS].rsplit(" ", 1)[0]

    return f"{shortened}..."