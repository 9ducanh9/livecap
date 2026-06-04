"""Unit tests for backend/app/services/logging_service.py.

Covers:
- setup_logging() configures a logger without raising
- Fallback to stdout when CloudWatch is unavailable
- log_session_start() emits a structured record with the correct event key
  and session_id (Requirement 10.1)
- log_session_end() emits a structured record with the correct event key
  and session_id (Requirement 10.2)
- log_integration_error() emits a structured record containing session_id,
  service_name, error details (Requirement 10.3)
- get_logger() returns a Logger instance
- No duplicate handlers when setup_logging() is called twice
"""

from __future__ import annotations

import importlib
import json
import logging
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_service():
    """Re-import the module with a clean logger state."""
    import app.services.logging_service as mod  # noqa: PLC0415

    # Remove all handlers and reset the internal logger so each test starts
    # from a known state.
    logger = logging.getLogger(mod.LOGGER_NAME)
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    # Reset the cached module-level logger reference
    importlib.reload(mod)
    return mod


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


def _make_mock_watchtower():
    """Return a mock watchtower module with a CloudWatchLogHandler class."""
    mock_wt = MagicMock()
    mock_handler_instance = MagicMock(spec=logging.Handler)
    mock_handler_instance.level = logging.DEBUG
    mock_wt.CloudWatchLogHandler.return_value = mock_handler_instance
    return mock_wt, mock_handler_instance


def _make_mock_boto3():
    mock_b3 = MagicMock()
    mock_b3.client.return_value = MagicMock()
    return mock_b3


class TestSetupLogging:
    def test_no_exception_when_cloudwatch_unavailable(self):
        """setup_logging() must not raise even when boto3/watchtower fail."""
        mod = _reload_service()
        # Inject fake modules that fail during CloudWatchLogHandler construction.
        mock_wt = MagicMock()
        mock_wt.CloudWatchLogHandler.side_effect = Exception("no creds")
        mock_b3 = _make_mock_boto3()
        with patch.dict(sys.modules, {"watchtower": mock_wt, "boto3": mock_b3}):
            # Should not raise.
            mod.setup_logging()

    def test_fallback_adds_stream_handler(self):
        """When CloudWatch init fails, a StreamHandler is added."""
        mod = _reload_service()
        mock_wt = MagicMock()
        mock_wt.CloudWatchLogHandler.side_effect = Exception("no creds")
        mock_b3 = _make_mock_boto3()
        with patch.dict(sys.modules, {"watchtower": mock_wt, "boto3": mock_b3}):
            mod.setup_logging()
        logger = logging.getLogger(mod.LOGGER_NAME)
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)

    def test_no_duplicate_handlers(self):
        """Calling setup_logging() twice must not add a second handler."""
        mod = _reload_service()
        mock_wt = MagicMock()
        mock_wt.CloudWatchLogHandler.side_effect = Exception("no creds")
        mock_b3 = _make_mock_boto3()
        with patch.dict(sys.modules, {"watchtower": mock_wt, "boto3": mock_b3}):
            mod.setup_logging()
            handler_count_after_first = len(logging.getLogger(mod.LOGGER_NAME).handlers)
            mod.setup_logging()
            handler_count_after_second = len(logging.getLogger(mod.LOGGER_NAME).handlers)
        assert handler_count_after_first == handler_count_after_second

    def test_cloudwatch_handler_attached_when_available(self):
        """When watchtower succeeds, a CloudWatchLogHandler is added."""
        mod = _reload_service()

        mock_wt, mock_handler_instance = _make_mock_watchtower()
        mock_b3 = _make_mock_boto3()

        with patch.dict(sys.modules, {"watchtower": mock_wt, "boto3": mock_b3}):
            mod.setup_logging()

        logger = logging.getLogger(mod.LOGGER_NAME)
        assert mock_handler_instance in logger.handlers


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class TestJsonFormatter:
    """Verify that records are emitted as parseable JSON with required keys."""

    def _capture_output(self, mod) -> tuple[StringIO, logging.StreamHandler]:
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(mod._JsonFormatter())
        logger = logging.getLogger(mod.LOGGER_NAME)
        logger.addHandler(handler)
        return buf, handler

    def test_log_record_is_valid_json(self):
        mod = _reload_service()
        buf, handler = self._capture_output(mod)
        try:
            logging.getLogger(mod.LOGGER_NAME).info("test message")
            output = buf.getvalue().strip()
            parsed = json.loads(output)
            assert parsed["message"] == "test message"
            assert "timestamp" in parsed
            assert "level" in parsed
        finally:
            logging.getLogger(mod.LOGGER_NAME).removeHandler(handler)

    def test_extra_fields_included(self):
        mod = _reload_service()
        buf, handler = self._capture_output(mod)
        try:
            logging.getLogger(mod.LOGGER_NAME).info(
                "with extras", extra={"session_id": "s-123", "event": "test_event"}
            )
            parsed = json.loads(buf.getvalue().strip())
            assert parsed["session_id"] == "s-123"
            assert parsed["event"] == "test_event"
        finally:
            logging.getLogger(mod.LOGGER_NAME).removeHandler(handler)

    def test_exception_info_included(self):
        mod = _reload_service()
        buf, handler = self._capture_output(mod)
        try:
            try:
                raise ValueError("boom")
            except ValueError:
                logging.getLogger(mod.LOGGER_NAME).exception("caught error")
            parsed = json.loads(buf.getvalue().strip())
            assert "exception" in parsed
            assert "ValueError" in parsed["exception"]
        finally:
            logging.getLogger(mod.LOGGER_NAME).removeHandler(handler)


