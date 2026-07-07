from __future__ import annotations

import argparse
import gc
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

COMMAND_PHRASES = (
    "open notepad",
    "open calculator",
    "minimize notepad",
    "restore notepad",
    "close notepad",
    "confirm close notepad",
    "refresh app list",
    "take a note buy chicken tomorrow",
    "add note finish Avens tests",
    "show my notes",
    "list notes",
    "search notes chicken",
    "delete note 2",
    "confirm delete note 2",
    "cancel delete note",
    "go to sleep",
    "list apps",
    "search apps chrome",
    "what can i control",
    "what can i do with chrome",
)

NON_COMMAND_PHRASES = (
    "what time is it",
    "tell me a joke about computers",
    "what is the weather in Delhi",
    "explain machine learning simply",
    "what does notepad do",
    "how do I close a file safely",
    "why do people minimize windows",
    "I do not want you to open anything",
    "what happens when a computer goes to sleep",
    "how do I refresh a web page",
)

PHRASE_SETS = {
    "commands": COMMAND_PHRASES,
    "noncommands": NON_COMMAND_PHRASES,
}

DEFAULT_MODELS = (
    "distil-small.en",
    "small.en",
)

MANIFEST_FILENAME = "manifest.json"

COMMAND_HOTWORDS = (
    "Notepad, Calculator, minimize, maximize, restore, bring up, "
    "close, confirm, cancel, refresh, app list, list apps, show apps, "
    "search apps, find app, what can I control, what can I do with, "
    "go to sleep"
    "Notepad, Calculator, minimize, maximize, restore, bring up, "
    "close, confirm, cancel, refresh, app list, list apps, show apps, "
    "search apps, find app, what can I control, what can I do with, "
    "take a note, add note, show my notes, list notes, search notes, "
    "delete note, confirm delete note, cancel delete note, "
    "go to sleep"
)

COMMAND_INITIAL_PROMPT = (
    "Voice commands include: Open Notepad. Open Calculator. "
    "Minimize Notepad. Restore Notepad. Close Notepad. "
    "Confirm close Notepad. Refresh app list. List apps. "
    "Search apps Chrome. Find app Visual Studio Code. "
    "What can I control? What can I do with Chrome? Go to sleep."
    "Voice commands include: Open Notepad. Open Calculator. "
    "Minimize Notepad. Restore Notepad. Close Notepad. "
    "Confirm close Notepad. Refresh app list. List apps. "
    "Search apps Chrome. Find app Visual Studio Code. "
    "What can I control? What can I do with Chrome? "
    "Take a note buy chicken tomorrow. Add note finish Avens tests. "
    "Show my notes. List notes. Search notes chicken. Go to sleep."
    "Delete note 2. Confirm delete note 2. Cancel delete note. "
)

@dataclass(frozen=True)
class CommandSample:
    expected_text: str
    audio_file: str
    take: int


@dataclass(frozen=True)
class SampleResult:
    model_name: str
    expected_text: str
    audio_file: str
    take: int
    transcription: str
    normalized_transcription: str
    exact_match: bool
    decode_seconds: float


def normalize_command_text(text: str) -> str:
    """Normalize text for strict benchmark comparisons."""
    lowered = text.casefold()
    letters_numbers_and_spaces = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return " ".join(letters_numbers_and_spaces.split())


def is_exact_command_match(
    expected_text: str,
    transcription: str,
) -> bool:
    """Return whether a transcript matches its expected command exactly."""
    return (
        normalize_command_text(expected_text)
        == normalize_command_text(transcription)
    )


def load_samples(sample_directory: Path) -> list[CommandSample]:
    """Load and validate the local command-sample manifest."""
    manifest_path = sample_directory / MANIFEST_FILENAME

    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Command-sample manifest was not found: {manifest_path}"
        )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_samples = payload.get("samples")

    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError(
            "The command-sample manifest must contain a non-empty "
            "'samples' list."
        )

    samples = []

    for index, raw_sample in enumerate(raw_samples, start=1):
        if not isinstance(raw_sample, dict):
            raise ValueError(
                f"Manifest sample {index} must be a JSON object."
            )

        expected_text = raw_sample.get("expected_text")
        audio_file = raw_sample.get("audio_file")
        take = raw_sample.get("take")

        if not isinstance(expected_text, str) or not expected_text.strip():
            raise ValueError(
                f"Manifest sample {index} has an invalid expected_text."
            )

        if not isinstance(audio_file, str) or not audio_file.strip():
            raise ValueError(
                f"Manifest sample {index} has an invalid audio_file."
            )

        if not isinstance(take, int) or take < 1:
            raise ValueError(
                f"Manifest sample {index} has an invalid take."
            )

        audio_path = sample_directory / audio_file

        if not audio_path.is_file():
            raise FileNotFoundError(
                f"Manifest sample {index} audio file was not found: "
                f"{audio_path}"
            )

        samples.append(
            CommandSample(
                expected_text=expected_text,
                audio_file=audio_file,
                take=take,
            )
        )

    return samples


