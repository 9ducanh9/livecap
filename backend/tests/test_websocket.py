"""Unit tests for backend/app/routers/websocket.py.

Tests cover:
- Session ID assignment and session_start message (Req 2.2)
- Binary frame routing to transcription with audio validation (Req 2.3, 2.8, 3.1)
- JSON stop signal handling (Req 2.4)
- Partial and finalized segment forwarding (Req 3.2, 3.3)
- Translation of finalized segments (Req 5.2)
- Error message generation and session_end on failure (Req 3.7, 2.5)
- Session timeout enforcement (Req 2.5)
- Resource cleanup and logging (Req 10.1, 10.2)
- Connection interruption handling
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket

from app.config import Settings
from app.models import (
    ErrorCode,
    FinalizedSegmentMessage,
    PartialSegmentMessage,
    Segment,
    SessionEndMessage,
    SessionStartMessage,
)
from app.routers import websocket as ws_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_settings(**overrides) -> Settings:
    defaults = dict(
        aws_region="us-east-1",
        s3_bucket="test-bucket",
        download_link_expiration=86400,
        session_timeout=30,  # short timeout for tests
        bilingual_dual_stream=False,
        allowed_origin="http://localhost:5173",
        cloudwatch_log_group="livecap",
        max_concurrent_sessions=4,
        max_sessions_per_ip=1,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def mock_settings():
    """Patch get_settings to return test configuration."""
    with patch("app.routers.websocket.get_settings", return_value=make_settings()):
        yield


@pytest.fixture
def mock_logging():
    """Patch all logging service calls to avoid side effects in tests."""
    with patch("app.routers.websocket.log_session_start"), \
         patch("app.routers.websocket.log_session_end"), \
         patch("app.routers.websocket.log_websocket_connect"), \
         patch("app.routers.websocket.log_websocket_disconnect"), \
         patch("app.routers.websocket.log_integration_error"):
        yield


@pytest.fixture
def app():
    """Create a minimal FastAPI app with the WebSocket router."""
    test_app = FastAPI()
    test_app.include_router(ws_module.router)
    return test_app


@pytest.fixture(autouse=True)
def clear_active_session_registry():
    """Ensure process-local session limits do not leak between tests."""
    ws_module.active_session_registry.clear()
    yield
    ws_module.active_session_registry.clear()


def make_valid_audio_chunk() -> bytes:
    """Return valid PCM 16-bit mono 16 kHz audio (~100 ms)."""
    return b"\x00" * 3200


def make_invalid_audio_chunk() -> bytes:
    """Return an invalid chunk (odd byte count, fails validation)."""
    return b"\x00" * 3201


def make_stop_message() -> str:
    """Return the JSON stop signal."""
    return json.dumps({"type": "stop"})


def make_ping_message() -> str:
    """Return the JSON heartbeat ping signal."""
    return json.dumps({"type": "ping"})


def collect_until_session_end(websocket, max_messages: int = 20) -> list[dict]:
    """Receive JSON messages from *websocket* until session_end or max_messages.

    Note: starlette's TestClient WebSocketTestSession does not support a
    timeout parameter on receive_text(). Tests must drive the session to a
    natural end so that session_end is sent, or rely on the connection being
    closed by the server.  A WebSocketDisconnect from the server side is
    treated as end-of-stream.
    """
    received: list[dict] = []
    for _ in range(max_messages):
        try:
            msg_text = websocket.receive_text()
            msg = json.loads(msg_text)
            received.append(msg)
            if msg.get("type") == "session_end":
                break
        except Exception:
            # Connection closed or other error — stop collecting.
            break
    return received


# ---------------------------------------------------------------------------
# Session ID assignment and session_start message (Req 2.2)
# ---------------------------------------------------------------------------


class TestSessionStartMessage:
    """Verify that the backend assigns a UUID v4 Session_ID and sends session_start."""

    def test_sends_session_start_after_accept(self, app, mock_settings, mock_logging):
        """First message after accept should be session_start with a valid session_id."""

        received_msgs = []

        async def mock_transcribe(*args, **kwargs):
            # Return empty generator (no transcription events)
            if False:
                yield

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    # Receive the first message
                    data = websocket.receive_text()
                    msg = json.loads(data)
                    received_msgs.append(msg)

                    # Send stop to close cleanly
                    websocket.send_text(make_stop_message())

        # Check session_start structure
        assert len(received_msgs) >= 1
        start_msg = received_msgs[0]
        assert start_msg["type"] == "session_start"
        assert "session_id" in start_msg
        # UUID v4 has 36 chars including dashes
        assert len(start_msg["session_id"]) == 36

    def test_each_connection_gets_unique_session_id(
        self, app, mock_settings, mock_logging
    ):
        """Two connections should get different Session_IDs."""

        session_ids = []

        async def mock_transcribe(*args, **kwargs):
            if False:
                yield

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                # First connection
                with client.websocket_connect("/ws/transcribe") as ws1:
                    msg1 = json.loads(ws1.receive_text())
                    session_ids.append(msg1["session_id"])
                    ws1.send_text(make_stop_message())

                # Second connection
                with client.websocket_connect("/ws/transcribe") as ws2:
                    msg2 = json.loads(ws2.receive_text())
                    session_ids.append(msg2["session_id"])
                    ws2.send_text(make_stop_message())

        assert len(session_ids) == 2
        assert session_ids[0] != session_ids[1]


# ---------------------------------------------------------------------------
# Manual language mode validation
# ---------------------------------------------------------------------------


class TestLanguageMode:
    def test_default_mode_uses_vietnamese_to_english(
        self, app, mock_settings, mock_logging
    ):
        async def mock_transcribe(audio_queue):
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
            if False:
                yield

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()
                    websocket.send_text(make_stop_message())
                    collect_until_session_end(websocket)

        kwargs = MockTranscriptionService.call_args.kwargs
        assert kwargs["language_code"] == "vi-VN"

    def test_english_to_vietnamese_mode_sets_transcribe_source(
        self, app, mock_settings, mock_logging
    ):
        async def mock_transcribe(audio_queue):
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
            if False:
                yield

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws/transcribe?source=en-US&target=vi"
                ) as websocket:
                    _ = websocket.receive_text()
                    websocket.send_text(make_stop_message())
                    collect_until_session_end(websocket)

        kwargs = MockTranscriptionService.call_args.kwargs
        assert kwargs["language_code"] == "en-US"

    def test_invalid_language_mode_is_rejected(self, app, mock_settings):
        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws/transcribe?source=vi-VN&target=vi"
                ) as websocket:
                    msg = json.loads(websocket.receive_text())

        assert msg["type"] == "error"
        assert msg["code"] == ErrorCode.INVALID_LANGUAGE_MODE.value
        MockTranscriptionService.assert_not_called()


# ---------------------------------------------------------------------------
# Active session abuse guard
# ---------------------------------------------------------------------------


class TestActiveSessionGuard:
    def test_rejects_when_per_ip_limit_exceeded(self, app, mock_logging):
        settings = make_settings(max_concurrent_sessions=4, max_sessions_per_ip=1)
        ws_module.active_session_registry.try_register(
            session_id="existing",
            client_ip="203.0.113.10",
            max_total=4,
            max_per_ip=1,
        )

        with patch("app.routers.websocket.get_settings", return_value=settings), \
             patch("app.routers.websocket.TranscriptionService") as MockTranscriptionService:
            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws/transcribe",
                    headers={"x-forwarded-for": "203.0.113.10"},
                ) as websocket:
                    msg = json.loads(websocket.receive_text())

        assert msg["type"] == "error"
        assert msg["code"] == ErrorCode.TOO_MANY_SESSIONS.value
        MockTranscriptionService.assert_not_called()

    def test_rejects_when_global_limit_exceeded(self, app, mock_logging):
        settings = make_settings(max_concurrent_sessions=1, max_sessions_per_ip=1)
        ws_module.active_session_registry.try_register(
            session_id="existing",
            client_ip="203.0.113.10",
            max_total=1,
            max_per_ip=1,
        )

        with patch("app.routers.websocket.get_settings", return_value=settings), \
             patch("app.routers.websocket.TranscriptionService") as MockTranscriptionService:
            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws/transcribe",
                    headers={"x-forwarded-for": "198.51.100.20"},
                ) as websocket:
                    msg = json.loads(websocket.receive_text())

        assert msg["type"] == "error"
        assert msg["code"] == ErrorCode.TOO_MANY_SESSIONS.value
        MockTranscriptionService.assert_not_called()

    def test_registry_cleanup_after_stop(self, app, mock_settings, mock_logging):
        async def mock_transcribe(audio_queue):
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
            if False:
                yield

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws/transcribe",
                    headers={"x-forwarded-for": "203.0.113.30"},
                ) as websocket:
                    _ = websocket.receive_text()
                    assert ws_module.active_session_registry.active_count == 1
                    websocket.send_text(make_stop_message())
                    collect_until_session_end(websocket)

        assert ws_module.active_session_registry.active_count == 0
        assert ws_module.active_session_registry.active_count_for_ip("203.0.113.30") == 0

    def test_registry_cleanup_after_transcribe_error(
        self, app, mock_settings, mock_logging
    ):
        async def mock_transcribe(audio_queue):
            _ = await audio_queue.get()
            yield RuntimeError("transcribe failed")
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws/transcribe",
                    headers={"x-forwarded-for": "203.0.113.40"},
                ) as websocket:
                    _ = websocket.receive_text()
                    websocket.send_bytes(make_valid_audio_chunk())
                    collect_until_session_end(websocket)

        assert ws_module.active_session_registry.active_count == 0
        assert ws_module.active_session_registry.active_count_for_ip("203.0.113.40") == 0


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    def test_ping_returns_pong(self, app, mock_settings, mock_logging):
        async def mock_transcribe(audio_queue):
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
            if False:
                yield

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()
                    websocket.send_text(make_ping_message())
                    msg = json.loads(websocket.receive_text())
                    websocket.send_text(make_stop_message())
                    collect_until_session_end(websocket)

        assert msg == {"type": "pong"}


# ---------------------------------------------------------------------------
# Bilingual dual-stream mode
# ---------------------------------------------------------------------------


class TestBilingualDualStream:
    def test_dual_stream_fans_out_audio_and_emits_longer_finalized_candidate(
        self, app, mock_logging
    ):
        settings = make_settings(bilingual_dual_stream=True)
        chunks_by_language: dict[str, list[bytes]] = {"vi-VN": [], "en-US": []}

        vi_msg = FinalizedSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="xin chao",
            text_en="",
            spoken_language="vi",
            timestamp_start=0.0,
            timestamp_end=1.0,
        )
        en_msg = FinalizedSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="",
            text_en="hi there",
            spoken_language="en",
            timestamp_start=0.0,
            timestamp_end=1.0,
        )

        def make_service(*args, **kwargs):
            language_code = kwargs["language_code"]

            async def mock_transcribe(audio_queue):
                chunk = await audio_queue.get()
                if chunk is not None:
                    chunks_by_language[language_code].append(chunk)
                yield vi_msg if language_code == "vi-VN" else en_msg
                while True:
                    item = await audio_queue.get()
                    if item is None:
                        break

            service = MagicMock()
            service.transcribe = mock_transcribe
            return service

        async def mock_translate(segment, session_id="", **kwargs):
            if segment.spoken_language == "vi":
                return segment.model_copy(update={"text_en": "hello"})
            return segment.model_copy(update={"text_vi": "xin"})

        with patch("app.routers.websocket.get_settings", return_value=settings), \
             patch("app.routers.websocket._DUAL_STREAM_WINDOW_SECONDS", 0.01), \
             patch("app.routers.websocket.TranscriptionService", side_effect=make_service), \
             patch("app.routers.websocket.translate_segment", new=mock_translate):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()
                    websocket.send_bytes(make_valid_audio_chunk())
                    websocket.send_text(make_stop_message())
                    received_msgs = collect_until_session_end(websocket, max_messages=10)

        assert chunks_by_language["vi-VN"] == [make_valid_audio_chunk()]
        assert chunks_by_language["en-US"] == [make_valid_audio_chunk()]
        finalized_msgs = [m for m in received_msgs if m["type"] == "finalized_segment"]
        assert len(finalized_msgs) == 1
        assert finalized_msgs[0]["segment_id"] == "vi-seg-1"
        assert finalized_msgs[0]["text_vi"] == "xin chao"
        assert finalized_msgs[0]["text_en"] == "hello"

    def test_dual_stream_prefers_english_candidate_for_english_speech(
        self, app, mock_logging
    ):
        settings = make_settings(bilingual_dual_stream=True)

        vi_msg = FinalizedSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="Sense my voice.",
            text_en="",
            spoken_language="vi",
            timestamp_start=0.0,
            timestamp_end=1.0,
        )
        en_msg = FinalizedSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="",
            text_en="Sense my voice.",
            spoken_language="en",
            timestamp_start=0.0,
            timestamp_end=1.0,
        )

        def make_service(*args, **kwargs):
            language_code = kwargs["language_code"]

            async def mock_transcribe(audio_queue):
                _ = await audio_queue.get()
                yield vi_msg if language_code == "vi-VN" else en_msg
                while True:
                    item = await audio_queue.get()
                    if item is None:
                        break

            service = MagicMock()
            service.transcribe = mock_transcribe
            return service

        async def mock_translate(segment, session_id="", **kwargs):
            if segment.spoken_language == "en":
                return segment.model_copy(update={"text_vi": "Cảm nhận giọng nói của tôi."})
            return segment.model_copy(update={"text_en": "Senza mi voce."})

        with patch("app.routers.websocket.get_settings", return_value=settings), \
             patch("app.routers.websocket._DUAL_STREAM_WINDOW_SECONDS", 0.01), \
             patch("app.routers.websocket.TranscriptionService", side_effect=make_service), \
             patch("app.routers.websocket.translate_segment", new=mock_translate):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()
                    websocket.send_bytes(make_valid_audio_chunk())
                    websocket.send_text(make_stop_message())
                    received_msgs = collect_until_session_end(websocket, max_messages=10)

        finalized_msgs = [m for m in received_msgs if m["type"] == "finalized_segment"]
        assert len(finalized_msgs) == 1
        assert finalized_msgs[0]["segment_id"] == "en-seg-1"
        assert finalized_msgs[0]["text_en"] == "Sense my voice."
        assert finalized_msgs[0]["text_vi"] == "Cảm nhận giọng nói của tôi."

    def test_dual_stream_forwards_partial_from_dominant_language(
        self, app, mock_logging
    ):
        """Live partials from the dominant (default source) stream are forwarded,
        and the off-language stream's partials are suppressed to avoid flicker."""
        settings = make_settings(bilingual_dual_stream=True)

        vi_partial = PartialSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="xin",
            text_en="",
            spoken_language="vi",
        )
        en_partial = PartialSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="",
            text_en="sin",
            spoken_language="en",
        )

        def make_service(*args, **kwargs):
            language_code = kwargs["language_code"]

            async def mock_transcribe(audio_queue):
                _ = await audio_queue.get()
                # Each stream emits only its own-language partial, then idles
                # until end-of-stream. No finalized segment is produced so the
                # dominant language stays at the default (vi).
                yield vi_partial if language_code == "vi-VN" else en_partial
                while True:
                    item = await audio_queue.get()
                    if item is None:
                        break

            service = MagicMock()
            service.transcribe = mock_transcribe
            return service

        async def mock_translate(segment, session_id="", **kwargs):
            return segment

        with patch("app.routers.websocket.get_settings", return_value=settings), \
             patch("app.routers.websocket.TranscriptionService", side_effect=make_service), \
             patch("app.routers.websocket.translate_segment", new=mock_translate):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()
                    websocket.send_bytes(make_valid_audio_chunk())
                    websocket.send_text(make_stop_message())
                    received_msgs = collect_until_session_end(websocket, max_messages=10)

        partial_msgs = [m for m in received_msgs if m["type"] == "partial_segment"]
        # The default source language is vi, so only the vi partial is shown.
        assert len(partial_msgs) >= 1
        assert all(m["spoken_language"] == "vi" for m in partial_msgs)
        assert partial_msgs[0]["segment_id"] == "vi-seg-1"
        assert partial_msgs[0]["text_vi"] == "xin"


