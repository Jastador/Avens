"""Compare local vision-language models on one identical webcam crop.

Nothing is written to disk. The captured frame stays only in RAM.
Press SPACE to capture the current scan region.
Press ESC to cancel.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Final

import cv2
import numpy as np
import requests


OLLAMA_URL: Final = "http://127.0.0.1:11434/api/generate"

MODELS: Final = (
    "minicpm-v4.6:1b",
    "minicpm-v4.6:1b",
)

IMAGE_MAX_SIDE: Final = 640
CONTEXT_TOKENS: Final = 2048
MAX_RESPONSE_TOKENS: Final = 96
REQUEST_TIMEOUT_SECONDS: Final = 150

CROP_WIDTH_RATIO: Final = 0.72
CROP_HEIGHT_RATIO: Final = 0.86

IDENTIFY_PROMPT: Final = (
    "Identify the main everyday object held in the centre of this image. "
    "Give the generic object category first, followed by one short sentence "
    "about clearly visible details. Do not guess brand or model. "
    "If uncertain, begin with Uncertain."
)


@dataclass(frozen=True)
class BenchmarkResult:
    model: str
    answer: str
    wall_seconds: float
    load_seconds: float
    prompt_seconds: float
    answer_seconds: float


def open_camera() -> cv2.VideoCapture:
    """Open the default webcam, preferring DirectShow on Windows."""
    camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    if not camera.isOpened():
        camera.release()
        camera = cv2.VideoCapture(0)

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    camera.set(cv2.CAP_PROP_FPS, 30)

    return camera


def crop_scan_region(frame: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Return the centre crop and its rectangle coordinates."""
    height, width = frame.shape[:2]

    crop_width = int(width * CROP_WIDTH_RATIO)
    crop_height = int(height * CROP_HEIGHT_RATIO)

    left = (width - crop_width) // 2
    top = (height - crop_height) // 2
    right = left + crop_width
    bottom = top + crop_height

    return frame[top:bottom, left:right].copy(), (left, top, right, bottom)


def resize_frame(frame: np.ndarray) -> np.ndarray:
    """Limit image size so every model receives the same workload."""
    height, width = frame.shape[:2]
    longest_side = max(height, width)

    if longest_side <= IMAGE_MAX_SIDE:
        return frame

    scale = IMAGE_MAX_SIDE / longest_side

    return cv2.resize(
        frame,
        (int(width * scale), int(height * scale)),
        interpolation=cv2.INTER_AREA,
    )


def capture_frame() -> np.ndarray | None:
    """Show a live preview until the user captures one centre crop."""
    camera = open_camera()

    if not camera.isOpened():
        print("Camera 0 could not be opened.")
        return None

    window_name = "Avens Local VLM Benchmark"

    try:
        while True:
            success, frame = camera.read()

            if not success:
                print("Camera stopped returning frames.")
                return None

            _, (left, top, right, bottom) = crop_scan_region(frame)

            preview = frame.copy()

            cv2.rectangle(
                preview,
                (left, top),
                (right, bottom),
                (0, 220, 255),
                2,
            )

            cv2.putText(
                preview,
                "Hold object inside box | SPACE: capture | ESC: cancel",
                (24, 36),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 220, 255),
                2,
                lineType=cv2.LINE_AA,
            )

            cv2.imshow(window_name, preview)

            key = cv2.waitKey(1) & 0xFF

            if key == 32:
                crop, _ = crop_scan_region(frame)
                return crop

            if key in {27, ord("q")}:
                return None

    finally:
        camera.release()
        cv2.destroyAllWindows()


def encode_image(frame: np.ndarray) -> str:
    """Encode one RAM frame for Ollama without creating a file."""
    prepared = resize_frame(frame)

    success, encoded = cv2.imencode(
        ".jpg",
        prepared,
        [cv2.IMWRITE_JPEG_QUALITY, 88],
    )

    if not success:
        raise RuntimeError("Could not encode the captured webcam frame.")

    return base64.b64encode(encoded.tobytes()).decode("ascii")


def seconds_from_nanoseconds(value: object) -> float:
    """Convert Ollama timing fields into readable seconds."""
    try:
        return float(value or 0) / 1_000_000_000
    except (TypeError, ValueError):
        return 0.0


def benchmark_model(model: str, image_base64: str) -> BenchmarkResult:
    """Run one local VLM on the same image payload."""
    payload = {
        "model": model,
        "prompt": IDENTIFY_PROMPT,
        "images": [image_base64],
        "stream": False,
        "keep_alive": "2m",
        "options": {
            "temperature": 0,
            "num_ctx": CONTEXT_TOKENS,
            "num_predict": MAX_RESPONSE_TOKENS,
        },
    }

    started_at = time.perf_counter()

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    wall_seconds = time.perf_counter() - started_at
    response.raise_for_status()

    data = response.json()

    answer = " ".join(
        str(data.get("response", "")).split()
    ).strip()

    return BenchmarkResult(
        model=model,
        answer=answer or "[No answer returned]",
        wall_seconds=wall_seconds,
        load_seconds=seconds_from_nanoseconds(
            data.get("load_duration"),
        ),
        prompt_seconds=seconds_from_nanoseconds(
            data.get("prompt_eval_duration"),
        ),
        answer_seconds=seconds_from_nanoseconds(
            data.get("eval_duration"),
        ),
    )


def print_result(result: BenchmarkResult) -> None:
    """Print one easy-to-compare benchmark record."""
    print()
    print("=" * 66)
    print(f"MODEL:  {result.model}")
    print(f"ANSWER: {result.answer}")
    print(
        "TIME:   "
        f"wall={result.wall_seconds:.1f}s | "
        f"load={result.load_seconds:.1f}s | "
        f"image+prompt={result.prompt_seconds:.1f}s | "
        f"answer={result.answer_seconds:.1f}s"
    )
    print("=" * 66)


def main() -> None:
    print("Opening webcam preview...")
    print("Use one simple object first: phone, mouse, remote, or mug.")

    frame = capture_frame()

    if frame is None:
        print("Benchmark cancelled.")
        return

    image_base64 = encode_image(frame)

    print()
    print("Captured one RAM-only frame.")
    print("Testing all models with the identical image crop.")

    for model in MODELS:
        try:
            print()
            print(f"Running {model}...")

            result = benchmark_model(model, image_base64)
            print_result(result)

        except requests.RequestException as error:
            print(f"{model} failed: {error}")

        except Exception as error:
            print(f"{model} failed unexpectedly: {error}")

    frame = None
    image_base64 = None

    print()
    print("Benchmark complete. No image file was saved.")


if __name__ == "__main__":
    main()