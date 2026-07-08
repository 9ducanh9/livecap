"""Tests for application configuration helpers."""

from app.config import DEFAULT_ALLOWED_ORIGIN, Settings


def test_allowed_origins_supports_multiple_exact_origins() -> None:
    settings = Settings(
        allowed_origin=(
            "https://livecap.logantai.com,"
            "https://dpeohr327wt9l.cloudfront.net"
        )
    )

    assert settings.allowed_origins == (
        "https://livecap.logantai.com",
        "https://dpeohr327wt9l.cloudfront.net",
    )


def test_allowed_origins_removes_blanks_and_duplicates() -> None:
    settings = Settings(allowed_origin=" https://example.com, ,https://example.com ")

    assert settings.allowed_origins == ("https://example.com",)


def test_allowed_origins_falls_back_to_local_default() -> None:
    settings = Settings(allowed_origin=" , ")

    assert settings.allowed_origins == (DEFAULT_ALLOWED_ORIGIN,)