# ---------------------------------------------------------------------------
# Binary frame routing to transcription (Req 2.3, 3.1)
# ---------------------------------------------------------------------------


class TestAudioFrameRouting:
    """Verify that binary frames are pushed to the transcription audio queue."""

    def test_valid_audio_chunk_is_accepted(self, app, mock_settings, mock_logging):
        """Valid audio should be validated and pushed to the audio queue."""

        audio_chunks_received = []

        async def mock_transcribe(audio_queue):
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                audio_chunks_received.append(chunk)
            if False:
                yield

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()  # session_start

                    # Send a valid audio chunk
                    chunk = make_valid_audio_chunk()
                    websocket.send_bytes(chunk)

                    # Send stop to close
                    websocket.send_text(make_stop_message())

                    # Drain remaining messages until session_end or disconnect
                    collect_until_session_end(websocket)

        # The audio chunk should have been received
        assert len(audio_chunks_received) >= 1
        assert audio_chunks_received[0] == make_valid_audio_chunk()


# ---------------------------------------------------------------------------
# Audio validation (Req 2.8)
# ---------------------------------------------------------------------------


class TestAudioValidation:
    """Verify that malformed audio is rejected with an error message."""

    def test_invalid_audio_chunk_triggers_error(self, app, mock_settings, mock_logging):
        """Invalid audio should trigger an INVALID_AUDIO_FORMAT error."""

        async def mock_transcribe(audio_queue):
            # Drain the queue — the error_event will cause None to be enqueued
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
            if False:
                yield

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()  # session_start

                    # Send an invalid audio chunk (odd byte count)
                    websocket.send_bytes(make_invalid_audio_chunk())

                    # Collect messages until session_end (no timeout needed —
                    # the mock transcribe terminates after draining the queue)
                    received_msgs = collect_until_session_end(websocket)

        # Should have received error and session_end
        error_msgs = [m for m in received_msgs if m["type"] == "error"]
        assert len(error_msgs) >= 1
        error = error_msgs[0]
        assert error["code"] == ErrorCode.INVALID_AUDIO_FORMAT.value
        assert "message" in error

        session_end_msgs = [m for m in received_msgs if m["type"] == "session_end"]
        assert len(session_end_msgs) >= 1

    def test_invalid_audio_stops_session(self, app, mock_settings, mock_logging):
        """After invalid audio, the session should end gracefully."""

        async def mock_transcribe(audio_queue):
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
            if False:
                yield

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()  # session_start

                    websocket.send_bytes(make_invalid_audio_chunk())

                    received_msgs = collect_until_session_end(websocket)

        # session_end should have been sent
        assert any(m["type"] == "session_end" for m in received_msgs)


