import ctypes
import os
import queue
import re
import threading
import time
from pathlib import Path
from dataclasses import dataclass
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from utils.mic_check import get_active_mic
from utils.microphone_lock import microphone_lock
from core.performance import performance

STT_PRIMARY_MODEL = "small.en"
STT_FALLBACK_MODEL = "tiny.en"

STT_GPU_DEVICE = "cuda"
STT_GPU_COMPUTE_TYPE = "int8_float16"

STT_CPU_DEVICE = "cpu"
STT_CPU_COMPUTE_TYPE = "int8"
STT_CPU_THREADS = 4
STT_COMMAND_HOTWORDS = (
    "Notepad, Calculator, minimize, maximize, restore, bring up, "
    "close, confirm, cancel, refresh, app list, list apps, show apps, "
    "search apps, find app, what can I control, what can I do with, "
    "take a note, add note, show my notes, list notes, search notes, "
    "delete note, confirm delete note, cancel delete note, "
    "set volume, increase volume, decrease volume, mute volume, "
    "unmute volume, what is the volume, set brightness, "
    "increase brightness, decrease brightness, what is brightness, "
    "night light settings, reading setup, "
    "go to sleep"
)

STT_COMMAND_INITIAL_PROMPT = (
    "Voice commands include: Open Notepad. Open Calculator. "
    "Minimize Notepad. Restore Notepad. Close Notepad. "
    "Confirm close Notepad. Refresh app list. List apps. "
    "Search apps Chrome. Find app Visual Studio Code. "
    "What can I control? What can I do with Chrome? "
    "Take a note buy chicken tomorrow. Add note finish Avens tests. "
    "Show my notes. List notes. Search notes chicken. "
    "Delete note 2. Confirm delete note 2. Cancel delete note. "
    "Set volume to 70. Increase volume by 10. Mute volume. "
    "What is the volume? Set brightness to 50. "
    "Decrease brightness by 10. What is brightness? "
    "Open Night Light Settings. Start reading setup. "
    "Go to sleep."
)

CUDA_RUNTIME_DLLS = (
    "cublasLt64_12.dll",
    "cublas64_12.dll",
    "cudnn64_9.dll",
)

_gpu_runtime_preloaded = False
_gpu_runtime_dll_directory_handles = []
_gpu_runtime_dll_handles = []


def _append_gpu_runtime_directory(
    directory,
    directories,
    seen_directories,
):
    """Add one existing runtime directory once."""
    directory_path = Path(directory)

    if not directory_path.is_dir():
        return

    directory_key = str(directory_path).casefold()

    if directory_key in seen_directories:
        return

    seen_directories.add(directory_key)
    directories.append(directory_path)


def _iter_gpu_runtime_directories():
    """Return deterministic CUDA and cuDNN runtime search directories."""
    directories = []
    seen_directories = set()

    for path_entry in os.environ.get("PATH", "").split(os.pathsep):
        if path_entry:
            _append_gpu_runtime_directory(
                path_entry,
                directories,
                seen_directories,
            )

    for variable_name, variable_value in os.environ.items():
        variable_name = variable_name.upper()

        if (
            variable_name == "CUDA_PATH"
            or variable_name.startswith("CUDA_PATH_V")
        ) and variable_value:
            _append_gpu_runtime_directory(
                Path(variable_value) / "bin",
                directories,
                seen_directories,
            )

    program_files = Path(
        os.environ.get("ProgramFiles", r"C:\Program Files")
    )

    cuda_install_root = (
        program_files
        / "NVIDIA GPU Computing Toolkit"
        / "CUDA"
    )

    for directory in sorted(
        cuda_install_root.glob("v*/bin"),
        reverse=True,
    ):
        _append_gpu_runtime_directory(
            directory,
            directories,
            seen_directories,
        )

    cudnn_install_root = program_files / "NVIDIA" / "CUDNN"

    for pattern in (
        "v*/bin/*/x64",
        "v*/bin/x64",
        "v*/bin",
    ):
        for directory in sorted(
            cudnn_install_root.glob(pattern),
            reverse=True,
        ):
            _append_gpu_runtime_directory(
                directory,
                directories,
                seen_directories,
            )

    return directories