def load_transcription_model(
    model_name: str,
    *,
    allow_model_download: bool,
):
    """Load one Faster-Whisper model using Avens's GPU runtime setup."""
    from core.stt import _preload_gpu_runtime_dlls

    _preload_gpu_runtime_dlls()

    from faster_whisper import WhisperModel

    return WhisperModel(
        model_name,
        device="cuda",
        compute_type="int8_float16",
        local_files_only=not allow_model_download,
    )


def transcribe_sample(
    model,
    audio_path: Path,
    *,
    command_aware: bool,
) -> tuple[str, float]:
    """Transcribe one sample and include lazy decode time."""
    options = {
        "language": "en",
        "beam_size": 5,
        "vad_filter": True,
    }

    if command_aware:
        options.update(
            {
                "condition_on_previous_text": False,
                "hotwords": COMMAND_HOTWORDS,
                "initial_prompt": COMMAND_INITIAL_PROMPT,
            }
        )

    started_at = time.perf_counter()
    segments, _ = model.transcribe(
        str(audio_path),
        **options,
    )
    transcription = "".join(segment.text for segment in segments).strip()
    decode_seconds = time.perf_counter() - started_at

    return transcription, decode_seconds


def benchmark_model(
    model_name: str,
    model,
    sample_directory: Path,
    samples: Iterable[CommandSample],
    *,
    command_aware: bool,
) -> list[SampleResult]:
    """Benchmark one model against the same local command clips."""
    results = []

    for sample in samples:
        audio_path = sample_directory / sample.audio_file
        transcription, decode_seconds = transcribe_sample(
            model,
            audio_path,
            command_aware=command_aware,
        )

        results.append(
            SampleResult(
                model_name=model_name,
                expected_text=sample.expected_text,
                audio_file=sample.audio_file,
                take=sample.take,
                transcription=transcription,
                normalized_transcription=normalize_command_text(
                    transcription
                ),
                exact_match=is_exact_command_match(
                    sample.expected_text,
                    transcription,
                ),
                decode_seconds=round(decode_seconds, 4),
            )
        )

    return results


def build_summary(results: Iterable[SampleResult]) -> dict[str, float | int]:
    """Build one compact exact-command accuracy and speed summary."""
    result_list = list(results)

    if not result_list:
        return {
            "total_samples": 0,
            "exact_matches": 0,
            "exact_match_rate": 0.0,
            "average_decode_seconds": 0.0,
        }

    exact_matches = sum(result.exact_match for result in result_list)
    average_decode_seconds = sum(
        result.decode_seconds
        for result in result_list
    ) / len(result_list)

    return {
        "total_samples": len(result_list),
        "exact_matches": exact_matches,
        "exact_match_rate": round(
            exact_matches / len(result_list),
            4,
        ),
        "average_decode_seconds": round(average_decode_seconds, 4),
    }


def write_results(
    sample_directory: Path,
    *,
    summaries: dict[str, dict[str, float | int]],
    results: list[SampleResult],
) -> Path:
    """Write local benchmark results beside the source clips."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result_path = sample_directory / f"results_{timestamp}.json"

    payload = {
        "created_at_utc": timestamp,
        "summaries": summaries,
        "results": [
            asdict(result)
            for result in results
        ],
    }

    result_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    return result_path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare local Faster-Whisper models against the same "
            "recorded Avens command clips."
        )
    )
    parser.add_argument(
        "--sample-dir",
        required=True,
        type=Path,
        help="Directory containing manifest.json and local WAV clips.",
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help=(
            "Model to compare. Repeat for multiple models. Defaults to "
            "distil-small.en and small.en."
        ),
    )
    parser.add_argument(
        "--allow-model-download",
        action="store_true",
        help=(
            "Allow an explicitly requested model to download when it is "
            "not already cached locally."
        ),
    )
    parser.add_argument(
        "--command-aware",
        action="store_true",
        help=(
            "Use command vocabulary hints and repetition-resistant "
            "decoding for this benchmark run."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    sample_directory = args.sample_dir.resolve()
    models = tuple(args.models or DEFAULT_MODELS)
    samples = load_samples(sample_directory)

    all_results = []
    summaries = {}

    print(f"Loaded {len(samples)} local command samples.")

    for model_name in models:
        print(f"\nBenchmarking {model_name} on GPU...")

        try:
            model = load_transcription_model(
                model_name,
                allow_model_download=args.allow_model_download,
            )
        except Exception as error:
            raise RuntimeError(
                f"Could not load {model_name}. If it is not cached "
                "locally, rerun with --allow-model-download. "
                f"Original error: {error}"
            ) from error

        model_results = benchmark_model(
            model_name,
            model,
            sample_directory,
            samples,
            command_aware=args.command_aware,
        )
        summary = build_summary(model_results)

        summaries[model_name] = summary
        all_results.extend(model_results)

        print(
            f"{model_name}: "
            f"{summary['exact_matches']}/{summary['total_samples']} "
            "exact matches | "
            f"average decode {summary['average_decode_seconds']:.2f}s"
        )

        del model
        gc.collect()

    result_path = write_results(
        sample_directory,
        summaries=summaries,
        results=all_results,
    )
    print(f"\nSaved local results: {result_path}")


if __name__ == "__main__":
    main()