# ---------------------------------------------------------------------------
# JSON stop signal handling (Req 2.4)
# ---------------------------------------------------------------------------


class TestStopSignalHandling:
    """Verify that the stop signal triggers graceful session teardown."""

    def test_stop_signal_triggers_session_end(self, app, mock_settings, mock_logging):
        """Sending {"type": "stop"} should result in a session_end message."""

        async def mock_transcribe(audio_queue):
            # Wait until the queue sends None (which happens when stop is received)
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
            if False:
                yield

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()  # session_start

                    # Send stop
                    websocket.send_text(make_stop_message())

                    # Collect messages until session_end
                    received_msgs = collect_until_session_end(websocket)

        session_end_msgs = [m for m in received_msgs if m["type"] == "session_end"]
        assert len(session_end_msgs) >= 1


# ---------------------------------------------------------------------------
# Segment message forwarding (Req 3.2, 3.3)
# ---------------------------------------------------------------------------


class TestSegmentForwarding:
    """Verify that partial and finalized segments are forwarded to the client."""

    def test_partial_segment_is_forwarded(self, app, mock_settings, mock_logging):
        """Partial segments from TranscriptionService are sent to the client."""

        partial_msg = PartialSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="Xin",
            text_en="",
            spoken_language="vi",
        )

        async def mock_transcribe(audio_queue):
            _ = await audio_queue.get()  # consume one chunk
            yield partial_msg
            # Drain remaining queue items (stop sentinel)
            while True:
                item = await audio_queue.get()
                if item is None:
                    break

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService, patch(
            "app.routers.websocket.translate_segment", new_callable=AsyncMock
        ):
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()  # session_start

                    websocket.send_bytes(make_valid_audio_chunk())
                    websocket.send_text(make_stop_message())

                    # Collect all messages until session_end
                    received_msgs = collect_until_session_end(websocket)

        # Partial segment should be present
        partial_msgs = [m for m in received_msgs if m["type"] == "partial_segment"]
        assert len(partial_msgs) >= 1
        assert partial_msgs[0]["segment_id"] == "seg-1"

    def test_finalized_segment_is_translated_and_forwarded(
        self, app, mock_settings, mock_logging
    ):
        """Finalized segments are translated then forwarded."""

        finalized_msg = FinalizedSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="Xin chào",
            text_en="",
            spoken_language="vi",
            timestamp_start=0.0,
            timestamp_end=1.0,
        )

        translated_segment = Segment(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="Xin chào",
            text_en="Hello",
            spoken_language="vi",
            is_final=True,
            timestamp_start=0.0,
            timestamp_end=1.0,
        )

        async def mock_transcribe(audio_queue):
            _ = await audio_queue.get()  # consume chunk
            yield finalized_msg
            # Drain remaining queue items (stop sentinel)
            while True:
                item = await audio_queue.get()
                if item is None:
                    break

        async def mock_translate(segment, session_id="", **kwargs):
            return translated_segment

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService, patch(
            "app.routers.websocket.translate_segment", new=mock_translate
        ):
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()  # session_start

                    websocket.send_bytes(make_valid_audio_chunk())
                    websocket.send_text(make_stop_message())

                    # Collect all messages until session_end
                    received_msgs = collect_until_session_end(websocket)

        # Finalized segment with translation should be present
        finalized_msgs = [m for m in received_msgs if m["type"] == "finalized_segment"]
        assert len(finalized_msgs) >= 1
        assert finalized_msgs[0]["segment_id"] == "seg-1"
        assert finalized_msgs[0]["text_vi"] == "Xin chào"
        assert finalized_msgs[0]["text_en"] == "Hello"