def _find_gpu_runtime_dll_path(dll_name):
    """Find one required CUDA or cuDNN DLL in known local locations."""
    for directory in _iter_gpu_runtime_directories():
        dll_path = directory / dll_name

        if dll_path.is_file():
            return dll_path

    return None


def _preload_gpu_runtime_dlls():
    """Preload CUDA runtime DLLs needed by CTranslate2 on Windows."""
    global _gpu_runtime_preloaded

    if os.name != "nt" or _gpu_runtime_preloaded:
        return

    runtime_dll_paths = []

    for dll_name in CUDA_RUNTIME_DLLS:
        dll_path = _find_gpu_runtime_dll_path(dll_name)

        if dll_path is None:
            raise RuntimeError(
                "Required GPU runtime DLL was not found locally: "
                f"{dll_name}"
            )

        runtime_dll_paths.append((dll_name, dll_path))

    runtime_directories = []
    seen_directories = set()

    for _, dll_path in runtime_dll_paths:
        directory = dll_path.parent
        directory_key = str(directory).casefold()

        if directory_key not in seen_directories:
            seen_directories.add(directory_key)
            runtime_directories.append(directory)

    directory_handles = [
        os.add_dll_directory(str(directory))
        for directory in runtime_directories
    ]

    dll_handles = [
        ctypes.WinDLL(str(dll_path))
        for _, dll_path in runtime_dll_paths
    ]

    _gpu_runtime_dll_directory_handles.extend(directory_handles)
    _gpu_runtime_dll_handles.extend(dll_handles)
    _gpu_runtime_preloaded = True

model = None
audio_queue = queue.Queue()

@dataclass(frozen=True)
class SttDecodeDecision:
    """Transcript selected after command-first STT decoding."""

    text: str
    decode_path: str
    command_decode_seconds: float
    generic_decode_seconds: float | None


def _normalise_sentence_for_repeat_check(text: str) -> str:
    """Normalize one sentence only for exact repetition checks."""
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.casefold())
    return " ".join(cleaned.split())


def _collapse_exact_repeated_sentences(text: str) -> str:
    """Collapse only identical repeated sentences from command decoding."""
    stripped_text = text.strip()
    sentences = [
        sentence.strip()
        for sentence in re.split(r"[.!?]+", stripped_text)
        if sentence.strip()
    ]

    if len(sentences) < 2:
        return stripped_text

    first_normalized = _normalise_sentence_for_repeat_check(
        sentences[0]
    )

    if (
        first_normalized
        and all(
            _normalise_sentence_for_repeat_check(sentence)
            == first_normalized
            for sentence in sentences
        )
    ):
        return sentences[0]

    return stripped_text


def _transcribe_audio(
    audio_data,
    *,
    command_aware: bool,
) -> str:
    """Decode already-recorded audio with one selected STT policy."""
    options = {
        "language": "en",
        "beam_size": 5,
        "vad_filter": True,
    }

    if command_aware:
        options.update(
            {
                "condition_on_previous_text": False,
                "hotwords": STT_COMMAND_HOTWORDS,
                "initial_prompt": STT_COMMAND_INITIAL_PROMPT,
            }
        )

    segments, _ = model.transcribe(
        audio_data,
        **options,
    )

    return "".join(
        segment.text
        for segment in segments
    ).strip()


def _is_explicit_local_skill_request(text: str) -> bool:
    """Use the side-effect-free local-skill grammar checker."""
    from skills.router import is_explicit_local_skill_request

    return is_explicit_local_skill_request(text)


def _decode_audio_for_turn(audio_data) -> SttDecodeDecision:
    """Prefer an explicit command transcript, otherwise use generic STT."""
    command_started_at = time.perf_counter()

    try:
        command_text = _collapse_exact_repeated_sentences(
            _transcribe_audio(
                audio_data,
                command_aware=True,
            )
        )
    except Exception as error:
        print(f"⚠️ Command-aware transcription pass failed: {error}")
        command_text = ""

    command_decode_seconds = (
        time.perf_counter() - command_started_at
    )

    if (
        command_text
        and _is_explicit_local_skill_request(command_text)
    ):
        return SttDecodeDecision(
            text=command_text,
            decode_path="command",
            command_decode_seconds=command_decode_seconds,
            generic_decode_seconds=None,
        )

    generic_started_at = time.perf_counter()
    generic_text = _transcribe_audio(
        audio_data,
        command_aware=False,
    )
    generic_decode_seconds = (
        time.perf_counter() - generic_started_at
    )

    return SttDecodeDecision(
        text=generic_text,
        decode_path="generic",
        command_decode_seconds=command_decode_seconds,
        generic_decode_seconds=generic_decode_seconds,
    )