# ---------------------------------------------------------------------------
# log_session_start  (Requirement 10.1)
# ---------------------------------------------------------------------------


class TestLogSessionStart:
    def test_emits_session_start_event(self):
        mod = _reload_service()
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(mod._JsonFormatter())
        logging.getLogger(mod.LOGGER_NAME).addHandler(handler)

        try:
            mod.log_session_start("sess-abc")
            record = json.loads(buf.getvalue().strip())
            assert record["event"] == "session_start"
            assert record["session_id"] == "sess-abc"
            assert record["level"] == "INFO"
        finally:
            logging.getLogger(mod.LOGGER_NAME).removeHandler(handler)

    def test_accepts_arbitrary_session_id(self):
        mod = _reload_service()
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(mod._JsonFormatter())
        logging.getLogger(mod.LOGGER_NAME).addHandler(handler)

        try:
            mod.log_session_start("550e8400-e29b-41d4-a716-446655440000")
            record = json.loads(buf.getvalue().strip())
            assert record["session_id"] == "550e8400-e29b-41d4-a716-446655440000"
        finally:
            logging.getLogger(mod.LOGGER_NAME).removeHandler(handler)


# ---------------------------------------------------------------------------
# log_session_end  (Requirement 10.2)
# ---------------------------------------------------------------------------


class TestLogSessionEnd:
    def test_emits_session_end_event(self):
        mod = _reload_service()
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(mod._JsonFormatter())
        logging.getLogger(mod.LOGGER_NAME).addHandler(handler)

        try:
            mod.log_session_end("sess-xyz")
            record = json.loads(buf.getvalue().strip())
            assert record["event"] == "session_end"
            assert record["session_id"] == "sess-xyz"
            assert record["level"] == "INFO"
        finally:
            logging.getLogger(mod.LOGGER_NAME).removeHandler(handler)


# ---------------------------------------------------------------------------
# log_integration_error  (Requirement 10.3)
# ---------------------------------------------------------------------------


class TestLogIntegrationError:
    def _make_record(self, mod, session_id, service_name, exc) -> dict:
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(mod._JsonFormatter())
        logging.getLogger(mod.LOGGER_NAME).addHandler(handler)
        try:
            mod.log_integration_error(session_id, service_name, exc)
            return json.loads(buf.getvalue().strip())
        finally:
            logging.getLogger(mod.LOGGER_NAME).removeHandler(handler)

    def test_event_key(self):
        mod = _reload_service()
        record = self._make_record(mod, "s-1", "Amazon S3", RuntimeError("upload failed"))
        assert record["event"] == "integration_error"

    def test_session_id_included(self):
        mod = _reload_service()
        record = self._make_record(mod, "s-42", "Amazon Translate", ValueError("timeout"))
        assert record["session_id"] == "s-42"

    def test_service_name_included(self):
        mod = _reload_service()
        record = self._make_record(mod, "s-1", "Amazon Transcribe Streaming", IOError("net"))
        assert record["service_name"] == "Amazon Transcribe Streaming"

    def test_error_type_included(self):
        mod = _reload_service()
        record = self._make_record(mod, "s-1", "Amazon S3", TypeError("bad type"))
        assert record["error_type"] == "TypeError"

    def test_error_message_included(self):
        mod = _reload_service()
        exc = RuntimeError("bucket not found")
        record = self._make_record(mod, "s-1", "Amazon S3", exc)
        assert "bucket not found" in record["error_message"]

    def test_level_is_error(self):
        mod = _reload_service()
        record = self._make_record(mod, "s-1", "Amazon Translate", Exception("err"))
        assert record["level"] == "ERROR"

    @pytest.mark.parametrize(
        "service",
        [
            "Amazon Transcribe Streaming",
            "Amazon Translate",
            "Amazon S3",
        ],
    )
    def test_all_integration_services(self, service):
        mod = _reload_service()
        record = self._make_record(mod, "s-1", service, RuntimeError("fail"))
        assert record["service_name"] == service


# ---------------------------------------------------------------------------
# Convenience WebSocket helpers
# ---------------------------------------------------------------------------


class TestWebSocketHelpers:
    def _make_record(self, mod, fn, *args) -> dict:
        buf = StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(mod._JsonFormatter())
        logging.getLogger(mod.LOGGER_NAME).addHandler(handler)
        try:
            fn(*args)
            return json.loads(buf.getvalue().strip())
        finally:
            logging.getLogger(mod.LOGGER_NAME).removeHandler(handler)

    def test_websocket_connect(self):
        mod = _reload_service()
        record = self._make_record(mod, mod.log_websocket_connect, "sess-1")
        assert record["event"] == "websocket_connect"
        assert record["session_id"] == "sess-1"

    def test_websocket_disconnect(self):
        mod = _reload_service()
        record = self._make_record(mod, mod.log_websocket_disconnect, "sess-2")
        assert record["event"] == "websocket_disconnect"
        assert record["session_id"] == "sess-2"


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_logger_instance(self):
        mod = _reload_service()
        logger = mod.get_logger()
        assert isinstance(logger, logging.Logger)

    def test_returns_named_logger(self):
        mod = _reload_service()
        logger = mod.get_logger()
        assert logger.name == mod.LOGGER_NAME

    def test_same_instance_on_repeated_calls(self):
        mod = _reload_service()
        assert mod.get_logger() is mod.get_logger()
