"""Tests for B5 session-id continuity on reconnect (`_resolve_session_id`)."""

from __future__ import annotations

import uuid

from app.routers.websocket import _resolve_session_id


class _FakeWebSocket:
    def __init__(self, params: dict[str, str]) -> None:
        self.query_params = params


def test_reuses_valid_uuid():
    sid = str(uuid.uuid4())
    assert _resolve_session_id(_FakeWebSocket({"session_id": sid})) == sid


def test_mints_new_uuid_when_absent():
    out = _resolve_session_id(_FakeWebSocket({}))
    uuid.UUID(out)  # does not raise → valid UUID


def test_mints_new_uuid_when_invalid():
    out = _resolve_session_id(_FakeWebSocket({"session_id": "not-a-uuid"}))
    uuid.UUID(out)
    assert out != "not-a-uuid"


def test_normalizes_uuid_string():
    raw = "12345678123412341234123456789012"
    assert _resolve_session_id(_FakeWebSocket({"session_id": raw})) == str(uuid.UUID(raw))
