#!/usr/bin/env python3
"""Client-only LiveCap benchmark; definitions: docs/benchmark-harness.md.

Legacy --url/--concurrency/--duration/--ramp sends silent PCM. Speech metrics
require --audio-file. Never calls wake or AWS APIs. Public deployments require
separate run authorization.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import importlib.metadata
import io
import json
import logging
import math
import os
import platform
import re
import ssl
import statistics
import subprocess
import tempfile
import time
import uuid
import wave
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2
FRAME_SAMPLES = 1_600
SCHEMA_VERSION = "1.0"
# A private disabled logger prevents library debug output echoing auth headers.
TRANSPORT_LOGGER = logging.Logger("livecap.benchmark.transport")
TRANSPORT_LOGGER.disabled = True
TRANSPORT_LOGGER.propagate = False
OUTCOMES = (
    "success", "auth_rejected", "limit_rejected", "quota_rejected",
    "admission_error", "transcribe_failed", "translation_degraded",
    "unexpected_disconnect", "timeout", "client_error",
)
SERVER_CODES = {
    "UNAUTHORIZED", "TOO_MANY_SESSIONS", "QUOTA_EXCEEDED", "TRANSCRIBE_ERROR",
    "TRANSLATE_ERROR", "SESSION_TIMEOUT", "INVALID_AUDIO_FORMAT",
    "INVALID_LANGUAGE_MODE", "INVALID_ROOM", "INTERNAL_ERROR",
}
ATTEMPT_LATENCIES = (
    "transport_handshake_ms", "session_admission_ms", "connect_to_session_start_ms",
    "time_to_first_partial_ms", "time_to_first_final_ms",
)


def redact(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    """Redact exact secrets (also URL encoded) and JWT-like strings recursively."""
    if isinstance(value, str):
        for secret in sorted((s for s in secrets if s), key=len, reverse=True):
            for representation in (secret, quote(secret, safe=""), quote_plus(secret)):
                value = value.replace(representation, "[REDACTED]")
        return re.sub(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
                      "[REDACTED]", value)
    if isinstance(value, dict):
        return {redact(k, secrets): redact(v, secrets) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [redact(v, secrets) for v in value]
    return value


def sanitized_url(url: str) -> str:
    """Evidence retains no URL credentials, query values or fragment."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    authority = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, authority, parts.path, "", ""))


@dataclass(frozen=True)
class AudioFixture:
    mode: str
    samples: int
    path: Path | None = None
    sha256: str | None = None
    pcm_sha256: str | None = None

    @property
    def duration(self) -> float:
        return self.samples / SAMPLE_RATE

    def frames(self) -> Iterator[tuple[int, bytes]]:
        if self.path is None:
            for start in range(0, self.samples, FRAME_SAMPLES):
                yield start, bytes(min(FRAME_SAMPLES, self.samples - start) * SAMPLE_WIDTH)
            return
        with wave.open(str(self.path), "rb") as wav:
            start = 0
            while start < self.samples:
                data = wav.readframes(min(FRAME_SAMPLES, self.samples - start))
                if not data or len(data) % SAMPLE_WIDTH:
                    raise ValueError("WAV changed or was truncated during replay")
                yield start, data
                start += len(data) // SAMPLE_WIDTH


def validate_wav(path: Path) -> AudioFixture:
    """Validate full PCM payload and hash with bounded reads before connections."""
    try:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(64 * 1024), b""):
                digest.update(block)
        with wave.open(str(path), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(),
                    wav.getcomptype()) != (1, 2, 16_000, "NONE"):
                raise ValueError("WAV must be mono, signed PCM 16-bit, 16000 Hz")
            samples = wav.getnframes()
            if samples <= 0:
                raise ValueError("WAV must contain audio samples")
            pcm_digest = hashlib.sha256()
            read_bytes = 0
            while block := wav.readframes(32_768):
                read_bytes += len(block)
                pcm_digest.update(block)
            if read_bytes != samples * SAMPLE_WIDTH:
                raise ValueError("WAV PCM payload is truncated")
    except (OSError, EOFError, wave.Error) as exc:
        raise ValueError("Cannot read a valid PCM WAV fixture") from exc
    return AudioFixture("wav", samples, path, digest.hexdigest(), pcm_digest.hexdigest())


@dataclass(frozen=True)
class Config:
    url: str
    concurrency: int = 8
    duration: float = 8.0
    ramp: float = 0.2
    source: str = "vi-VN"
    target: str = "en"
    stream_mode: str = "dual"
    connect_timeout: float = 30.0
    first_caption_timeout: float = 30.0
    shutdown_timeout: float = 10.0
    send_timeout: float = 10.0
    warmup_sessions: int = 0
    insecure: bool = False
    auth: bool = False
    token: str = field(default="", repr=False)
    run_id: str = ""
    scenario: str = "unspecified"