def audio_callback(indata, frames, time_info, status):
    if status:
        pass
    audio_queue.put(indata.copy())


def _create_whisper_model(
    model_name,
    *,
    device,
    compute_type,
):
    """Create one Whisper model with only device-appropriate options."""
    options = {
        "device": device,
        "compute_type": compute_type,
    }

    if device == STT_CPU_DEVICE:
        options["cpu_threads"] = STT_CPU_THREADS

    return WhisperModel(
        model_name,
        **options,
    )


def init_model():
    global model

    if model is not None:
        print("✅ Faster-Whisper already initialized.")
        return

    print("🧠 Initializing Faster-Whisper Engine...")

    try:
        _preload_gpu_runtime_dlls()

        if os.name == "nt":
            print("✅ CUDA runtime DLLs preloaded for GPU STT.")

        model = _create_whisper_model(
            STT_PRIMARY_MODEL,
            device=STT_GPU_DEVICE,
            compute_type=STT_GPU_COMPUTE_TYPE,
        )
        print(
            "✅ Success: Faster-Whisper Engine Online on GPU "
            "(CUDA int8_float16)."
        )
        return
    except Exception as gpu_error:
        print(
            "⚠️ GPU Faster-Whisper initialization failed: "
            f"{gpu_error}. Trying CPU fallback..."
        )

    try:
        model = _create_whisper_model(
            STT_PRIMARY_MODEL,
            device=STT_CPU_DEVICE,
            compute_type=STT_CPU_COMPUTE_TYPE,
        )
        print(
            "✅ Success: Faster-Whisper Engine Online on CPU "
            "fallback."
        )
        return
    except Exception as cpu_error:
        print(
            f"⚠️ CPU {STT_PRIMARY_MODEL} initialization failed: "
            f"{cpu_error}. Trying tiny.en fallback..."
        )

    try:
        model = _create_whisper_model(
            STT_FALLBACK_MODEL,
            device=STT_CPU_DEVICE,
            compute_type=STT_CPU_COMPUTE_TYPE,
        )
        print(
            "✅ Success: Faster-Whisper tiny.en fallback Engine "
            "Online on CPU."
        )
    except Exception as fallback_error:
        model = None
        print(
            "❌ CRITICAL: Faster-Whisper failed entirely. "
            f"{fallback_error}"
        )

