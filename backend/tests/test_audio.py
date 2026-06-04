"""Unit tests for backend/app/utils/audio.py.

Covers validate_audio_chunk: empty input, odd byte count, oversized chunks,
valid chunks, and boundary cases.
"""

from __future__ import annotations

import struct

import pytest

from app.utils.audio import (
    EXPECTED_CHUNK_BYTES,
    EXPECTED_BYTES_PER_SAMPLE,
    EXPECTED_SAMPLE_RATE,
    _MAX_CHUNK_BYTES,
    validate_audio_chunk,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_pcm_frame(num_samples: int, value: int = 0) -> bytes:
    """Return *num_samples* silent (or constant-value) 16-bit PCM samples."""
    return struct.pack(f"<{num_samples}h", *([value] * num_samples))


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


class TestEmptyChunk:
    def test_empty_bytes_rejected(self):
        is_valid, reason = validate_audio_chunk(b"")
        assert is_valid is False
        assert reason is not None
        assert len(reason) > 0

    def test_empty_rejection_mentions_format(self):
        _, reason = validate_audio_chunk(b"")
        assert "16" in reason  # 16-bit or 16000 Hz
        assert reason is not None


# ---------------------------------------------------------------------------
# Odd byte count (incompatible with 16-bit samples)
# ---------------------------------------------------------------------------


class TestOddByteCount:
    def test_single_byte_rejected(self):
        is_valid, reason = validate_audio_chunk(b"\x00")
        assert is_valid is False
        assert reason is not None

    def test_three_bytes_rejected(self):
        is_valid, reason = validate_audio_chunk(b"\x00\x01\x02")
        assert is_valid is False

    def test_odd_byte_reason_mentions_16bit(self):
        _, reason = validate_audio_chunk(b"\x01")
        assert "16" in reason

    def test_large_odd_count_rejected(self):
        # 3199 bytes: odd count just below nominal chunk size
        data = bytes(3199)
        is_valid, _ = validate_audio_chunk(data)
        assert is_valid is False


# ---------------------------------------------------------------------------
# Oversized chunks
# ---------------------------------------------------------------------------


class TestOversizedChunk:
    def test_chunk_just_over_max_rejected(self):
        # _MAX_CHUNK_BYTES + 2 (even, so not tripped by odd-byte check)
        data = bytes(_MAX_CHUNK_BYTES + 2)
        is_valid, reason = validate_audio_chunk(data)
        assert is_valid is False
        assert reason is not None

    def test_very_large_chunk_rejected(self):
        data = bytes(_MAX_CHUNK_BYTES * 2)
        is_valid, _ = validate_audio_chunk(data)
        assert is_valid is False

    def test_oversized_reason_mentions_max(self):
        data = bytes(_MAX_CHUNK_BYTES + 2)
        _, reason = validate_audio_chunk(data)
        assert str(_MAX_CHUNK_BYTES) in reason


# ---------------------------------------------------------------------------
# Valid chunks
# ---------------------------------------------------------------------------


class TestValidChunks:
    def test_nominal_100ms_chunk_accepted(self):
        # Exactly EXPECTED_CHUNK_BYTES of silence
        data = bytes(EXPECTED_CHUNK_BYTES)
        is_valid, reason = validate_audio_chunk(data)
        assert is_valid is True
        assert reason is None

    def test_two_byte_minimum_chunk_accepted(self):
        # Smallest possible valid chunk: a single 16-bit sample
        data = make_pcm_frame(1)
        is_valid, reason = validate_audio_chunk(data)
        assert is_valid is True
        assert reason is None

    def test_max_size_chunk_accepted(self):
        # Exactly at the upper bound (even byte count)
        data = bytes(_MAX_CHUNK_BYTES)
        is_valid, reason = validate_audio_chunk(data)
        assert is_valid is True
        assert reason is None

    def test_50ms_chunk_accepted(self):
        # Half of nominal 100 ms chunk
        num_samples = EXPECTED_SAMPLE_RATE // 20  # 800 samples
        data = make_pcm_frame(num_samples)
        is_valid, reason = validate_audio_chunk(data)
        assert is_valid is True
        assert reason is None

    def test_nonzero_audio_accepted(self):
        # Non-silent PCM data
        data = make_pcm_frame(1600, value=1000)
        is_valid, reason = validate_audio_chunk(data)
        assert is_valid is True
        assert reason is None


# ---------------------------------------------------------------------------
# Boundary conditions
# ---------------------------------------------------------------------------


class TestBoundaryConditions:
    def test_exactly_max_bytes_even_valid(self):
        data = bytes(_MAX_CHUNK_BYTES)
        is_valid, _ = validate_audio_chunk(data)
        assert is_valid is True

    def test_one_over_max_even_invalid(self):
        data = bytes(_MAX_CHUNK_BYTES + 2)
        is_valid, _ = validate_audio_chunk(data)
        assert is_valid is False

    def test_return_type_on_valid(self):
        data = bytes(EXPECTED_CHUNK_BYTES)
        result = validate_audio_chunk(data)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] is True
        assert result[1] is None

    def test_return_type_on_invalid(self):
        result = validate_audio_chunk(b"")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] is False
        assert isinstance(result[1], str)
