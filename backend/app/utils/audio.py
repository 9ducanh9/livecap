"""Audio format validation utilities.

Validates that incoming binary frames conform to the Expected_Audio_Format:
PCM, 16-bit, mono, 16 kHz.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Expected_Audio_Format constants
# ---------------------------------------------------------------------------

EXPECTED_SAMPLE_RATE: int = 16_000       # Hz
EXPECTED_BIT_DEPTH: int = 16             # bits per sample
EXPECTED_CHANNELS: int = 1              # mono
EXPECTED_BYTES_PER_SAMPLE: int = EXPECTED_BIT_DEPTH // 8  # 2 bytes

# Chunk duration target: ~100 ms
_CHUNK_DURATION_MS: int = 100
_CHUNK_DURATION_S: float = _CHUNK_DURATION_MS / 1000.0

# Expected bytes for one ~100 ms chunk: 16000 samples/s * 2 bytes * 0.1 s = 3200
EXPECTED_CHUNK_BYTES: int = int(
    EXPECTED_SAMPLE_RATE * EXPECTED_BYTES_PER_SAMPLE * _CHUNK_DURATION_S
)

# Reasonable size limits: accept up to 10× the nominal 100 ms chunk (1 second).
_MAX_CHUNK_BYTES: int = EXPECTED_CHUNK_BYTES * 10  # 32 000 bytes

# Human-readable format description used in rejection messages.
_FORMAT_DESCRIPTION: str = (
    f"Expected PCM 16-bit mono audio at {EXPECTED_SAMPLE_RATE} Hz sample rate"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_audio_chunk(data: bytes) -> tuple[bool, str | None]:
    """Validate that *data* is a plausible PCM 16-bit mono 16 kHz audio chunk.

    Since raw PCM carries no header, structural validation is limited to
    properties that can be inferred from the byte layout:

    1. Non-empty – the frame must contain at least one sample.
    2. Even byte count – 16-bit samples occupy exactly 2 bytes each, so the
       total payload must be divisible by 2.
    3. Reasonable size – the frame must not exceed ~1 second of audio at the
       expected format (32 000 bytes), which guards against accidental
       delivery of differently-formatted or corrupted data.

    Args:
        data: Raw bytes from a WebSocket binary frame.

    Returns:
        ``(True, None)`` when *data* passes all checks.
        ``(False, reason)`` when a check fails, where *reason* is a
        human-readable string describing the expected format.
    """
    if not data:
        return False, f"Audio chunk is empty. {_FORMAT_DESCRIPTION}."

    if len(data) % EXPECTED_BYTES_PER_SAMPLE != 0:
        return (
            False,
            f"Audio chunk has an odd byte count ({len(data)} bytes), which is "
            f"incompatible with 16-bit samples. {_FORMAT_DESCRIPTION}.",
        )

    if len(data) > _MAX_CHUNK_BYTES:
        return (
            False,
            f"Audio chunk is too large ({len(data)} bytes; maximum is "
            f"{_MAX_CHUNK_BYTES} bytes for ~1 s of audio). {_FORMAT_DESCRIPTION}.",
        )

    return True, None