def connection_url(config: Config) -> str:
    if config.token and any(secret in config.url for secret in (
            config.token, quote(config.token, safe=""), quote_plus(config.token))):
        raise ValueError("Access tokens must never appear in the target URL")
    parts = urlsplit(config.url)
    if (parts.scheme not in {"ws", "wss"} or not parts.hostname or
            parts.username is not None or parts.password is not None or parts.fragment):
        raise ValueError("Target must be ws:// or wss:// without credentials or fragment")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if set(query) - {"source", "target", "stream_mode", "benchmark_run_id"}:
        raise ValueError("URL query allows only language, stream mode and benchmark correlation")
    query.update(source=config.source, target=config.target)
    query.setdefault("stream_mode", config.stream_mode)
    query.pop("benchmark_run_id", None)
    # Only metadata-safe correlation labels enter the URL, never the token.
    run_id = config.run_id
    if (re.fullmatch(r"[A-Za-z0-9._-]{1,64}", run_id) and
            not (config.token and config.token in run_id) and
            not re.search(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", run_id)):
        query["benchmark_run_id"] = run_id
    if query["stream_mode"] not in {"single", "dual"}:
        raise ValueError("Invalid stream mode")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


class Clock:
    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


def scheduled_send_time(origin: float, sample_start: int) -> float:
    return origin + sample_start / SAMPLE_RATE


async def pace(clock: Clock, deadline: float) -> float:
    await clock.sleep(max(0.0, deadline - clock.now()))
    return clock.now()


@dataclass
class FrameTiming:
    frame_index: int
    sample_start: int
    sample_end: int
    scheduled_send_offset_ms: float
    actual_send_offset_ms: float
    send_complete_offset_ms: float | None = None
    pacing_drift_ms: float = 0.0
    sent: bool = False


@dataclass
class SegmentResult:
    attempt_id: str
    segment_id: str | None
    timestamp_start: float | None
    timestamp_end: float | None
    received_offset_ms: float
    mapped_audio_end_offset_ms: float | None = None
    finalized_caption_lag_ms: float | None = None
    lag_status: str = "unavailable"
    lag_reason: str | None = None
    source_text_present: bool = False
    target_text_present: bool = False
    valid_finalized_segment: bool = False


@dataclass
class AttemptResult:
    attempt_id: str
    phase: str = "measured"
    outcome: str | None = None
    failure_kind: str | None = None
    diagnostic: str | None = None
    session_id: str | None = None
    handshake_completed: bool = False
    admitted: bool = False
    full_audio_sent: bool = False
    stop_sent: bool = False
    session_end_received: bool = False
    session_end_after_stop: bool = False
    expected_close: bool = False
    unexpected_disconnect: bool = False
    close_code: int | None = None
    close_reason: str | None = None
    close_initiator: str | None = None
    server_error_codes: list[str] = field(default_factory=list)
    attempt_start_offset_ms: float = 0.0  # Relative to measured/warmup phase origin.
    transport_connect_started_offset_ms: float | None = None
    handshake_complete_offset_ms: float | None = None  # Remaining offsets: attempt origin.
    session_start_received_offset_ms: float | None = None
    audio_streaming_start_offset_ms: float | None = None
    audio_streaming_end_offset_ms: float | None = None
    stop_send_started_offset_ms: float | None = None
    stop_sent_offset_ms: float | None = None
    session_end_received_offset_ms: float | None = None
    socket_closed_offset_ms: float | None = None
    transport_handshake_ms: float | None = None
    session_admission_ms: float | None = None
    connect_to_session_start_ms: float | None = None
    time_to_first_partial_ms: float | None = None
    time_to_first_final_ms: float | None = None
    total_messages_received: int = 0
    partial_segments_received: int = 0
    finalized_segments_received: int = 0
    unique_finalized_segments: int = 0
    control_messages_received: int = 0
    bytes_sent: int = 0  # PCM payload only, no control/transport overhead.
    audio_frames_sent: int = 0
    audio_seconds_scheduled: float = 0.0
    audio_seconds_sent: float = 0.0
    wall_time_seconds: float = 0.0
    pacing_drift_max_ms: float | None = None
    pacing_drift_p95_ms: float | None = None
    frames: list[FrameTiming] = field(default_factory=list)
    segments: list[SegmentResult] = field(default_factory=list)


class AdmissionBarrier:
    """Release after every admission verdict, including failures."""
    def __init__(self, attempts: int) -> None:
        self.remaining = attempts
        self.ready = asyncio.Event()

    def arrive(self) -> None:
        self.remaining -= 1
        if self.remaining == 0:
            self.ready.set()


class ConcurrencyTracker:
    def __init__(self, clock: Clock, origin: float) -> None:
        self.clock = clock
        self.origin = origin
        self.active: set[str] = set()
        self.peak = 0
        self.events: list[dict[str, Any]] = []

    def change(self, attempt_id: str, active: bool) -> None:
        if active:
            self.active.add(attempt_id)
        else:
            if attempt_id not in self.active:
                return
            self.active.remove(attempt_id)
        self.peak = max(self.peak, len(self.active))
        self.events.append({"offset_ms": (self.clock.now() - self.origin) * 1000,
                            "attempt_id": attempt_id,
                            "observed_active_sessions": len(self.active)})


def nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if not 0 < percentile <= 100:
        raise ValueError("Percentile must be in (0, 100]")
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * percentile / 100) - 1]


def metric_summary(values: list[float | None]) -> dict[str, Any]:
    valid = [value for value in values if value is not None and math.isfinite(value)]
    return {
        "valid_count": len(valid), "missing_count": len(values) - len(valid),
        "min": min(valid) if valid else None,
        "mean": statistics.fmean(valid) if valid else None,
        "p50": nearest_rank(valid, 50), "p95": nearest_rank(valid, 95),
        "p99": nearest_rank(valid, 99), "max": max(valid) if valid else None,
    }