# ---------------------------------------------------------------------------
# Translation error handling (Req 5.3)
# ---------------------------------------------------------------------------


class TestTranslationErrorHandling:
    """Verify that translation errors are logged and untranslated segment forwarded."""

    def test_translation_error_forwards_untranslated_segment(
        self, app, mock_settings, mock_logging
    ):
        """If translation fails, the original segment should still be sent."""

        finalized_msg = FinalizedSegmentMessage(
            segment_id="seg-1",
            speaker_label="Speaker 1",
            text_vi="Xin chào",
            text_en="",
            spoken_language="vi",
            timestamp_start=0.0,
            timestamp_end=1.0,
        )

        async def mock_transcribe(audio_queue):
            _ = await audio_queue.get()
            yield finalized_msg
            # Drain remaining queue items
            while True:
                item = await audio_queue.get()
                if item is None:
                    break

        async def mock_translate_fail(segment, session_id="", **kwargs):
            raise RuntimeError("Translation service unavailable")

        with patch(
            "app.routers.websocket.TranscriptionService"
        ) as MockTranscriptionService, patch(
            "app.routers.websocket.translate_segment", new=mock_translate_fail
        ), patch(
            "app.routers.websocket.log_integration_error"
        ):
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()  # session_start

                    websocket.send_bytes(make_valid_audio_chunk())
                    websocket.send_text(make_stop_message())

                    received_msgs = collect_until_session_end(websocket)

        # Original untranslated segment should have been forwarded
        finalized_msgs = [m for m in received_msgs if m["type"] == "finalized_segment"]
        assert len(finalized_msgs) >= 1
        assert finalized_msgs[0]["text_vi"] == "Xin chào"
        # text_en remains empty since translation failed
        assert finalized_msgs[0]["text_en"] == ""


