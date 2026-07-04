"""Benchmark warm Kokoro synthesis under Avens-like CPU settings."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import statistics
import sys
import time

from dotenv import load_dotenv


parser = argparse.ArgumentParser()
parser.add_argument(
    "--omp-threads",
    type=int,
    default=1,
)
parser.add_argument(
    "--torch-threads",
    type=int,
    default=1,
)
args = parser.parse_args()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(
    PROJECT_ROOT / ".env",
    override=False,
)

os.environ["HF_HOME"] = os.getenv(
    "AVENS_HF_HOME",
    str(PROJECT_ROOT / "models" / "huggingface"),
)

offline_mode = os.getenv(
    "AVENS_OFFLINE_MODE",
    "false",
).strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}

for variable in (
    "HF_HUB_OFFLINE",
    "HF_DATASETS_OFFLINE",
    "TRANSFORMERS_OFFLINE",
):
    os.environ[variable] = "1" if offline_mode else "0"

os.environ["OMP_NUM_THREADS"] = str(
    max(1, args.omp_threads)
)

os.environ["MKL_NUM_THREADS"] = str(
    max(1, args.omp_threads)
)

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

sys.path.insert(0, str(PROJECT_ROOT))

import torch

torch.set_num_threads(
    max(1, args.torch_threads)
)

from core.tts import pipeline, voicepack


def measure_once(text: str) -> dict[str, float]:
    started_at = time.perf_counter()
    first_chunk_at = None
    generated_audio_seconds = 0.0
    chunks = 0

    for _, _, audio_chunk in pipeline(
        text,
        voice=voicepack,
        speed=1.0,
    ):
        if first_chunk_at is None:
            first_chunk_at = time.perf_counter()

        chunks += 1

        sample_count = (
            audio_chunk.numel()
            if hasattr(audio_chunk, "numel")
            else len(audio_chunk)
        )

        generated_audio_seconds += sample_count / 24000.0

    finished_at = time.perf_counter()

    return {
        "first_audio_seconds": (
            first_chunk_at - started_at
            if first_chunk_at is not None
            else 0.0
        ),
        "total_synthesis_seconds": finished_at - started_at,
        "generated_audio_seconds": generated_audio_seconds,
        "chunks": float(chunks),
    }


print(
    "Kokoro benchmark settings | "
    f"OMP={args.omp_threads} | "
    f"Torch={torch.get_num_threads()} | "
    f"offline={offline_mode}"
)

print("Warming Kokoro...")
for _ in pipeline(
    "Ready.",
    voice=voicepack,
    speed=1.0,
):
    pass

tests = {
    "short": "A computer mouse.",
    "clean_camera_reply": (
        "A computer mouse. "
        "Black, with a scroll wheel and side buttons."
    ),
    "current_camera_reply": (
        "The object is black and appears to be a computer mouse. "
        "It has a textured wheel for navigation and a small blue logo on its side. "
        "The object is a computer mouse. It is black with a textured wheel "
        "and a small blue logo."
    ),
}

for name, text in tests.items():
    runs = [
        measure_once(text),
        measure_once(text),
    ]

    first_audio = statistics.mean(
        run["first_audio_seconds"]
        for run in runs
    )

    total_synthesis = statistics.mean(
        run["total_synthesis_seconds"]
        for run in runs
    )

    generated_audio = statistics.mean(
        run["generated_audio_seconds"]
        for run in runs
    )

    print(
        f"{name}: "
        f"first_audio={first_audio:.2f}s | "
        f"total_synthesis={total_synthesis:.2f}s | "
        f"generated_audio={generated_audio:.2f}s"
    )