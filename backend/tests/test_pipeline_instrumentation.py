"""Metadata contracts with mocked providers and in-process WebSockets only."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import contextmanager
from io import StringIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.datastructures import QueryParams

from app.config import Settings
from app.models import FinalizedSegmentMessage, PartialSegmentMessage, Segment
from app.routers import websocket as ws
from app.services import logging_service as logs
from app.services import pipeline_instrumentation as pi
from app.services import transcription as transcribe
from app.services import translation as translate

SID = "550e8400-e29b-41d4-a716-446655440000"
PRIVATE = "SECRET_AUDIO_TRANSCRIPT_TOKEN_EMAIL_user@example.test_198.51.100.7"


@pytest.fixture
def records():
    logger = logs.get_logger()
    old_level, old_handlers, old_propagate = logger.level, logger.handlers[:], logger.propagate
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logs._JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    result = []
    yield result, output
    common = {"schema_version", "event", "timestamp", "benchmark_run_id", "session_id",
              "segment_id", "stream_mode", "source_language", "target_language",
              "success", "duration_ms", "error_type", "asyncio_task"}
    observed = [json.loads(line) for line in output.getvalue().splitlines()]
    assert all(common <= row.keys() and row["schema_version"] == "1.0"
               and isinstance(row["success"], bool)
               for row in observed if row.get("event") in pi.EVENTS)
    logger.handlers = old_handlers
    logger.setLevel(old_level)
    logger.propagate = old_propagate


def read(records):
    return [json.loads(line) for line in records[1].getvalue().splitlines()]


def events(records, event):
    return [row for row in read(records) if row.get("event") == event]


@contextmanager
def correlated(mode="single"):
    state = pi.PipelineTelemetry(benchmark_run_id="validation.run-1", session_id=SID,
                                 stream_mode=mode, source_language="vi-VN", target_language="en")
    token = pi.CURRENT.set(state)
    try:
        yield state
    finally:
        pi.CURRENT.reset(token)


@pytest.mark.parametrize("value,expected", [
    (None, None), ("", None), ("valid-ID_1.v2", "valid-ID_1.v2"), ("x" * 64, "x" * 64),
    ("x" * 65, None), ("white space", None), ("trailing\n", None), ("../x", None),
    ("@email", None), ("Tiếng Việt", None), (1, None),
])
def test_run_id_validation(value, expected):
    assert pi.validate_benchmark_run_id(value) == expected


def test_common_schema_metadata_allowlist_and_monotonic_duration(records):
    with correlated() as state, patch.object(pi.time, "perf_counter", return_value=3.25):
        assert pi.duration_ms(3) == 250
        state.emit("websocket_caption_send_completed", duration_ms=pi.duration_ms(3),
                   segment_id="seg-1", kind="final", aggregate=False,
                   transcript_text=PRIVATE, raw_audio=PRIVATE.encode(), token=PRIVATE,
                   email=PRIVATE, client_ip=PRIVATE, user_id=PRIVATE,
                   timestamp_end=float("nan"), sdk_call_duration_ms=PRIVATE.encode())
    event = events(records, "websocket_caption_send_completed")[0]
    assert set(("schema_version", "event", "timestamp", "benchmark_run_id", "session_id",
                "segment_id", "stream_mode", "source_language", "target_language",
                "success", "duration_ms", "error_type", "asyncio_task")) <= event.keys()
    assert event["duration_ms"] == 250
    assert event["timestamp_end"] is None
    assert event["sdk_call_duration_ms"] is None
    assert event["benchmark_run_id"] == "validation.run-1"
    assert PRIVATE not in records[1].getvalue()


def test_exception_messages_tracebacks_and_unsafe_ids_are_not_logged(records):
    state = pi.PipelineTelemetry(benchmark_run_id=PRIVATE, session_id=PRIVATE,
                                 source_language=PRIVATE, target_language=PRIVATE)
    state.emit("translation_operation_completed", success=False, error=ValueError(PRIVATE),
               segment_id=PRIVATE, outcome=PRIVATE, close_reason=PRIVATE)
    logs.log_integration_error(SID, "Amazon Translate", RuntimeError(PRIVATE))
    row = events(records, "translation_operation_completed")[0]
    assert row["error_type"] == "ValueError"
    assert row["benchmark_run_id"] is None
    assert row["session_id"] is None
    assert row["segment_id"] is None
    assert PRIVATE not in records[1].getvalue()
    assert "error_message" not in events(records, "integration_error")[0]


@pytest.mark.parametrize("outcome", ["auth_rejected", "limit_rejected", "quota_rejected", "store_error"])
def test_rejected_attempt_has_no_admitted_terminal_event(records, outcome):
    with correlated() as state:
        state.admission(outcome, state.started_at)
        state.finish()
    assert len(events(records, "websocket_admission_completed")) == 1
    assert events(records, "websocket_session_outcome") == []


def test_terminal_event_is_once_and_primary_outcomes_are_exclusive(records):
    with correlated() as state:
        state.admitted = True
        state.fail("translation_degraded")
        state.fail("send_failed", OSError(PRIVATE))
        state.fail("transcribe_failed", RuntimeError(PRIVATE))
        state.finish()
        state.finish()
    assert len(events(records, "websocket_session_outcome")) == 1
    assert events(records, "websocket_session_outcome")[0]["outcome"] == "transcribe_failed"


def test_translation_split_timing_and_direction(records, monkeypatch):
    async def run():
        clock = SimpleNamespace(value=100.0)
        monkeypatch.setattr(pi.time, "perf_counter", lambda: clock.value)
        loop = asyncio.get_running_loop()

        def execute(pool, call):
            clock.value += .025  # Queue wait, before worker starts.
            future = loop.create_future()
            future.set_result(call())
            return future

        monkeypatch.setattr(loop, "run_in_executor", execute)

        def sdk(**kwargs):
            clock.value += .05
            return {"TranslatedText": "translated " + PRIVATE}

        with patch.object(translate.boto3, "client") as client, correlated("dual"):
            client.return_value.translate_text.side_effect = sdk
            service = translate.TranslationService()
            result = await service.translate_segment(Segment(segment_id="seg-1", speaker_label="Speaker 1", text_vi=PRIVATE,
                                                               spoken_language="vi"), SID)
            assert result.text_vi == PRIVATE
            assert result.text_en == "translated " + PRIVATE
    asyncio.run(run())
    row = events(records, "translation_operation_completed")[0]
    assert row["outcome"] == "translated"
    assert row["direction"] == "vi_to_en"
    assert row["segment_id"] == "vi-seg-1"
    assert row["executor_queue_duration_ms"] == pytest.approx(25)
    assert row["sdk_call_duration_ms"] == pytest.approx(50)
    assert row["duration_ms"] == pytest.approx(75)
    assert PRIVATE not in records[1].getvalue()


@pytest.mark.parametrize("source,raises,outcome", [(PRIVATE, True, "failed"), ("  ", False, "skipped_empty")])
def test_translation_failure_and_empty_do_not_fake_sdk_latency(records, source, raises, outcome):
    with patch.object(translate.boto3, "client") as client:
        service = translate.TranslationService()
        client.return_value.translate_text.side_effect = RuntimeError(PRIVATE)
        segment = Segment(segment_id="seg-1", speaker_label="Speaker 1", text_vi=source, spoken_language="vi")
        result = asyncio.run(service.translate_segment(segment, SID))
    row = events(records, "translation_operation_completed")[0]
    assert row["outcome"] == outcome
    assert result.model_dump() == segment.model_dump()
    if raises:
        assert row["success"] is False
        assert row["error_type"] == "RuntimeError"
        assert row["sdk_call_duration_ms"] is not None
    else:
        client.return_value.translate_text.assert_not_called()
        assert row["duration_ms"] is None
        assert row["sdk_call_duration_ms"] is None
        assert row["executor_queue_duration_ms"] is None
    assert PRIVATE not in records[1].getvalue()


def test_transcribe_open_results_and_partial_aggregation(records, monkeypatch):
    async def run():
        with correlated("dual"):
            service = transcribe.TranscriptionService(SID, Settings(), language_code="en-US")
            stream = SimpleNamespace(input_stream=AsyncMock(), output_stream=MagicMock())
            client = MagicMock(start_stream_transcription=AsyncMock(return_value=stream))

            async def handle(handler):
                for partial in (True, True, False):
                    result = SimpleNamespace(result_id="r-1", is_partial=partial,
                        start_time=0, end_time=.1, language_code="en-US", language_identification=None,
                        alternatives=[SimpleNamespace(transcript=PRIVATE,
                                                      items=[SimpleNamespace(speaker_label="spk_0")])])
                    await handler.handle_transcript_event(SimpleNamespace(transcript=SimpleNamespace(results=[result])))

            monkeypatch.setattr(transcribe, "TranscribeStreamingClient", lambda **kwargs: client)
            monkeypatch.setattr(transcribe._SegmentHandler, "handle_events", handle)
            audio = asyncio.Queue()
            await audio.put(bytes(3200))
            await audio.put(None)
            results = [message async for message in service.transcribe(audio)]
            assert len(results) == 3
            assert results[-1].text_en == PRIVATE
            stream.input_stream.send_audio_event.assert_awaited_once_with(audio_chunk=bytes(3200))
    asyncio.run(run())
    opened = events(records, "transcribe_stream_started")
    assert len(opened) == 1 and opened[0]["success"] is True
    assert opened[0]["stream_mode"] == "dual"
    assert opened[0]["stream_language"] == "en-US"
    received = events(records, "transcribe_result_received")
    assert len(received) == 2  # One final + one partial aggregate, never per revision.
    final = next(row for row in received if not row["aggregate"])
    assert final["segment_id"] == "en-seg-1"
    assert final["timestamp_end"] == .1
    assert final["duration_ms"] is None  # Receipt isn't AWS service latency.
    assert next(row for row in received if row["aggregate"])["partial_count"] == 2
    assert PRIVATE not in records[1].getvalue()


class MemoryWebSocket:
    def __init__(self, run_id="validation.run-1", fail_send=None, incoming=None):
        self.query_params = QueryParams({"benchmark_run_id": run_id, "source": "vi-VN", "target": "en"})
        self.headers = {"sec-websocket-protocol": "livecap.v1, " + PRIVATE,
                        "x-forwarded-for": "198.51.100.7"}
        self.client = SimpleNamespace(host="198.51.100.7")
        self.outgoing = []
        self.fail_send = fail_send
        self.incoming = list(incoming or [
            {"bytes": bytes(3200)}, {"bytes": bytes(1600)}, {"text": '{"type":"stop"}'},
        ])

    async def accept(self, **kwargs):
        pass

    async def send_text(self, payload):
        if json.loads(payload)["type"] == self.fail_send:
            raise OSError(PRIVATE)
        self.outgoing.append(json.loads(payload))

    async def receive(self):
        await asyncio.sleep(0)
        if self.incoming:
            return self.incoming.pop(0)
        await asyncio.Event().wait()

    async def close(self, *args, **kwargs):
        pass


@contextmanager
def pipeline(*, source_fails=False, translation_fails=False, settings=None):
    async def messages(audio):
        while await audio.get() is not None:
            pass
        if source_fails:
            raise RuntimeError(PRIVATE)
        yield PartialSegmentMessage(segment_id="seg-1", speaker_label="Speaker 1",
                                    text_vi=PRIVATE, spoken_language="vi")
        yield FinalizedSegmentMessage(segment_id="seg-1", speaker_label="Speaker 1",
                                      text_vi=PRIVATE, spoken_language="vi", timestamp_start=0,
                                      timestamp_end=.15)

    settings = settings or Settings(enable_auth=False, bilingual_dual_stream=False,
                                    session_store_backend="memory", enable_idle_scale_down=False)
    service = MagicMock(transcribe=messages)
    client = MagicMock()
    client.translate_text.return_value = {"TranslatedText": "translation " + PRIVATE}
    if translation_fails:
        client.translate_text.side_effect = RuntimeError(PRIVATE)
    translation_service = None
    ws.active_session_registry.clear()
    with patch.object(ws, "get_settings", return_value=settings), \
            patch.object(ws, "TranscriptionService", return_value=service), \
            patch.object(ws, "get_idle_scale_down_scheduler", return_value=MagicMock()), \
            patch.object(translate.boto3, "client", return_value=client):
        translation_service = translate.TranslationService()
        with patch.object(translate, "_get_default_service", return_value=translation_service):
            yield
    ws.active_session_registry.clear()


@pytest.mark.parametrize("send_failure,translation_failure,outcome", [
    (None, False, "success"), ("finalized_segment", False, "send_failed"),
    ("partial_segment", False, "send_failed"),
    ("session_end", False, "send_failed"), (None, True, "translation_degraded"),
])
def test_pipeline_counters_messages_and_single_terminal(records, send_failure, translation_failure, outcome):
    websocket = MemoryWebSocket(fail_send=send_failure)
    with pipeline(translation_fails=translation_failure):
        asyncio.run(ws.websocket_transcribe(websocket))
    terminal = events(records, "websocket_session_outcome")
    assert len(terminal) == 1
    result = terminal[0]
    assert result["outcome"] == outcome
    assert result["audio_bytes_received"] == 4800
    assert result["audio_frames_received"] == 2
    assert result["partial_count"] == 1 and result["final_count"] == 1
    assert result["translation_success_count"] == int(not translation_failure)
    assert result["translation_failure_count"] == int(translation_failure)
    assert result["session_end_send_success"] == (send_failure != "session_end")
    assert result["benchmark_run_id"] == "validation.run-1"
    assert [row["type"] for row in websocket.outgoing] == [
        kind for kind in ("session_start", "partial_segment", "finalized_segment", "session_end") if kind != send_failure]
    for row in websocket.outgoing:
        assert "benchmark_run_id" not in row and "run_id" not in row
    if not send_failure and not translation_failure:
        assert websocket.outgoing[1] == dict(type="partial_segment", segment_id="seg-1",
            speaker_label="Speaker 1", text_vi=PRIVATE, text_en="", spoken_language="vi", is_final=False)
        assert websocket.outgoing[2]["text_en"] == "translation " + PRIVATE
    assert PRIVATE not in records[1].getvalue()
    assert "198.51.100.7" not in records[1].getvalue()
    assert "websocket_admission_completed" in {row.get("event") for row in read(records)}
    assert pi.CURRENT.get() is None


def test_transcribe_failure_is_observed_without_altering_error_response(records):
    websocket = MemoryWebSocket()
    with pipeline(source_fails=True):
        asyncio.run(ws.websocket_transcribe(websocket))
    assert events(records, "websocket_session_outcome")[0]["outcome"] == "transcribe_failed"
    assert next(row for row in websocket.outgoing if row["type"] == "error")["code"] == "INTERNAL_ERROR"
    assert PRIVATE not in records[1].getvalue()


@pytest.mark.parametrize("kind", ["auth", "limit", "quota", "registry_store", "quota_store"])
def test_policy_rejections_store_errors_and_fail_open(records, kind):
    settings = Settings(enable_auth=True, bilingual_dual_stream=False, session_store_backend="memory")
    registry = MagicMock()
    registry.try_register.return_value = SimpleNamespace(allowed=kind != "limit", reason="max_total")
    if kind == "registry_store":
        registry.try_register.side_effect = RuntimeError(PRIVATE)
    user = SimpleNamespace(user_id=PRIVATE, email=PRIVATE)
    with pipeline(settings=settings), patch.object(ws, "authenticate_access_token", return_value=user) as auth, \
            patch.object(ws, "is_admin_user", return_value=False), \
            patch.object(ws, "get_session_registry", return_value=registry), \
            patch("app.services.usage_quota.reserve_weekly_session", return_value="quota limit" if kind == "quota" else None) as quota, \
            patch("app.services.usage_quota.add_minutes"):
        if kind == "auth":
            auth.side_effect = HTTPException(status_code=401, detail=PRIVATE)
        if kind == "quota_store":
            quota.side_effect = RuntimeError(PRIVATE)
        websocket = MemoryWebSocket()
        if kind == "registry_store":
            with pytest.raises(RuntimeError):
                asyncio.run(ws.websocket_transcribe(websocket))
        else:
            asyncio.run(ws.websocket_transcribe(websocket))
    admission = events(records, "websocket_admission_completed")
    assert len(admission) == 1
    assert admission[0]["outcome"] == {"auth": "auth_rejected", "limit": "limit_rejected",
        "quota": "quota_rejected", "registry_store": "store_error", "quota_store": "store_error"}[kind]
    assert admission[0]["duration_ms"] == admission[0]["total_admission_duration_ms"]
    if kind == "quota_store":
        assert admission[0]["admitted"] is True
        assert admission[0]["quota_error_type"] == "RuntimeError"
        assert len(events(records, "websocket_session_outcome")) == 1
    else:
        assert admission[0]["admitted"] is False
        assert events(records, "websocket_session_outcome") == []
    assert PRIVATE not in records[1].getvalue()
    assert "198.51.100.7" not in records[1].getvalue()


@pytest.mark.parametrize("source_fails,translation_fails", [(False, False), (True, False), (False, True)])
def test_logger_failure_does_not_change_pipeline_or_translation(records, source_fails, translation_fails):
    websocket = MemoryWebSocket()
    with pipeline(source_fails=source_fails, translation_fails=translation_fails), \
            patch.object(logs.get_logger(), "info", side_effect=RuntimeError(PRIVATE)), \
            patch.object(logs.get_logger(), "warning", side_effect=RuntimeError(PRIVATE)), \
            patch.object(logs.get_logger(), "error", side_effect=RuntimeError(PRIVATE)):
        asyncio.run(ws.websocket_transcribe(websocket))
    expected = ["session_start", "error", "session_end"] if source_fails else [
        "session_start", "partial_segment", "finalized_segment", "session_end"]
    assert [row["type"] for row in websocket.outgoing] == expected
    assert pi.CURRENT.get() is None


def test_buffer_emitted_dropped_metadata_and_windows_unchanged(records):
    with correlated():
        buffer = ws._SingleStreamCaptionBuffer()
        message = FinalizedSegmentMessage(segment_id="seg-1", speaker_label="Speaker 1", spoken_language="vi",
                                           text_vi=PRIVATE, timestamp_start=0, timestamp_end=.5)
        assert buffer.add(message) == []
        assert buffer.flush().text_vi == PRIVATE
        assert buffer.add(message.model_copy(update={"text_vi": ""})) == []
    rows = events(records, "arbitration_or_buffer_completed")
    assert [r["outcome"] for r in rows] == ["emitted", "dropped"]
    assert all(row["kind"] == "single_buffer" for row in rows)
    assert PRIVATE not in records[1].getvalue()
    assert ws._DUAL_STREAM_WINDOW_SECONDS == 1.5
    assert ws._SCREEN_SHARE_BUFFER_SECONDS == 2.4


@pytest.mark.parametrize("run_id", ["bad run id", "x" * 65, ""])
def test_invalid_correlation_is_null_without_rejecting_session(records, run_id):
    with pipeline():
        asyncio.run(ws.websocket_transcribe(MemoryWebSocket(run_id=run_id)))
    row = events(records, "websocket_session_outcome")[0]
    assert row["benchmark_run_id"] is None
    assert row["outcome"] == "success"


def test_admission_stage_clocks_are_separate_from_logger_wall_clock(records, monkeypatch):
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(pi.time, "perf_counter", lambda: clock.value)
    monkeypatch.setattr(pi.time, "time", lambda: 0.0)
    monkeypatch.setattr(pi.time, "time_ns", lambda: 0)

    def auth(token):
        clock.value += .01
        return SimpleNamespace(user_id=PRIVATE)

    def admin(user):
        clock.value += .02
        return False

    def register(**kwargs):
        clock.value += .03
        return SimpleNamespace(allowed=True)

    def quota(*args, **kwargs):
        clock.value += .04
        return None

    settings = Settings(enable_auth=True, bilingual_dual_stream=False, session_store_backend="memory")
    registry = MagicMock()
    registry.try_register.side_effect = register
    with pipeline(settings=settings), patch.object(ws, "authenticate_access_token", auth), \
            patch.object(ws, "is_admin_user", admin), patch.object(ws, "get_session_registry", return_value=registry), \
            patch("app.services.usage_quota.reserve_weekly_session", quota), patch("app.services.usage_quota.add_minutes"):
        asyncio.run(ws.websocket_transcribe(MemoryWebSocket()))
    row = events(records, "websocket_admission_completed")[0]
    assert row["auth_duration_ms"] == pytest.approx(10)
    assert row["admin_check_duration_ms"] == pytest.approx(20)
    assert row["registry_duration_ms"] == pytest.approx(30)
    assert row["quota_duration_ms"] == pytest.approx(40)
    assert row["total_admission_duration_ms"] == pytest.approx(100)
    assert row["timestamp"].startswith("1970-")  # Timestamp only; never duration subtraction.


def test_session_timeout_and_client_disconnect_have_single_terminal_events(records):
    async def hanging(audio):
        await asyncio.Event().wait()
        yield

    settings = Settings(enable_auth=False, bilingual_dual_stream=False, session_timeout=1)
    with pipeline(settings=settings), patch.object(ws, "TranscriptionService", return_value=MagicMock(transcribe=hanging)):
        asyncio.run(ws.websocket_transcribe(MemoryWebSocket()))
    assert events(records, "websocket_session_outcome")[0]["outcome"] == "timeout"
    records[1].truncate(0)
    records[1].seek(0)
    websocket = MemoryWebSocket(incoming=[{"type": "websocket.disconnect", "code": 1000, "reason": PRIVATE}])
    with pipeline():
        asyncio.run(ws.websocket_transcribe(websocket))
    rows = events(records, "websocket_session_outcome")
    assert len(rows) == 1 and rows[0]["outcome"] == "client_disconnect"
    assert rows[0]["close_code"] == 1000
    assert rows[0]["close_reason"] is None
    assert PRIVATE not in records[1].getvalue()


def test_dual_arbitration_metadata_uses_perf_clock_and_preserves_selection(records):
    async def run():
        with correlated("dual"):
            queue = asyncio.Queue()
            mode = ws._ALLOWED_LANGUAGE_MODES[("en-US", "vi")]
            msg = FinalizedSegmentMessage(segment_id="seg-1", speaker_label="Speaker 1",
                                           spoken_language="en", text_en="hello world",
                                           timestamp_start=0, timestamp_end=.1)
            queue.put_nowait(ws.TranscriptCandidate("en", "hello world", msg, mode, 0, 3.0))
            queue.put_nowait(None)
            queue.put_nowait(None)
            async def translated(segment, **kwargs):
                return segment.model_copy(update={"text_vi": "mock output"})
            with patch.object(pi.time, "perf_counter", return_value=3.25), patch.object(ws, "translate_segment", translated):
                emitted = [item async for item in ws._arbitrate_dual_candidates(session_id=SID, candidate_queue=queue)]
            assert emitted[0].segment_id == "en-seg-1"
            assert emitted[0].text_en == "hello world"
    asyncio.run(run())
    row = events(records, "arbitration_or_buffer_completed")[0]
    assert row["outcome"] == "emitted" and row["kind"] == "dual_arbitration"
    assert row["duration_ms"] == 250


def test_stream_open_failure_keeps_exception_and_logs_safe_duration(records):
    async def run():
        client = MagicMock(start_stream_transcription=AsyncMock(side_effect=RuntimeError(PRIVATE)))
        with patch.object(transcribe, "TranscribeStreamingClient", return_value=client), correlated():
            service = transcribe.TranscriptionService(SID, Settings())
            with pytest.raises(RuntimeError):
                _ = [item async for item in service.transcribe(asyncio.Queue())]
    asyncio.run(run())
    row = events(records, "transcribe_stream_started")[0]
    assert row["success"] is False and row["error_type"] == "RuntimeError"
    assert row["duration_ms"] >= 0
    assert PRIVATE not in records[1].getvalue()


def test_caption_processing_error_is_not_mislabeled_as_provider_failure(records):
    websocket = MemoryWebSocket()
    with pipeline(), patch.object(ws, "_send_caption", side_effect=RuntimeError(PRIVATE)):
        asyncio.run(ws.websocket_transcribe(websocket))
    row = events(records, "websocket_session_outcome")[0]
    assert row["outcome"] == "internal_error"
    assert row["error_type"] == "RuntimeError"
    assert PRIVATE not in records[1].getvalue()


def test_translation_cancelled_keeps_cancellation_and_null_unfinished_sdk_time(records):
    async def run():
        with patch.object(translate.boto3, "client"), correlated():
            service = translate.TranslationService()
            service._translate_async = AsyncMock(side_effect=asyncio.CancelledError(PRIVATE))
            with pytest.raises(asyncio.CancelledError):
                await service.translate_segment(Segment(segment_id="seg-1", speaker_label="Speaker 1",
                                                        spoken_language="vi", text_vi=PRIVATE), SID)
    asyncio.run(run())
    row = events(records, "translation_operation_completed")[0]
    assert row["outcome"] == "cancelled" and row["success"] is False
    assert row["error_type"] == "CancelledError"
    assert row["sdk_call_duration_ms"] is None
    assert row["duration_ms"] >= 0
    assert PRIVATE not in records[1].getvalue()


def test_translation_total_includes_lazy_client_initialization(records, monkeypatch):
    clock = SimpleNamespace(value=100.0)
    monkeypatch.setattr(pi.time, "perf_counter", lambda: clock.value)
    with patch.object(translate.boto3, "client") as client:
        client.return_value.translate_text.return_value = {"TranslatedText": "mock output"}
        service = translate.TranslationService()
        service._translate_async = AsyncMock(return_value="mock output")

        def initialize():
            clock.value += .02
            return service

        with patch.object(translate, "_get_default_service", side_effect=initialize):
            asyncio.run(translate.translate_segment(Segment(segment_id="seg-1", speaker_label="Speaker 1",
                                                             spoken_language="vi", text_vi=PRIVATE), SID))
    row = events(records, "translation_operation_completed")[0]
    assert row["duration_ms"] == pytest.approx(20)
    assert translate._OPERATION_START.get() is None


def test_translation_initialization_failure_has_direction_and_preserves_exception(records):
    segment = Segment(segment_id="seg-1", speaker_label="Speaker 1", spoken_language="en", text_en=PRIVATE)
    with patch.object(translate, "_get_default_service", side_effect=RuntimeError(PRIVATE)):
        with pytest.raises(RuntimeError):
            asyncio.run(translate.translate_segment(segment, SID))
    row = events(records, "translation_operation_completed")[0]
    assert row["direction"] == "en_to_vi"
    assert row["success"] is False and row["outcome"] == "failed"
    assert row["sdk_call_duration_ms"] is None
    assert PRIVATE not in records[1].getvalue()


def test_empty_sdk_output_is_failed_operation_without_changing_returned_payload(records):
    with patch.object(translate.boto3, "client") as client:
        client.return_value.translate_text.return_value = {"TranslatedText": ""}
        service = translate.TranslationService()
        segment = Segment(segment_id="seg-1", speaker_label="Speaker 1", spoken_language="vi", text_vi=PRIVATE)
        result = asyncio.run(service.translate_segment(segment, SID))
    assert result.model_dump() == segment.model_dump()
    row = events(records, "translation_operation_completed")[0]
    assert row["outcome"] == "failed" and row["success"] is False
    assert row["sdk_call_duration_ms"] is not None


def test_translation_correlations_are_isolated_across_concurrent_sessions(records):
    import threading

    rendezvous = threading.Barrier(2, timeout=5)

    def sdk(**kwargs):
        rendezvous.wait()
        return {"TranslatedText": "mock output"}

    async def run():
        with patch.object(translate.boto3, "client") as client:
            client.return_value.translate_text.side_effect = sdk
            service = translate.TranslationService()

            async def operation(run_id, spoken):
                state = pi.PipelineTelemetry(benchmark_run_id=run_id, session_id=str(uuid.uuid4()),
                                             stream_mode="dual")
                token = pi.CURRENT.set(state)
                try:
                    await service.translate_segment(Segment(segment_id="seg-1", speaker_label="Speaker 1",
                        spoken_language=spoken, text_vi=PRIVATE if spoken == "vi" else "",
                        text_en=PRIVATE if spoken == "en" else ""))
                finally:
                    pi.CURRENT.reset(token)

            await asyncio.gather(operation("isolated.vi", "vi"), operation("isolated.en", "en"))
    asyncio.run(run())
    rows = events(records, "translation_operation_completed")
    assert len(rows) == 2
    assert {(r["benchmark_run_id"], r["direction"], r["segment_id"]) for r in rows} == {
        ("isolated.vi", "vi_to_en", "vi-seg-1"), ("isolated.en", "en_to_vi", "en-seg-1")}
    assert len({r["session_id"] for r in rows}) == 2
    assert all(r["executor_queue_duration_ms"] >= 0 and r["sdk_call_duration_ms"] >= 0 for r in rows)


def test_partial_send_failures_are_aggregated_and_terminal_emission_is_once(records):
    async def run():
        with correlated() as state:
            state.admitted = True
            websocket = MemoryWebSocket(fail_send="partial_segment")
            for _ in range(3):
                await ws._send(websocket, PartialSegmentMessage(segment_id="seg-1", speaker_label="Speaker 1",
                                                               spoken_language="vi", text_vi=PRIVATE))
            state.finish()
            state.finish()
    asyncio.run(run())
    summaries = events(records, "websocket_caption_send_completed")
    assert len(summaries) == 1
    assert summaries[0]["aggregate"] is True
    assert summaries[0]["attempt_count"] == 3 and summaries[0]["failure_count"] == 3
    assert summaries[0]["success_count"] == 0 and summaries[0]["duration_ms"] is None
    assert summaries[0]["error_type"] == "OSError"
    assert len(events(records, "websocket_session_outcome")) == 1
    assert events(records, "websocket_session_outcome")[0]["outcome"] == "send_failed"


def test_invalid_binary_frame_is_counted_without_logging_its_payload(records):
    websocket = MemoryWebSocket(incoming=[{"bytes": b"\x00"}])
    with pipeline():
        asyncio.run(ws.websocket_transcribe(websocket))
    terminal = events(records, "websocket_session_outcome")[0]
    assert terminal["audio_frames_received"] == 1 and terminal["audio_bytes_received"] == 1
    assert terminal["partial_count"] == 0 and terminal["final_count"] == 0
    assert terminal["outcome"] == "internal_error"
    assert next(m for m in websocket.outgoing if m["type"] == "error")["code"] == "INVALID_AUDIO_FORMAT"
    assert PRIVATE not in records[1].getvalue()


def test_cancelled_caption_send_is_observed_and_cancellation_still_propagates(records):
    async def run():
        with correlated() as state:
            state.admitted = True
            websocket = MemoryWebSocket()
            websocket.send_text = AsyncMock(side_effect=asyncio.CancelledError(PRIVATE))
            with pytest.raises(asyncio.CancelledError):
                await ws._send(websocket, FinalizedSegmentMessage(segment_id="seg-1", speaker_label="Speaker 1",
                    spoken_language="vi", text_vi=PRIVATE, timestamp_start=0, timestamp_end=.1))
            state.finish()
            state.finish()
    asyncio.run(run())
    row = events(records, "websocket_caption_send_completed")[0]
    assert row["success"] is False and row["error_type"] == "CancelledError"
    assert len(events(records, "websocket_session_outcome")) == 1
    assert PRIVATE not in records[1].getvalue()


def test_reader_failure_is_observed_without_changing_caption_or_teardown_flow(records):
    websocket = MemoryWebSocket()
    websocket.receive = AsyncMock(side_effect=RuntimeError(PRIVATE))
    with pipeline():
        asyncio.run(ws.websocket_transcribe(websocket))
    row = events(records, "websocket_session_outcome")[0]
    assert row["outcome"] == "internal_error" and row["error_type"] == "RuntimeError"
    assert row["audio_frames_received"] == 0 and row["audio_bytes_received"] == 0
    assert [message["type"] for message in websocket.outgoing] == [
        "session_start", "partial_segment", "finalized_segment", "session_end"]
    assert PRIVATE not in records[1].getvalue()