# ---------------------------------------------------------------------------
# Session timeout (Req 2.5)
# ---------------------------------------------------------------------------


class TestSessionTimeout:
    """Verify that sessions are bounded by the configured timeout."""

    def test_session_timeout_sends_error_and_session_end(
        self, app, mock_logging
    ):
        """Session exceeding timeout should send SESSION_TIMEOUT error."""

        async def mock_transcribe_hang(audio_queue):
            # Simulate a long-running transcription that exceeds timeout
            await asyncio.sleep(100)  # never yields within the timeout window
            if False:
                yield

        with patch("app.routers.websocket.get_settings", return_value=make_settings(session_timeout=1)), \
             patch("app.routers.websocket.TranscriptionService") as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe_hang
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()  # session_start

                    websocket.send_bytes(make_valid_audio_chunk())

                    # The server will time out after 1 second and send
                    # error + session_end then close the connection.
                    # collect_until_session_end blocks on receive_text() until
                    # the server sends these messages or closes the connection.
                    received_msgs = collect_until_session_end(websocket, max_messages=10)

        # Should have received SESSION_TIMEOUT error
        error_msgs = [m for m in received_msgs if m["type"] == "error"]
        assert len(error_msgs) >= 1
        assert error_msgs[0]["code"] == ErrorCode.SESSION_TIMEOUT.value

        # Should have received session_end
        session_end_msgs = [m for m in received_msgs if m["type"] == "session_end"]
        assert len(session_end_msgs) >= 1