def numeric_timestamp(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return float(value) if math.isfinite(value) else None


def map_audio_end(segment: SegmentResult, attempt: AttemptResult,
                  audio: AudioFixture) -> None:
    if audio.mode != "wav":
        segment.lag_reason = "silent_mode"
        return
    end = segment.timestamp_end
    if end is None:
        segment.lag_reason = "missing_or_non_numeric_timestamp"
        return
    if end <= 0 or end > audio.duration:
        segment.lag_status = "invalid"
        segment.lag_reason = "timestamp_outside_fixture"
        return
    if segment.timestamp_start is not None and (
            segment.timestamp_start < 0 or segment.timestamp_start > end):
        segment.lag_status = "invalid"
        segment.lag_reason = "invalid_timestamp_order"
        return
    sample_end = end * SAMPLE_RATE
    for frame in attempt.frames:
        # At an exact frame boundary choose the preceding frame's last sample.
        if (frame.sent and frame.sample_start < sample_end <= frame.sample_end and
                frame.actual_send_offset_ms <= segment.received_offset_ms):
            mapped = (frame.actual_send_offset_ms +
                      (sample_end - frame.sample_start) / SAMPLE_RATE * 1000)
            segment.mapped_audio_end_offset_ms = mapped
            segment.finalized_caption_lag_ms = segment.received_offset_ms - mapped
            segment.lag_status = "valid"
            segment.lag_reason = None
            return
    segment.lag_reason = "audio_not_sent_at_receipt"


def record_message(attempt: AttemptResult, message: dict[str, Any],
                   offset_ms: float, mode: str, secrets: tuple[str, ...]) -> bool:
    """Store presence/counts only; no transcripts or server exception messages."""
    attempt.total_messages_received += 1
    kind = message.get("type")
    language = message.get("spoken_language")
    source = message.get("text_vi" if language == "vi" else "text_en")
    target = message.get("text_en" if language == "vi" else "text_vi")
    source_present = isinstance(source, str) and bool(source.strip())
    target_present = isinstance(target, str) and bool(target.strip())
    audio_start = attempt.audio_streaming_start_offset_ms
    if kind == "partial_segment":
        attempt.partial_segments_received += 1
        if (mode == "wav" and source_present and language in {"vi", "en"} and
                audio_start is not None and attempt.time_to_first_partial_ms is None):
            attempt.time_to_first_partial_ms = offset_ms - audio_start
        return source_present and language in {"vi", "en"}
    if kind == "finalized_segment":
        attempt.finalized_segments_received += 1
        raw_id = message.get("segment_id")
        segment_id = (redact(raw_id, secrets) if isinstance(raw_id, str) and
                      re.fullmatch(r"(?:vi-|en-)?seg-\d+", raw_id) else None)
        valid = (segment_id is not None and source_present and language in {"vi", "en"}
                 and message.get("is_final", True) is True)
        attempt.segments.append(SegmentResult(
            attempt_id=attempt.attempt_id, segment_id=segment_id,
            timestamp_start=numeric_timestamp(message.get("timestamp_start")),
            timestamp_end=numeric_timestamp(message.get("timestamp_end")),
            received_offset_ms=offset_ms, source_text_present=source_present,
            target_text_present=target_present, valid_finalized_segment=valid,
        ))
        if mode == "wav" and valid and audio_start is not None:
            if attempt.time_to_first_final_ms is None:
                attempt.time_to_first_final_ms = offset_ms - audio_start
        return valid
    attempt.control_messages_received += 1
    if kind == "error":
        raw_code = message.get("code")
        code = raw_code if isinstance(raw_code, str) and raw_code in SERVER_CODES else "UNKNOWN_SERVER_ERROR"
        attempt.server_error_codes.append(code)
    return False


def terminal_outcome(attempt: AttemptResult, mode: str) -> str:
    """A single terminal category. Explicit causes precede incidental cleanup."""
    codes = set(attempt.server_error_codes)
    for code, outcome in (("UNAUTHORIZED", "auth_rejected"),
                          ("TOO_MANY_SESSIONS", "limit_rejected"),
                          ("QUOTA_EXCEEDED", "quota_rejected"),
                          ("TRANSCRIBE_ERROR", "transcribe_failed"),
                          ("SESSION_TIMEOUT", "timeout")):
        if code in codes:
            return outcome
    if codes - {"TRANSLATE_ERROR"}:
        return "client_error" if attempt.admitted else "admission_error"
    if attempt.failure_kind is not None:
        return attempt.failure_kind
    if attempt.unexpected_disconnect:
        return "unexpected_disconnect" if attempt.admitted else "admission_error"
    base_success = (attempt.handshake_completed and attempt.admitted and
                    attempt.full_audio_sent and attempt.stop_sent and
                    attempt.session_end_received and attempt.session_end_after_stop)
    if not base_success:
        return "client_error" if attempt.admitted else "admission_error"
    if mode == "wav":
        if not any(s.valid_finalized_segment for s in attempt.segments):
            return "client_error"
        if ("TRANSLATE_ERROR" in codes or
                any(s.source_text_present and not s.target_text_present for s in attempt.segments)):
            return "translation_degraded"
    elif "TRANSLATE_ERROR" in codes:
        return "translation_degraded"
    return "success"


def is_closed_exception(exc: Exception) -> bool:
    return (isinstance(exc, (ConnectionError, EOFError)) or
            any(cls.__name__.startswith("ConnectionClosed") for cls in type(exc).__mro__))


def parse_message(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise ValueError("Expected JSON text message")
    message = json.loads(raw)
    if not isinstance(message, dict):
        raise ValueError("Expected JSON object message")
    return message


async def one_session(config: Config, audio: AudioFixture, attempt_id: str,
                      tracker: ConcurrencyTracker, connector: Callable[..., Any],
                      clock: Clock, barrier: AdmissionBarrier | None = None,
                      phase: str = "measured") -> AttemptResult:
    start = clock.now()
    attempt = AttemptResult(attempt_id, phase=phase,
                            attempt_start_offset_ms=(start - tracker.origin) * 1000,
                            audio_seconds_scheduled=audio.duration)
    socket = None
    arrived = False
    tasks: list[asyncio.Task] = []
    secrets = (config.token,)
    stop_started = False
    first_caption = asyncio.Event()
    session_end = asyncio.Event()

    def offset() -> float:
        return (clock.now() - start) * 1000

    def observe_close(exc: Exception) -> None:
        attempt.socket_closed_offset_ms = offset()
        attempt.close_initiator = "remote"
        # Modern websockets exposes the received close frame. Its legacy
        # exception .code/.reason properties warn (and fail under -W error).
        received_close = getattr(exc, "rcvd", None)
        websocket_exception = any(cls.__name__.startswith("ConnectionClosed")
                                  for cls in type(exc).__mro__)
        code = getattr(socket, "close_code", None)
        if code is None:
            code = (getattr(received_close, "code", 1006) if websocket_exception
                    else getattr(exc, "code", None))
        attempt.close_code = code if isinstance(code, int) else None
        raw_reason = getattr(socket, "close_reason", None)
        if raw_reason is None:
            raw_reason = (getattr(received_close, "reason", "") if websocket_exception
                          else getattr(exc, "reason", ""))
        safe_reason = redact(raw_reason, secrets) if isinstance(raw_reason, str) else ""
        attempt.close_reason = (safe_reason if safe_reason in {"", "Normal closure",
                                "Going away", "[REDACTED]"} else "[OMITTED]")
        attempt.unexpected_disconnect = (not attempt.session_end_after_stop or
                                         attempt.close_code not in {1000, 1001})
        tracker.change(attempt_id, False)

    async def receive() -> None:
        while True:
            try:
                raw = await socket.recv()
            except Exception as exc:
                if is_closed_exception(exc):
                    observe_close(exc)
                    return
                raise
            received = offset()  # Before JSON parsing, never after stream/drain.
            message = parse_message(raw)
            usable = record_message(attempt, message, received, audio.mode, secrets)
            if usable and attempt.audio_streaming_start_offset_ms is not None:
                first_caption.set()
            if message.get("type") == "session_end":
                attempt.session_end_received = True
                attempt.session_end_received_offset_ms = received
                attempt.session_end_after_stop = stop_started
                session_end.set()
                if not stop_started:
                    attempt.failure_kind = "client_error"
                    attempt.diagnostic = "session_end_before_stop"
                    return
            if (message.get("type") == "error" and
                    attempt.server_error_codes[-1] != "TRANSLATE_ERROR"):
                return

    async def send() -> None:
        nonlocal stop_started
        origin = clock.now()
        attempt.audio_streaming_start_offset_ms = (origin - start) * 1000
        pcm_digest = hashlib.sha256()

        async def send_frame(index: int, sample_start: int, data: bytes,
                             scheduled: float) -> None:
            actual = clock.now()
            timing = FrameTiming(index, sample_start, sample_start + len(data) // 2,
                                 (scheduled - start) * 1000, (actual - start) * 1000,
                                 pacing_drift_ms=(actual - scheduled) * 1000)
            attempt.frames.append(timing)
            await socket.send(data)
            timing.send_complete_offset_ms = offset()
            timing.sent = True

        for index, (sample_start, data) in enumerate(audio.frames()):
            scheduled = scheduled_send_time(origin, sample_start)
            await pace(clock, scheduled)
            await asyncio.wait_for(send_frame(index, sample_start, data, scheduled), config.send_timeout)
            pcm_digest.update(data)
            attempt.bytes_sent += len(data)
            attempt.audio_frames_sent += 1
            attempt.audio_seconds_sent = attempt.bytes_sent / (SAMPLE_RATE * SAMPLE_WIDTH)
        if audio.pcm_sha256 is not None and pcm_digest.hexdigest() != audio.pcm_sha256:
            raise ValueError("WAV PCM changed after preflight")
        attempt.full_audio_sent = attempt.bytes_sent == audio.samples * SAMPLE_WIDTH
        await pace(clock, origin + audio.duration)  # Include final frame sample span.
        attempt.audio_streaming_end_offset_ms = offset()
        stop_started = True
        attempt.stop_send_started_offset_ms = offset()
        await asyncio.wait_for(socket.send(json.dumps({"type": "stop"})), config.send_timeout)
        attempt.stop_sent = True
        attempt.stop_sent_offset_ms = offset()

    async def caption_deadline() -> None:
        await asyncio.wait_for(first_caption.wait(), config.first_caption_timeout)

    try:
        ssl_ctx = None
        if config.url.startswith("wss://"):
            ssl_ctx = ssl.create_default_context()
            if config.insecure:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
        kwargs: dict[str, Any] = {"ssl": ssl_ctx, "max_size": None,
                                  "open_timeout": config.connect_timeout,
                                  "close_timeout": config.shutdown_timeout,
                                  "logger": TRANSPORT_LOGGER}
        if config.auth:
            kwargs["subprotocols"] = ["livecap.v1", config.token]
        target_url = connection_url(config)
        async with asyncio.timeout(config.connect_timeout):
            attempt.transport_connect_started_offset_ms = offset()
            socket = await connector(target_url, **kwargs)
            attempt.handshake_completed = True
            attempt.handshake_complete_offset_ms = offset()
            attempt.transport_handshake_ms = (attempt.handshake_complete_offset_ms -
                                               attempt.transport_connect_started_offset_ms)
            if config.auth and getattr(socket, "subprotocol", None) != "livecap.v1":
                attempt.failure_kind = "admission_error"
                attempt.diagnostic = "auth_subprotocol_not_negotiated"
                return attempt
            raw = await socket.recv()
            received = offset()
            first = parse_message(raw)
            record_message(attempt, first, received, audio.mode, secrets)
            if first.get("type") != "session_start":
                attempt.failure_kind = "admission_error"
                return attempt
            raw_id = first.get("session_id")
            try:
                attempt.session_id = str(uuid.UUID(raw_id))
            except (ValueError, TypeError, AttributeError):
                attempt.failure_kind = "admission_error"
                attempt.diagnostic = "invalid_session_id"
                return attempt
            attempt.admitted = True
            attempt.session_start_received_offset_ms = received
            attempt.session_admission_ms = received - attempt.handshake_complete_offset_ms
            attempt.connect_to_session_start_ms = received
            tracker.change(attempt_id, True)
        if barrier is not None:
            barrier.arrive()
            arrived = True
        receiver = asyncio.create_task(receive())
        tasks.append(receiver)
        if barrier is not None:
            barrier_wait = asyncio.create_task(barrier.ready.wait())
            tasks.append(barrier_wait)
            await asyncio.wait((receiver, barrier_wait), return_when=asyncio.FIRST_COMPLETED)
            if receiver.done():
                await receiver
                return attempt
        sender = asyncio.create_task(send())
        tasks.append(sender)
        pending = {receiver, sender}
        if audio.mode == "wav":
            guard = asyncio.create_task(caption_deadline())
            tasks.append(guard)
            pending.add(guard)
        while not sender.done():
            completed, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in completed:
                await task
                pending.discard(task)
            if receiver in completed:
                if attempt.session_end_after_stop:
                    # A fast end/close may arrive while send() is still completing.
                    # Let the bounded stop-send finish rather than canceling it.
                    await sender
                return attempt
        await sender
        end_wait = asyncio.create_task(session_end.wait())
        tasks.append(end_wait)
        guard_tasks = {task for task in pending if task is not receiver}
        async with asyncio.timeout(config.shutdown_timeout):
            while not end_wait.done():
                completed, _ = await asyncio.wait(
                    {receiver, end_wait, *guard_tasks}, return_when=asyncio.FIRST_COMPLETED)
                for task in completed:
                    await task
                    guard_tasks.discard(task)
                if receiver in completed and not session_end.is_set():
                    return attempt
                if receiver in completed:
                    break
    except TimeoutError:
        attempt.failure_kind = "timeout"
        attempt.diagnostic = "deadline_exceeded"
    except Exception as exc:
        if is_closed_exception(exc):
            if socket is None:
                attempt.failure_kind = "admission_error"
                attempt.diagnostic = redact(type(exc).__name__, secrets)
            else:
                observe_close(exc)
        else:
            handshake_error = any(cls.__name__ in {
                "InvalidStatus", "InvalidStatusCode", "InvalidHandshake", "NegotiationError"
            } for cls in type(exc).__mro__)
            attempt.failure_kind = ("admission_error" if not attempt.admitted and handshake_error
                                    else "client_error")
            attempt.diagnostic = redact(type(exc).__name__, secrets)
    finally:
        if barrier is not None and not arrived:
            barrier.arrive()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if (attempt.audio_streaming_start_offset_ms is not None and
                attempt.audio_streaming_end_offset_ms is None):
            attempt.audio_streaming_end_offset_ms = offset()
        if socket is not None:
            if attempt.socket_closed_offset_ms is None:
                attempt.close_initiator = "client_cleanup"
            try:
                await asyncio.wait_for(socket.close(), config.shutdown_timeout)
                if attempt.socket_closed_offset_ms is None:
                    attempt.socket_closed_offset_ms = offset()
                code = getattr(socket, "close_code", None)
                if isinstance(code, int):
                    if attempt.close_code is None or attempt.close_initiator != "remote":
                        attempt.close_code = code
                    # recv() can still be awaiting the close handshake when
                    # session_end wakes the drain waiter and cleanup cancels it.
                    # The transport's abnormal close verdict must not disappear.
                    if (attempt.admitted and code not in {1000, 1001} and
                            attempt.failure_kind != "timeout"):
                        attempt.unexpected_disconnect = True
                if attempt.close_reason is None:
                    raw_reason = getattr(socket, "close_reason", "")
                    safe_reason = redact(raw_reason, secrets) if isinstance(raw_reason, str) else ""
                    attempt.close_reason = (safe_reason if safe_reason in {"", "Normal closure",
                                            "Going away", "[REDACTED]"} else "[OMITTED]")
            except Exception:
                if attempt.failure_kind is None:
                    attempt.failure_kind = "timeout"
                    attempt.diagnostic = "close_cleanup_failed"
        tracker.change(attempt_id, False)
        attempt.expected_close = (attempt.session_end_after_stop and
                                  not attempt.unexpected_disconnect and
                                  attempt.socket_closed_offset_ms is not None and
                                  attempt.close_code in {1000, 1001})
        for segment in attempt.segments:
            map_audio_end(segment, attempt, audio)
        attempt.unique_finalized_segments = len({s.segment_id for s in attempt.segments
                                                 if s.segment_id is not None})
        drifts = [f.pacing_drift_ms for f in attempt.frames]
        attempt.pacing_drift_max_ms = max(drifts) if drifts else None
        attempt.pacing_drift_p95_ms = nearest_rank(drifts, 95)
        attempt.wall_time_seconds = clock.now() - start
        attempt.outcome = terminal_outcome(attempt, audio.mode)
    return attempt


def aggregate(attempts: list[AttemptResult], elapsed: float, mode: str,
              peak: int) -> dict[str, Any]:
    counts = Counter(attempt.outcome for attempt in attempts)
    admitted = sum(attempt.admitted for attempt in attempts)
    segments = [segment for attempt in attempts for segment in attempt.segments]
    valid_lags = sum(segment.lag_status == "valid" for segment in segments)

    def rate(count: int, denominator: float) -> float | None:
        return count / denominator if denominator > 0 else None

    metrics = {name: metric_summary([getattr(attempt, name) for attempt in attempts])
               for name in ATTEMPT_LATENCIES
               if mode == "wav" or name not in {
                   "time_to_first_partial_ms", "time_to_first_final_ms"}}
    metrics["pacing_drift_ms"] = metric_summary([
        frame.pacing_drift_ms for attempt in attempts for frame in attempt.frames])
    if mode == "wav":
        metrics["finalized_caption_lag_ms"] = metric_summary([
            segment.finalized_caption_lag_ms for segment in segments])
    return {
        "attempts": len(attempts),
        "handshakes_completed": sum(attempt.handshake_completed for attempt in attempts),
        "admitted": admitted,
        "outcome_counts": {outcome: counts[outcome] for outcome in OUTCOMES},
        "successful_session_rate_attempted": rate(counts["success"], len(attempts)),
        "successful_session_rate_admitted": rate(counts["success"], admitted),
        "unexpected_disconnect_rate_admitted": rate(
            sum(a.unexpected_disconnect for a in attempts if a.admitted), admitted),
        "peak_observed_concurrency": peak,
        "throughput_window_seconds": elapsed,
        "partial_messages_per_second": rate(
            sum(a.partial_segments_received for a in attempts), elapsed),
        "final_messages_per_second": rate(
            sum(a.finalized_segments_received for a in attempts), elapsed),
        "audio_bytes_sent_per_second": rate(sum(a.bytes_sent for a in attempts), elapsed),
        "final_segments_with_valid_lag": valid_lags,
        "final_segments_without_valid_lag": len(segments) - valid_lags,
        "lag_status_counts": dict(Counter(s.lag_status for s in segments)),
        "latencies": metrics,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def git_state() -> tuple[str | None, bool | None]:
    root = Path(__file__).resolve().parents[1]
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                             check=True, capture_output=True, text=True, timeout=5).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                                check=True, capture_output=True, text=True, timeout=5).stdout
        return sha, bool(status.strip())
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None, None


async def run_benchmark(config: Config, audio: AudioFixture,
                        connector: Callable[..., Any] | None = None,
                        clock: Clock | None = None) -> dict[str, Any]:
    config = replace(config, run_id=config.run_id or str(uuid.uuid4()))
    connection_url(config)
    if config.auth and not config.token.strip():
        raise ValueError("Authentication requested but token environment variable is empty")
    if connector is None:
        try:
            import websockets
        except ImportError as exc:
            raise ValueError("Install websockets before a separately authorized run") from exc
        connector = websockets.connect
    clock = clock or Clock()
    started_at = utc_now()
    sha, dirty = git_state()
    warmup_tracker = ConcurrencyTracker(clock, clock.now())
    warmups = []
    for index in range(config.warmup_sessions):
        warmups.append(await one_session(config, audio, f"warmup-{index + 1}",
                                         warmup_tracker, connector, clock, phase="warmup"))
    warmup_elapsed = clock.now() - warmup_tracker.origin
    origin = clock.now()
    tracker = ConcurrencyTracker(clock, origin)
    barrier = AdmissionBarrier(config.concurrency)
    tasks = []
    for index in range(config.concurrency):
        tasks.append(asyncio.create_task(one_session(
            config, audio, f"attempt-{index + 1}", tracker, connector, clock, barrier)))
        if config.ramp > 0 and index + 1 < config.concurrency:
            await clock.sleep(config.ramp)
    attempts = await asyncio.gather(*tasks)
    elapsed = clock.now() - origin
    try:
        websocket_version = importlib.metadata.version("websockets")
    except importlib.metadata.PackageNotFoundError:
        websocket_version = None
    metadata = {
        "schema_version": SCHEMA_VERSION, "started_at": started_at, "ended_at": utc_now(),
        "run_id": config.run_id or str(uuid.uuid4()), "scenario": config.scenario,
        "git_commit_sha": sha, "git_dirty": dirty,
        "target_url": sanitized_url(config.url), "source_language": config.source,
        "target_language": config.target,
        "stream_mode": dict(parse_qsl(urlsplit(connection_url(config)).query))["stream_mode"],
        "audio_mode": audio.mode, "auth_enabled": config.auth,
        "concurrency_requested": config.concurrency,
        "peak_observed_concurrency": tracker.peak, "ramp": config.ramp,
        "duration": audio.duration, "requested_silent_duration": config.duration,
        "warmup_sessions": config.warmup_sessions,
        "audio_filename": audio.path.name if audio.path else None,
        "audio_sha256": audio.sha256, "audio_duration_seconds": audio.duration,
        "audio_format": {"channels": 1, "sample_rate_hz": SAMPLE_RATE,
                         "sample_width_bytes": SAMPLE_WIDTH, "encoding": "signed_pcm_16le"},
        "python_version": platform.python_version(), "websockets_version": websocket_version,
        "platform": platform.platform(), "percentile_method": "nearest-rank: ceil(p/100*n)-1",
        "connect_timeout": config.connect_timeout,
        "first_caption_timeout": config.first_caption_timeout,
        "shutdown_timeout": config.shutdown_timeout, "insecure_tls": config.insecure,
        "send_timeout": config.send_timeout,
        "audio_timeline_origin": "first PCM sample; includes leading silence",
        "lag_mapping": "actual frame send start + within-frame sample offset",
        "throughput_window": "measured launch through final cleanup; includes ramp/admission/drain",
    }
    return redact({
        "metadata": metadata,
        "summary": aggregate(attempts, elapsed, audio.mode, tracker.peak),
        "warmup_summary": aggregate(warmups, warmup_elapsed, audio.mode, warmup_tracker.peak),
        "overall_summary": aggregate(warmups + attempts, clock.now() - warmup_tracker.origin,
                                     audio.mode, max(warmup_tracker.peak, tracker.peak)),
        "attempts": [asdict(attempt) for attempt in attempts],
        "warmup_attempts": [asdict(attempt) for attempt in warmups],
        "observed_active_sessions": tracker.events,
    }, (config.token,))


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as output:
            temp_name = output.name
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            os.unlink(temp_name)


def csv_content(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        encoded = {key: json.dumps(value) if isinstance(value, (list, dict)) else value
                   for key, value in row.items() if key in fieldnames}
        writer.writerow(encoded)
    return output.getvalue()


def write_outputs(report: dict[str, Any], json_path: Path | None,
                  csv_path: Path | None, secrets: tuple[str, ...] = ()) -> list[Path]:
    report = redact(report, secrets)
    paths = []
    if json_path is not None:
        atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        paths.append(json_path)
    if csv_path is not None:
        base = csv_path.with_suffix("")
        attempt_path = base.with_name(base.name + "-attempts.csv")
        segment_path = base.with_name(base.name + "-segments.csv")
        metadata = report["metadata"]
        attempts = report["warmup_attempts"] + report["attempts"]
        rows = [{"run_id": metadata["run_id"], "scenario": metadata["scenario"], **a}
                for a in attempts]
        attempt_fields = ["run_id", "scenario"] + [
            key for key in AttemptResult.__dataclass_fields__ if key not in {"frames", "segments"}]
        segments = [{"run_id": metadata["run_id"], "scenario": metadata["scenario"],
                     "phase": a["phase"], **segment}
                    for a in attempts for segment in a["segments"]]
        segment_fields = ["run_id", "scenario", "phase"] + list(SegmentResult.__dataclass_fields__)
        atomic_write(attempt_path, csv_content(rows, attempt_fields))
        atomic_write(segment_path, csv_content(segments, segment_fields))
        paths.extend((attempt_path, segment_path))
    return paths


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse otherwise echoes unknown CLI arguments, possibly a secret.
        self.exit(2, "Invalid arguments. Use --help; tokens belong in environment variables.\n")


def parser() -> argparse.ArgumentParser:
    result = SafeArgumentParser(description=__doc__, allow_abbrev=False)
    result.add_argument("--url", required=True, help="ws:// or wss:// endpoint; no tokens in URL")
    result.add_argument("--concurrency", type=int, default=8, help="Attempts, not observed concurrency")
    result.add_argument("--duration", type=float, default=8.0, help="Silent seconds; WAV replays full fixture")
    result.add_argument("--ramp", type=float, default=0.2, help="Seconds between admission attempts")
    result.add_argument("--source", default="vi-VN", choices=("vi-VN", "en-US"))
    result.add_argument("--target", default="en", choices=("en", "vi"))
    result.add_argument("--stream-mode", choices=("dual", "single"), default="dual")
    result.add_argument("--audio-mode", choices=("silent", "wav"))
    result.add_argument("--audio-file", type=Path)
    result.add_argument("--token-env", default="LIVECAP_ACCESS_TOKEN")
    auth = result.add_mutually_exclusive_group()
    auth.add_argument("--auth", action="store_true", default=None, help="Require an environment access token")
    auth.add_argument("--no-auth", action="store_false", dest="auth", help="Explicit anonymous test")
    result.add_argument("--insecure", action="store_true", help="Skip TLS verification (recorded)")
    result.add_argument("--connect-timeout", type=float, default=30.0, help="Handshake + admission deadline")
    result.add_argument("--first-caption-timeout", type=float, default=30.0)
    result.add_argument("--shutdown-timeout", type=float, default=10.0)
    result.add_argument("--send-timeout", type=float, default=10.0, help="Deadline per audio/stop send")
    result.add_argument("--warmup-sessions", type=int, default=0, help="Sequential full sessions recorded separately")
    result.add_argument("--output-json", type=Path)
    result.add_argument("--output-csv", type=Path)
    result.add_argument("--run-id", default="")
    result.add_argument("--scenario", default="unspecified")
    return result


def preflight(args: argparse.Namespace) -> tuple[Config, AudioFixture]:
    token = os.getenv(args.token_env, "").strip()
    auth = bool(token) if args.auth is None else args.auth
    if auth and not token:
        raise ValueError("Authentication requested but token environment variable is empty")
    if args.concurrency < 1 or args.warmup_sessions < 0:
        raise ValueError("Concurrency must be positive and warmup count nonnegative")
    for name in ("duration", "connect_timeout", "first_caption_timeout", "shutdown_timeout", "send_timeout"):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if not math.isfinite(args.ramp) or args.ramp < 0:
        raise ValueError("Ramp must be finite and nonnegative")
    if (args.source, args.target) not in {("vi-VN", "en"), ("en-US", "vi")}:
        raise ValueError("Use vi-VN/en or en-US/vi")
    mode = args.audio_mode or ("wav" if args.audio_file else "silent")
    if (mode == "wav") != (args.audio_file is not None):
        raise ValueError("WAV mode requires --audio-file; silent mode cannot use it")
    audio = validate_wav(args.audio_file) if mode == "wav" else AudioFixture(
        "silent", max(1, math.ceil(args.duration * SAMPLE_RATE)))
    config = Config(**{name: getattr(args, name) for name in (
        "url", "concurrency", "duration", "ramp", "source", "target", "stream_mode",
        "connect_timeout", "first_caption_timeout", "shutdown_timeout", "send_timeout", "warmup_sessions",
        "insecure", "run_id", "scenario")}, auth=auth, token=token)
    connection_url(config)
    output_paths = [args.output_json] if args.output_json is not None else []
    if args.output_csv is not None:
        base = args.output_csv.with_suffix("")
        output_paths.extend(base.with_name(base.name + suffix) for suffix in (
            "-attempts.csv", "-segments.csv"))
    resolved = [path.resolve() for path in output_paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("JSON and CSV output paths must be distinct")
    if args.audio_file is not None and args.audio_file.resolve() in resolved:
        raise ValueError("An output path cannot overwrite the audio fixture")
    return config, audio


def print_summary(report: dict[str, Any], secrets: tuple[str, ...] = ()) -> None:
    summary = report["summary"]
    print("\n=== Client benchmark summary ===")
    print(f"Total attempted     : {summary['attempts']}")
    print(f"Admitted            : {summary['admitted']}")
    print(f"Rejected (limit)    : {summary['outcome_counts']['limit_rejected']}")
    print(f"Errors              : {summary['attempts'] - summary['outcome_counts']['success'] - summary['outcome_counts']['limit_rejected']}")
    print(f"Peak observed       : {summary['peak_observed_concurrency']}")
    print(redact(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), secrets))
    print(redact("Warmup outcomes: " + json.dumps(report["warmup_summary"]["outcome_counts"]), secrets))
    print(redact("Overall outcomes: " + json.dumps(report["overall_summary"]["outcome_counts"]), secrets))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    secrets = (os.getenv(args.token_env, "").strip(),)
    preflight_complete = False
    try:
        config, audio = preflight(args)
        preflight_complete = True
        print(redact(f"Opening {config.concurrency} attempts to {sanitized_url(config.url)} "
                     f"(mode={audio.mode}, ramp={config.ramp}s)", secrets))
        report = asyncio.run(run_benchmark(config, audio))
        write_outputs(report, args.output_json, args.output_csv, secrets)
        print_summary(report, secrets)
        return 0 if report["overall_summary"]["outcome_counts"]["success"] == (
            config.concurrency + config.warmup_sessions) else 1
    except Exception as exc:
        detail = (str(exc) if isinstance(exc, ValueError) and not preflight_complete
                  else type(exc).__name__)
        print(redact(f"Benchmark preflight/output error: {detail}", secrets))
        return 2
    except KeyboardInterrupt:
        print("Benchmark cancelled")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
