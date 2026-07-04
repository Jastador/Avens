"""Local performance tracing for Avens.

Writes compact JSONL traces locally so startup, voice, camera, model, and TTS
latency can be measured without sending any telemetry anywhere.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from dotenv import load_dotenv
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Iterator
import uuid

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(
    PROJECT_ROOT / ".env",
    override=False,
)

def _env_flag(name: str, default: bool = False) -> bool:
    """Read a simple true/false environment setting."""
    default_text = "true" if default else "false"

    return os.getenv(name, default_text).strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _safe_json_value(value: Any) -> Any:
    """Convert small trace values into JSON-safe data."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): _safe_json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]

    return str(value)


@dataclass
class _Span:
    """One nested timed section inside a turn."""

    span_id: str
    name: str
    started_at: float
    metadata: dict[str, Any] = field(default_factory=dict)
    marks: dict[str, float] = field(default_factory=dict)
    outcome: str = "running"
    duration_seconds: float | None = None


@dataclass
class _Trace:
    """One complete user turn, boot sequence, or camera startup."""

    trace_id: str
    kind: str
    started_at: float
    started_at_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)
    marks: dict[str, float] = field(default_factory=dict)
    stages: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    spans: list[_Span] = field(default_factory=list)
    outcome: str = "running"


class PerformanceMonitor:
    """Thread-safe local recorder for Avens timing traces."""

    def __init__(self) -> None:
        self._enabled = _env_flag("AVENS_PERF_ENABLED", default=False)
        self._log_prompts = _env_flag(
            "AVENS_PERF_LOG_PROMPTS",
            default=False,
        )

        raw_log_dir = os.getenv(
            "AVENS_PERF_LOG_DIR",
            "logs/performance",
        ).strip()

        project_root = PROJECT_ROOT
        configured_dir = Path(raw_log_dir)

        self._log_dir = (
            configured_dir
            if configured_dir.is_absolute()
            else project_root / configured_dir
        )

        self._lock = threading.RLock()
        self._thread_state = threading.local()
        self._traces: dict[str, _Trace] = {}
        self._spans: dict[str, tuple[str, _Span]] = {}

    @property
    def enabled(self) -> bool:
        """Return whether local timing collection is currently enabled."""
        return self._enabled

    def begin(
        self,
        kind: str,
        metadata: dict[str, Any] | None = None,
        *,
        make_current: bool = True,
    ) -> str | None:
        """Start one trace and optionally attach it to this thread."""
        if not self._enabled:
            return None

        previous_trace_id = self.current_trace_id()

        if make_current and previous_trace_id:
            self.finish(
                previous_trace_id,
                outcome="superseded",
            )

        trace_id = uuid.uuid4().hex[:10]
        trace = _Trace(
            trace_id=trace_id,
            kind=" ".join(str(kind).split()) or "unknown",
            started_at=time.perf_counter(),
            started_at_utc=datetime.now(timezone.utc).isoformat(),
            metadata={
                key: _safe_json_value(value)
                for key, value in (metadata or {}).items()
            },
        )

        with self._lock:
            self._traces[trace_id] = trace

        if make_current:
            self._thread_state.current_trace_id = trace_id

        return trace_id

    def current_trace_id(self) -> str | None:
        """Return the active trace associated with this thread."""
        return getattr(self._thread_state, "current_trace_id", None)

    def mark(
        self,
        name: str,
        trace_id: str | None = None,
        *,
        only_once: bool = False,
    ) -> None:
        """Store a named timestamp relative to trace start."""
        trace = self._get_trace(trace_id)

        if trace is None:
            return

        key = " ".join(str(name).split())

        if not key:
            return

        with self._lock:
            if only_once and key in trace.marks:
                return

            trace.marks[key] = time.perf_counter() - trace.started_at

    def record_stage(
        self,
        name: str,
        seconds: float,
        trace_id: str | None = None,
    ) -> None:
        """Store a completed duration inside the active trace."""
        trace = self._get_trace(trace_id)

        if trace is None:
            return

        key = " ".join(str(name).split())

        if not key:
            return

        with self._lock:
            trace.stages[key] = max(0.0, float(seconds))

    def add_metric(
        self,
        name: str,
        value: Any,
        trace_id: str | None = None,
    ) -> None:
        """Store an extra numeric or text metric."""
        trace = self._get_trace(trace_id)

        if trace is None:
            return

        key = " ".join(str(name).split())

        if not key:
            return

        with self._lock:
            trace.metrics[key] = _safe_json_value(value)

    def add_metadata(
        self,
        values: dict[str, Any],
        trace_id: str | None = None,
    ) -> None:
        """Attach extra context without storing the raw user prompt by default."""
        trace = self._get_trace(trace_id)

        if trace is None:
            return

        with self._lock:
            for key, value in values.items():
                trace.metadata[str(key)] = _safe_json_value(value)

    def add_prompt_metadata(
        self,
        prompt: str,
        trace_id: str | None = None,
    ) -> None:
        """Store prompt length, and raw prompt only when explicitly enabled."""
        trace = self._get_trace(trace_id)

        if trace is None:
            return

        clean_prompt = str(prompt).strip()

        self.add_metadata(
            {
                "prompt_characters": len(clean_prompt),
            },
            trace_id=trace_id,
        )

        if self._log_prompts:
            self.add_metadata(
                {
                    "prompt": clean_prompt,
                },
                trace_id=trace_id,
            )

    def begin_span(
        self,
        name: str,
        trace_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Start a nested timed span such as one TTS call."""
        trace = self._get_trace(trace_id)

        if trace is None:
            return None

        span_id = uuid.uuid4().hex[:10]
        span = _Span(
            span_id=span_id,
            name=" ".join(str(name).split()) or "unnamed",
            started_at=time.perf_counter(),
            metadata={
                key: _safe_json_value(value)
                for key, value in (metadata or {}).items()
            },
        )

        with self._lock:
            trace.spans.append(span)
            self._spans[span_id] = (trace.trace_id, span)

        return span_id

    def mark_span(
        self,
        span_id: str | None,
        name: str,
        *,
        only_once: bool = False,
    ) -> None:
        """Store a timestamp relative to one nested span."""
        if span_id is None:
            return

        with self._lock:
            record = self._spans.get(span_id)

            if record is None:
                return

            _, span = record
            key = " ".join(str(name).split())

            if not key:
                return

            if only_once and key in span.marks:
                return

            span.marks[key] = time.perf_counter() - span.started_at

    def finish_span(
        self,
        span_id: str | None,
        outcome: str = "ok",
    ) -> None:
        """Close one nested timed span."""
        if span_id is None:
            return

        with self._lock:
            record = self._spans.pop(span_id, None)

            if record is None:
                return

            _, span = record
            span.duration_seconds = max(
                0.0,
                time.perf_counter() - span.started_at,
            )
            span.outcome = outcome

    @contextmanager
    def measure(
        self,
        name: str,
        trace_id: str | None = None,
    ) -> Iterator[None]:
        """Measure one simple synchronous stage."""
        started_at = time.perf_counter()

        try:
            yield
        finally:
            self.record_stage(
                name,
                time.perf_counter() - started_at,
                trace_id=trace_id,
            )

    def finish(
        self,
        trace_id: str | None = None,
        *,
        outcome: str = "ok",
    ) -> None:
        """Write one complete trace to disk and print a compact summary."""
        if not self._enabled:
            return

        resolved_trace_id = trace_id or self.current_trace_id()

        if not resolved_trace_id:
            return

        with self._lock:
            trace = self._traces.pop(resolved_trace_id, None)

            if trace is None:
                return

            trace.outcome = outcome
            total_seconds = max(
                0.0,
                time.perf_counter() - trace.started_at,
            )

            for span in trace.spans:
                if span.duration_seconds is None:
                    span.duration_seconds = max(
                        0.0,
                        time.perf_counter() - span.started_at,
                    )
                    span.outcome = "unfinished"

                self._spans.pop(span.span_id, None)

            current_trace_id = self.current_trace_id()

            if current_trace_id == resolved_trace_id:
                self._thread_state.current_trace_id = None

        self._add_derived_metrics(trace)
        self._write_trace(trace, total_seconds)
        self._print_summary(trace, total_seconds)

    def _get_trace(self, trace_id: str | None) -> _Trace | None:
        """Resolve an explicit trace ID or the active trace for this thread."""
        if not self._enabled:
            return None

        resolved_trace_id = trace_id or self.current_trace_id()

        if not resolved_trace_id:
            return None

        with self._lock:
            return self._traces.get(resolved_trace_id)

    @staticmethod
    def _add_derived_metrics(trace: _Trace) -> None:
        """Calculate user-visible latency from recorded timestamps."""
        speech_end = trace.marks.get("user_speech_end")
        first_answer_audio = trace.marks.get("first_answer_audio")

        if speech_end is not None and first_answer_audio is not None:
            trace.metrics[
                "speech_end_to_first_answer_audio_seconds"
            ] = max(
                0.0,
                first_answer_audio - speech_end,
            )

        result_markers = (
            (
                "camera_result_first_audio",
                "speech_end_to_camera_result_audio_seconds",
            ),
            (
                "lens_result_first_audio",
                "speech_end_to_lens_result_audio_seconds",
            ),
        )

        for marker_name, metric_name in result_markers:
            result_audio = trace.marks.get(marker_name)

            if speech_end is not None and result_audio is not None:
                trace.metrics[metric_name] = max(
                    0.0,
                    result_audio - speech_end,
                )

        camera_frame_ready = trace.marks.get("camera_frame_ready")
        camera_result_audio = trace.marks.get(
            "camera_result_first_audio",
        )

        if (
            camera_frame_ready is not None
            and camera_result_audio is not None
        ):
            trace.metrics[
                "camera_frame_to_result_audio_seconds"
            ] = max(
                0.0,
                camera_result_audio - camera_frame_ready,
            )

        brain_first_token = trace.marks.get(
            "brain_first_token",
        )

        brain_first_text = trace.marks.get(
            "brain_first_text_event",
        )

        brain_tts_started = trace.marks.get(
            "brain_response_tts_started",
        )

        brain_audio_ready = trace.marks.get(
            "brain_response_audio_chunk_ready",
        )

        brain_audio_queued = trace.marks.get(
            "brain_response_first_audio",
        )

        if (
            brain_first_token is not None
            and brain_first_text is not None
        ):
            trace.metrics[
                "brain_first_token_to_first_text_seconds"
            ] = max(
                0.0,
                brain_first_text - brain_first_token,
            )

        if (
            brain_first_text is not None
            and brain_tts_started is not None
        ):
            trace.metrics[
                "brain_first_text_to_tts_start_seconds"
            ] = max(
                0.0,
                brain_tts_started - brain_first_text,
            )

        if (
            brain_tts_started is not None
            and brain_audio_ready is not None
        ):
            trace.metrics[
                "brain_tts_start_to_audio_ready_seconds"
            ] = max(
                0.0,
                brain_audio_ready - brain_tts_started,
            )

        if (
            brain_first_text is not None
            and brain_audio_queued is not None
        ):
            trace.metrics[
                "brain_first_text_to_audio_seconds"
            ] = max(
                0.0,
                brain_audio_queued - brain_first_text,
            )

    def _write_trace(
        self,
        trace: _Trace,
        total_seconds: float,
    ) -> None:
        """Append one compact local JSON object to today's trace file."""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)

            date_stamp = datetime.now().strftime("%Y%m%d")
            log_path = self._log_dir / f"performance_{date_stamp}.jsonl"

            record = {
                "timestamp_utc": trace.started_at_utc,
                "trace_id": trace.trace_id,
                "kind": trace.kind,
                "outcome": trace.outcome,
                "total_seconds": round(total_seconds, 6),
                "metadata": trace.metadata,
                "marks_seconds_from_start": {
                    key: round(value, 6)
                    for key, value in trace.marks.items()
                },
                "stages_seconds": {
                    key: round(value, 6)
                    for key, value in trace.stages.items()
                },
                "metrics": trace.metrics,
                "spans": [
                    {
                        "name": span.name,
                        "outcome": span.outcome,
                        "duration_seconds": round(
                            span.duration_seconds or 0.0,
                            6,
                        ),
                        "metadata": span.metadata,
                        "marks_seconds_from_span_start": {
                            key: round(value, 6)
                            for key, value in span.marks.items()
                        },
                    }
                    for span in trace.spans
                ],
            }

            with log_path.open(
                "a",
                encoding="utf-8",
            ) as log_file:
                log_file.write(json.dumps(record) + "\n")

        except Exception as error:
            print(f"⚠️ Performance log write failed: {error}")

    @staticmethod
    def _print_summary(
        trace: _Trace,
        total_seconds: float,
    ) -> None:
        """Print the most useful latency stages for the completed trace."""
        priority_stage_names = (
            # Local-brain streaming path
            "brain_time_to_first_token_seconds",
            "brain_time_to_first_text_event_seconds",
            "tts_brain_response_time_to_first_audio_seconds",
            "stt_silence_tail_seconds",
            "stt_decode_seconds",
            "intent_routing_seconds",
            "brain_ollama_request_open_seconds",
            "brain_ollama_model_load_seconds",
            "brain_ollama_prompt_eval_seconds",
            "brain_ollama_answer_eval_seconds",
            "tts_time_to_first_audio_seconds",

            # Camera / Lens path
            "tts_camera_instruction_time_to_first_audio_seconds",
            "tts_camera_result_time_to_first_audio_seconds",
            "tts_lens_instruction_time_to_first_audio_seconds",
            "tts_lens_result_time_to_first_audio_seconds",
            "camera_wait_for_fresh_frame_seconds",
            "camera_autofocus_settle_seconds",
            "camera_hold_seconds",
            "local_vision_prepare_seconds",
            "local_vision_encode_seconds",
            "local_vision_model_load_seconds",
            "local_vision_image_prompt_seconds",
            "local_vision_answer_eval_seconds",

            # App boot
            "boot_module_import_to_main_seconds",
            "boot_stt_model_init_seconds",
            "boot_tts_module_import_seconds",
            "boot_brain_module_import_seconds",
            "boot_commands_module_import_seconds",
            "boot_wake_module_import_seconds",
            "boot_runtime_modules_seconds",
            "boot_loop_thread_start_seconds",
            "boot_ui_import_seconds",
            "boot_qt_application_create_seconds",
            "boot_orb_create_seconds",
            "boot_ui_show_request_seconds",

            # Wake word
            "wake_model_load_seconds",
            "wake_recognizer_create_seconds",
            "wake_microphone_lookup_seconds",
            "wake_microphone_lock_wait_seconds",
            "wake_stream_open_seconds",
            "wake_final_block_recognition_seconds",
        )

        selected_stages = [
            (name, trace.stages[name])
            for name in priority_stage_names
            if name in trace.stages
        ]

        if not selected_stages:
            selected_stages = list(trace.stages.items())[:8]

        stage_text = " | ".join(
            f"{name}={seconds:.2f}s"
            for name, seconds in selected_stages[:12]
        )

        first_audio = trace.metrics.get(
            "speech_end_to_first_answer_audio_seconds",
        )

        latency_text = (
            f"speech→audio={float(first_audio):.2f}s"
            if isinstance(first_audio, (int, float))
            else ""
        )

        pieces = [
            f"⏱️ PERF [{trace.kind}]",
            f"total={total_seconds:.2f}s",
            latency_text,
            stage_text,
        ]

        print(" | ".join(piece for piece in pieces if piece))

# Shared process-wide monitor used by all Avens modules.
performance = PerformanceMonitor()