# ---------------------------------------------------------------------------
# Logging (Req 10.1, 10.2)
# ---------------------------------------------------------------------------


class TestLogging:
    """Verify that session start/end events are logged."""

    def test_session_start_is_logged(self, app, mock_settings):
        """log_session_start should be called when a session begins."""

        async def mock_transcribe(audio_queue):
            # Drain until stop sentinel
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
            if False:
                yield

        with patch("app.routers.websocket.log_session_start") as mock_log_start, \
             patch("app.routers.websocket.log_session_end"), \
             patch("app.routers.websocket.log_websocket_connect"), \
             patch("app.routers.websocket.log_websocket_disconnect"), \
             patch("app.routers.websocket.TranscriptionService") as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()  # session_start
                    websocket.send_text(make_stop_message())
                    collect_until_session_end(websocket)

            mock_log_start.assert_called_once()

    def test_session_end_is_logged(self, app, mock_settings):
        """log_session_end should be called when a session ends."""

        async def mock_transcribe(audio_queue):
            # Drain until stop sentinel
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
            if False:
                yield

        with patch("app.routers.websocket.log_session_start"), \
             patch("app.routers.websocket.log_session_end") as mock_log_end, \
             patch("app.routers.websocket.log_websocket_connect"), \
             patch("app.routers.websocket.log_websocket_disconnect"), \
             patch("app.routers.websocket.TranscriptionService") as MockTranscriptionService:
            mock_service_instance = MagicMock()
            mock_service_instance.transcribe = mock_transcribe
            MockTranscriptionService.return_value = mock_service_instance

            with TestClient(app) as client:
                with client.websocket_connect("/ws/transcribe") as websocket:
                    _ = websocket.receive_text()  # session_start
                    websocket.send_text(make_stop_message())
                    collect_until_session_end(websocket)

            mock_log_end.assert_called_once()
