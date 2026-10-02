"""Best-effort metadata-only pipeline logs. No AWS calls or metric dimensions."""
from __future__ import annotations

import asyncio
import math
import re
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field

from app.services.logging_service import get_logger

EVENTS = {
    "websocket_admission_completed", "transcribe_stream_started",
    "transcribe_result_received", "translation_operation_completed",
    "arbitration_or_buffer_completed", "websocket_caption_send_completed",
    "websocket_session_outcome",
}
CURRENT: ContextVar[PipelineTelemetry | None] = ContextVar("pipeline_telemetry", default=None)


def validate_benchmark_run_id(value: str | None) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value) else None


def error_type(error: BaseException | None) -> str | None:
    if error is None:
        return None
    name = type(error).__name__
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) else "Exception"


def duration_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def segment_id(value: str | None, mode: str | None, language: str | None = None) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"(?:vi-|en-)?seg-\d{1,16}", value):
        return None
    if mode == "dual" and value.startswith("seg-") and language in {"vi", "en"}:
        return f"{language}-{value}"
    return value


@dataclass
class PipelineTelemetry:
    benchmark_run_id: str | None = None
    session_id: str | None = None
    stream_mode: str | None = None
    source_language: str | None = None
    target_language: str | None = None
    started_at: float = field(default_factory=lambda: time.perf_counter())
    admitted: bool = False
    admission_logged: bool = False
    finished: bool = False
    auth_duration_ms: float | None = None
    admin_check_duration_ms: float | None = None
    registry_duration_ms: float | None = None
    quota_duration_ms: float | None = None
    quota_error_type: str | None = None
    audio_bytes_received: int = 0
    audio_frames_received: int = 0
    partial_count: int = 0
    final_count: int = 0
    translation_success_count: int = 0
    translation_failure_count: int = 0
    translation_skipped_count: int = 0
    partial_send_success_count: int = 0
    partial_send_failure_count: int = 0
    partial_send_duration_sum_ms: float = 0.0
    partial_send_duration_max_ms: float | None = None
    partial_send_error_type: str | None = None
    session_end_send_success: bool | None = None
    close_code: int | None = None
    failures: dict[str, str | None] = field(default_factory=dict)

    def emit(self, event: str, *, success: bool = True, duration_ms: float | None = None,
             error: BaseException | None = None, **metadata) -> None:
        """Callers pass only numeric metadata, closed enums, or validated IDs."""
        try:
            if event not in EVENTS:
                return
            task = asyncio.current_task()
            task_name = task.get_name() if task else None
        except RuntimeError:
            task_name = None
        try:
            task_name = task_name if task_name and re.fullmatch(r"Task-\d+", task_name) else None
            session = str(uuid.UUID(self.session_id)) if self.session_id else None
        except (ValueError, TypeError, AttributeError):
            session = None
        try:
            payload = {
                "schema_version": "1.0", "event": event,
                "benchmark_run_id": validate_benchmark_run_id(self.benchmark_run_id),
                "session_id": session, "segment_id": None,
                "stream_mode": self.stream_mode if self.stream_mode in {"single", "dual"} else None,
                "source_language": self.source_language if self.source_language in {"vi", "en", "vi-VN", "en-US"} else None,
                "target_language": self.target_language if self.target_language in {"vi", "en"} else None,
                "success": success if isinstance(success, bool) else False,
                "duration_ms": duration_ms if isinstance(duration_ms, (int, float))
                and not isinstance(duration_ms, bool) else None,
                "error_type": error_type(error),
                "asyncio_task": task_name,
            }
            # Never retain arbitrary extras or stringify an exception/object.
            allowed = {
                "segment_id", "stream_language", "direction", "outcome", "kind", "reason",
                "aggregate", "is_partial", "timestamp_start", "timestamp_end",
                "backend_received_offset_ms", "executor_queue_duration_ms", "sdk_call_duration_ms",
                "send_duration_ms", "attempt_count", "success_count", "failure_count",
                "duration_sum_ms", "duration_max_ms", "admitted", "auth_duration_ms",
                "admin_check_duration_ms", "registry_duration_ms", "quota_duration_ms",
                "total_admission_duration_ms", "quota_error_type", "audio_bytes_received",
                "audio_frames_received", "partial_count", "final_count", "translation_success_count",
                "translation_failure_count", "translation_skipped_count", "session_duration_ms",
                "session_end_send_success", "close_code", "close_reason", "error_type",
            }
            enums = {
                "stream_language": {"vi-VN", "en-US"},
                "direction": {"vi_to_en", "en_to_vi"},
                "outcome": {"admitted", "auth_rejected", "limit_rejected", "quota_rejected", "store_error",
                            "success", "client_disconnect", "timeout", "transcribe_failed",
                            "translation_degraded", "send_failed", "internal_error", "emitted", "dropped",
                            "translated", "failed", "skipped_empty", "cancelled"},
                "kind": {"partial", "final", "single_buffer", "dual_arbitration"},
                "reason": {"empty_text", "too_short", "too_few_words", "wrong_language_score",
                           "duplicate_within_2s", "lower_language_score_window_candidate", "empty_or_suspicious"},
                "close_reason": {"Normal closure", "Going away"},
            }
            boolean_fields = {"aggregate", "is_partial", "admitted", "session_end_send_success"}
            for key, value in metadata.items():
                if key not in allowed:
                    continue
                if value is None:
                    payload[key] = None
                elif key in enums:
                    payload[key] = value if isinstance(value, str) and value in enums[key] else None
                elif key == "segment_id":
                    payload[key] = segment_id(value, self.stream_mode)
                elif key in {"error_type", "quota_error_type"}:
                    payload[key] = value if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", value) else "Exception"
                elif key in boolean_fields:
                    payload[key] = value if isinstance(value, bool) else None
                else:
                    payload[key] = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
            payload["segment_id"] = segment_id(payload["segment_id"], self.stream_mode)
            for key, value in list(payload.items()):
                if isinstance(value, float) and not math.isfinite(value):
                    payload[key] = None
            get_logger().info(event, extra=payload)
        except Exception:
            # Formatting, filter, handler, and transport failures cannot fail a session.
            pass

    def admission(self, outcome: str, admission_start: float,
                  error: BaseException | None = None) -> None:
        if self.admission_logged:
            return
        self.admission_logged = True
        elapsed = duration_ms(admission_start)
        self.emit("websocket_admission_completed", success=outcome == "admitted",
                  duration_ms=elapsed, error=error, outcome=outcome,
                  admitted=self.admitted, auth_duration_ms=self.auth_duration_ms,
                  admin_check_duration_ms=self.admin_check_duration_ms,
                  registry_duration_ms=self.registry_duration_ms, quota_duration_ms=self.quota_duration_ms,
                  quota_error_type=self.quota_error_type,
                  error_type=error_type(error) or self.quota_error_type,
                  total_admission_duration_ms=elapsed)

    def fail(self, outcome: str, error: BaseException | None = None) -> None:
        self.failures.setdefault(outcome, error_type(error))

    def finish(self) -> None:
        if not self.admitted or self.finished:
            return
        self.finished = True
        if self.partial_count:
            self.emit("websocket_caption_send_completed", success=self.partial_send_failure_count == 0,
                      kind="partial", aggregate=True, attempt_count=self.partial_count,
                      success_count=self.partial_send_success_count, failure_count=self.partial_send_failure_count,
                      duration_sum_ms=self.partial_send_duration_sum_ms,
                      duration_max_ms=self.partial_send_duration_max_ms,
                      error_type=self.partial_send_error_type)
        outcome = next((cause for cause in (
            "internal_error", "transcribe_failed", "timeout", "client_disconnect", "send_failed",
            "translation_degraded") if cause in self.failures), "success")
        self.emit("websocket_session_outcome", success=outcome == "success", outcome=outcome,
                  error_type=self.failures.get(outcome), session_duration_ms=duration_ms(self.started_at),
                  audio_bytes_received=self.audio_bytes_received, audio_frames_received=self.audio_frames_received,
                  partial_count=self.partial_count, final_count=self.final_count,
                  translation_success_count=self.translation_success_count,
                  translation_failure_count=self.translation_failure_count,
                  translation_skipped_count=self.translation_skipped_count,
                  session_end_send_success=self.session_end_send_success,
                  close_code=self.close_code, close_reason=None)


def context(session_id: str | None = None) -> PipelineTelemetry:
    return CURRENT.get() or PipelineTelemetry(session_id=session_id, stream_mode="single")