def listen(silence_limit=1.8, max_duration=15):
    global model

    trace_id = performance.current_trace_id()
    owns_trace = trace_id is None

    if owns_trace:
        trace_id = performance.begin(
            "stt_listen",
            metadata={
                "backend": "faster_whisper",
                "silence_limit_seconds": silence_limit,
                "max_duration_seconds": max_duration,
            },
        )

    listen_started_at = time.perf_counter()
    outcome = "ok"

    try:
        if model is None:
            model_init_started_at = time.perf_counter()

            init_model()

            performance.record_stage(
                "stt_model_init_seconds",
                time.perf_counter() - model_init_started_at,
                trace_id,
            )

            if model is None:
                outcome = "model_unavailable"
                return ""

        print("🎤 Listening...")
        time.sleep(0.1)

        # Flush audio left over from a prior recording stream.
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                break

        sample_rate = 16000
        # Smaller chunks let Avens detect the end of speech more precisely.
        # Keep the same silence_limit policy for now.
        chunk_duration = 0.25

        chunk_samples = int(sample_rate * chunk_duration)
        energy_threshold = 0.015

        recorded_chunks = []
        has_spoken = False
        mic_id = get_active_mic()

        capture_started_at = None
        last_voice_at = None

        performance.add_metadata(
            {
                "sample_rate": sample_rate,
                "chunk_duration_seconds": chunk_duration,
                "energy_threshold": energy_threshold,
                "microphone_id": mic_id,
            },
            trace_id,
        )

        try:
            lock_wait_started_at = time.perf_counter()

            # Wake word and barge-in share this microphone lock.
            with microphone_lock:
                performance.record_stage(
                    "stt_microphone_lock_wait_seconds",
                    time.perf_counter() - lock_wait_started_at,
                    trace_id,
                )

                with sd.InputStream(
                    device=mic_id,
                    samplerate=sample_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=chunk_samples,
                    callback=audio_callback,
                ):
                    capture_started_at = time.perf_counter()
                    performance.mark(
                        "stt_capture_started",
                        trace_id,
                        only_once=True,
                    )

                    while True:
                        try:
                            chunk = audio_queue.get(timeout=2.0)
                        except queue.Empty:
                            print("⚠️ Mic timeout.")
                            outcome = "mic_timeout"
                            break

                        recorded_chunks.append(chunk)
                        energy = np.sqrt(np.mean(chunk ** 2))
                        now = time.perf_counter()

                        if energy > energy_threshold:
                            if not has_spoken:
                                has_spoken = True
                                performance.mark(
                                    "user_speech_started",
                                    trace_id,
                                    only_once=True,
                                )

                            last_voice_at = now

                            # This is overwritten each time speech is detected,
                            # leaving the final real voice chunk as speech end.
                            performance.mark(
                                "user_speech_end",
                                trace_id,
                            )

                        elif has_spoken and last_voice_at is not None:
                            silence_elapsed = now - last_voice_at

                            if silence_elapsed >= silence_limit:
                                break

                        if (
                            len(recorded_chunks) * chunk_duration
                            > max_duration
                        ):
                            outcome = "max_duration_reached"
                            break

        except sd.PortAudioError as error:
            print(f"⚠️ Recording audio error: {error}")
            outcome = "recording_error"
            return ""

        except Exception as error:
            print(f"❌ Recording pipeline failure: {error}")
            outcome = "recording_error"
            return ""

        finally:
            if capture_started_at is not None:
                capture_finished_at = time.perf_counter()

                performance.record_stage(
                    "stt_audio_capture_seconds",
                    capture_finished_at - capture_started_at,
                    trace_id,
                )

                performance.mark(
                    "stt_capture_finished",
                    trace_id,
                )

                if last_voice_at is not None:
                    performance.record_stage(
                        "stt_silence_tail_seconds",
                        capture_finished_at - last_voice_at,
                        trace_id,
                    )

        if not recorded_chunks:
            outcome = "no_audio"
            return ""

        audio_data = np.concatenate(recorded_chunks).flatten()

        performance.add_metric(
            "stt_audio_duration_seconds",
            len(audio_data) / sample_rate,
            trace_id,
        )

        print("Transcribing...")

        transcription_started_at = time.perf_counter()
        performance.mark(
            "stt_decode_started",
            trace_id,
            only_once=True,
        )

        try:
            decision = _decode_audio_for_turn(audio_data)
            text = decision.text

            performance.record_stage(
                "stt_command_decode_seconds",
                decision.command_decode_seconds,
                trace_id,
            )

            if decision.generic_decode_seconds is not None:
                performance.record_stage(
                    "stt_generic_decode_seconds",
                    decision.generic_decode_seconds,
                    trace_id,
                )

            performance.add_metadata(
                {
                    "stt_decode_path": decision.decode_path,
                },
                trace_id,
            )

            print(f"STT decode path: {decision.decode_path}")

        except Exception as error:
            print(f"⚠️ Transcription inference failed: {error}")
            text = ""
            outcome = "transcription_error"

        finally:
            performance.record_stage(
                "stt_decode_seconds",
                time.perf_counter() - transcription_started_at,
                trace_id,
            )

            performance.mark(
                "stt_decode_finished",
                trace_id,
            )

        if not text and outcome == "ok":
            outcome = "empty_transcript"

        performance.add_metric(
            "transcript_characters",
            len(text),
            trace_id,
        )

        print("You said:", text)
        return text

    finally:
        performance.record_stage(
            "stt_listen_total_seconds",
            time.perf_counter() - listen_started_at,
            trace_id,
        )

        performance.mark(
            "stt_listen_finished",
            trace_id,
        )

        if owns_trace:
            performance.finish(
                trace_id,
                outcome=outcome,
            )