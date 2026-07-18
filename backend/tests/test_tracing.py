"""Tests for optional X-Ray tracing setup (C4). No AWS/daemon needed."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI

from app.tracing import configure_tracing, xray_enabled


def test_xray_enabled_reads_env(monkeypatch):
    monkeypatch.setenv("ENABLE_XRAY", "true")
    assert xray_enabled() is True
    monkeypatch.setenv("ENABLE_XRAY", "false")
    assert xray_enabled() is False
    monkeypatch.delenv("ENABLE_XRAY", raising=False)
    assert xray_enabled() is False


def test_configure_disabled_is_noop(monkeypatch):
    monkeypatch.delenv("ENABLE_XRAY", raising=False)
    app = FastAPI()
    before = len(app.user_middleware)
    assert configure_tracing(app) is False
    assert len(app.user_middleware) == before


def test_configure_enabled_adds_middleware(monkeypatch):
    monkeypatch.setenv("ENABLE_XRAY", "true")
    app = FastAPI()

    import aws_xray_sdk.core as xcore

    with patch.object(xcore, "patch_all") as mock_patch, patch.object(
        xcore.xray_recorder, "configure"
    ) as mock_configure:
        result = configure_tracing(app)

    assert result is True
    mock_patch.assert_called_once()
    mock_configure.assert_called_once()
    assert any(
        m.cls.__name__ == "_XRayHttpMiddleware" for m in app.user_middleware
    )
