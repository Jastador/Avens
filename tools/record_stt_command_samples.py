from __future__ import annotations

import argparse
import json
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sounddevice as sd

from tools.benchmark_stt_commands import (
    MANIFEST_FILENAME,
    PHRASE_SETS,
)

from utils.mic_check import get_active_mic

SAMPLE_RATE = 16_000
CHANNELS = 1
DEFAULT_TAKES_PER_COMMAND = 3
DEFAULT_RECORD_SECONDS = 4.0


def make_default_output_directory(phrase_set: str) -> Path:
    """Create a distinct local directory for one command-sample session."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("logs") / "stt_benchmark" / phrase_set / timestamp


def write_pcm16_wave(
    output_path: Path,
    audio: np.ndarray,
) -> None:
    """Write a mono float32 recording as a standard 16 kHz PCM WAV."""
    clipped_audio = np.clip(audio, -1.0, 1.0)
    pcm_audio = (clipped_audio * 32767).astype("<i2")

    with wave.open(str(output_path), "wb") as wave_file:
        wave_file.setnchannels(CHANNELS)
        wave_file.setsampwidth(2)
        wave_file.setframerate(SAMPLE_RATE)
        wave_file.writeframes(pcm_audio.tobytes())


def write_manifest(
    output_directory: Path,
    samples: list[dict[str, str | int]],
) -> None:
    """Persist the recording manifest after every completed clip."""
    payload = {
        "created_at_utc": datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        ),
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "samples": samples,
    }

    manifest_path = output_directory / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def countdown() -> None:
    """Give the speaker a predictable moment before recording begins."""
    for remaining in range(3, 0, -1):
        print(f"Recording starts in {remaining}...")
        time.sleep(1)


def record_command(
    *,
    duration_seconds: float,
    device,
) -> np.ndarray:
    """Capture one fixed-length command clip from Avens's active mic."""
    frame_count = round(duration_seconds * SAMPLE_RATE)

    recording = sd.rec(
        frame_count,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        device=device,
    )
    sd.wait()

    return recording


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record local Avens command clips for offline STT comparison."
        )
    )
    parser.add_argument(
        "--takes",
        type=int,
        default=DEFAULT_TAKES_PER_COMMAND,
        help="How many recordings to capture for every command.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=DEFAULT_RECORD_SECONDS,
        help="Fixed duration of each recording.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Optional empty directory for the clips. By default, a new "
            "timestamped folder is created under logs."
        ),
    )
    parser.add_argument(
        "--phrase-set",
        choices=tuple(PHRASE_SETS),
        default="commands",
        help="Phrase set to record for STT benchmarking.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    phrase_set_name = args.phrase_set
    phrases = PHRASE_SETS[phrase_set_name]

    if args.takes < 1:
        raise ValueError("--takes must be at least 1.")

    if args.seconds <= 0:
        raise ValueError("--seconds must be greater than zero.")

    output_directory = (
        args.output_dir
        if args.output_dir is not None
        else make_default_output_directory(phrase_set_name)
    )

    if output_directory.exists() and any(output_directory.iterdir()):
        raise FileExistsError(
            f"Refusing to overwrite existing files in: {output_directory}"
        )

    output_directory.mkdir(parents=True, exist_ok=True)

    device = get_active_mic()
    samples = []
    total_recordings = len(phrases) * args.takes

    print(f"Using Avens microphone: {device}")
    print(f"Saving {total_recordings} local clips in: {output_directory}")
    print(
        "Speak the displayed command once, naturally, after each "
        "countdown. Do not add filler words."
    )

    completed = 0

    for command_index, expected_text in enumerate(phrases, start=1):
        for take in range(1, args.takes + 1):
            completed += 1
            file_name = (
                f"command_{command_index:02d}_take_{take:02d}.wav"
            )
            output_path = output_directory / file_name

            print(
                f"\n[{completed}/{total_recordings}] "
                f"Say exactly: {expected_text}"
            )
            input("Press Enter when ready. ")

            countdown()
            recording = record_command(
                duration_seconds=args.seconds,
                device=device,
            )
            write_pcm16_wave(output_path, recording)

            samples.append(
                {
                    "expected_text": expected_text,
                    "audio_file": file_name,
                    "take": take,
                }
            )
            write_manifest(output_directory, samples)

            print(f"Saved: {output_path.name}")

    print("\nRecording set complete.")
    print(
        "Run this next:\n"
        "python -m tools.benchmark_stt_commands "
        f'--sample-dir "{output_directory}"'
    )


if __name__ == "__main__":
    main()