"""Offline contract tests. Generated audio/fake results are tests, not evidence."""
from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import io
import json
import socket
import tempfile
import unittest
import uuid
import wave
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from tools import ws_load_test as harness

TOKEN = "eyJTEST.access.private_signature"
TRANSCRIPT = "PRIVATE_TRANSCRIPT_DO_NOT_EXPORT"
URL = "ws://localhost:8000/ws/transcribe"


def make_wav(path: Path, samples: int = 4000, channels: int = 1,
             width: int = 2, rate: int = 16000) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(bytes(samples * channels * width))
    return path


class FakeClock(harness.Clock):
    def __init__(self) -> None:
        self.value = 100.0
        self.sleeps = []

    def now(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds
        await asyncio.sleep(0)


class FakeClosed(ConnectionError):
    def __init__(self, code: int = 1000, reason: str = "") -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class FakeSocket:
    def __init__(self, clock: FakeClock, *, rejection=None, error=None,
                 disconnect=False, target=True, captions=True, end=True,
                 send_failure=False, block_send=False, malformed=False, remote_close_code=1000):
        self.clock = clock
        self.rejection = rejection
        self.error = error
        self.disconnect = disconnect
        self.target = target
        self.captions = captions
        self.end = end
        self.send_failure = send_failure
        self.block_send = block_send
        self.malformed = malformed
        self.remote_close_code = remote_close_code
        self.close_code = None
        self.close_reason = None
        self.subprotocol = "livecap.v1"
        self.messages = asyncio.Queue()
        self.sent = []
        self.stop_requested = False
        self.partial_received_before_stop = False
        self.frames_sent = 0
        first = ({"type": "error", "code": rejection, "message": TOKEN + TRANSCRIPT}
                 if rejection else {"type": "session_start", "session_id": str(uuid.uuid4())})
        self.messages.put_nowait(json.dumps(first))

    async def recv(self):
        value = await self.messages.get()
        if isinstance(value, Exception):
            if isinstance(value, FakeClosed):
                self.close_code, self.close_reason = value.code, value.reason
            raise value
        if isinstance(value, str) and '"type": "partial_segment"' in value:
            self.partial_received_before_stop |= not self.stop_requested
        return value

    async def send(self, value):
        self.sent.append(value)
        if self.send_failure:
            raise RuntimeError(TOKEN + TRANSCRIPT)
        if isinstance(value, bytes):
            self.frames_sent += 1
            if self.block_send:
                await asyncio.Event().wait()
            if self.frames_sent == 1:
                if self.malformed:
                    self.messages.put_nowait("not json " + TOKEN + TRANSCRIPT)
                elif self.disconnect:
                    self.messages.put_nowait(FakeClosed(1006, TOKEN + TRANSCRIPT))
                elif self.error:
                    self.messages.put_nowait(json.dumps({
                        "type": "error", "code": self.error, "message": TOKEN + TRANSCRIPT}))
                elif self.captions:
                    self.messages.put_nowait(json.dumps({
                        "type": "partial_segment", "segment_id": "vi-seg-1",
                        "spoken_language": "vi", "text_vi": TRANSCRIPT, "text_en": ""}))
        else:
            self.stop_requested = True
            if self.captions:
                self.messages.put_nowait(json.dumps({
                    "type": "finalized_segment", "segment_id": "vi-seg-1",
                    "spoken_language": "vi", "text_vi": TRANSCRIPT,
                    "text_en": TRANSCRIPT if self.target else "",
                    "timestamp_start": 0.0, "timestamp_end": 0.25, "is_final": True}))
            if self.end:
                self.messages.put_nowait(json.dumps({"type": "session_end"}))
                if self.remote_close_code is not None:
                    self.messages.put_nowait(FakeClosed(self.remote_close_code))
        await asyncio.sleep(0)

    async def close(self):
        if self.close_code is None:
            self.close_code = 1000
        await asyncio.sleep(0)


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Reject even accidental real network calls, including injected fallback.
        for name in ("connect", "connect_ex"):
            guard = patch.object(socket.socket, name, side_effect=AssertionError("Network forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        guard = patch("socket.create_connection", side_effect=AssertionError("Network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)


class AudioTests(OfflineCase):
    def test_wav_duration_frames_and_fixture_hash(self):
        path = make_wav(self.root / "speech.wav")
        fixture = harness.validate_wav(path)
        frames = list(fixture.frames())
        self.assertEqual(fixture.duration, 0.25)
        self.assertEqual([start for start, _ in frames], [0, 1600, 3200])
        self.assertEqual([len(data) for _, data in frames], [3200, 3200, 1600])
        self.assertEqual(fixture.sha256, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(fixture.pcm_sha256, hashlib.sha256(bytes(8000)).hexdigest())

    def test_wav_validation_rejects_wrong_format(self):
        for kwargs in ({"channels": 2}, {"width": 1}, {"width": 3}, {"rate": 44100},
                       {"samples": 0}):
            with self.subTest(kwargs=kwargs):
                path = make_wav(self.root / "bad.wav", **kwargs)
                with self.assertRaises(ValueError):
                    harness.validate_wav(path)

    def test_invalid_compressed_truncated_and_missing_wav(self):
        with self.assertRaises(ValueError):
            harness.validate_wav(self.root / "missing.wav")
        path = self.root / "invalid.wav"
        path.write_bytes(b"not a wav")
        with self.assertRaises(ValueError):
            harness.validate_wav(path)
        make_wav(path)
        data = bytearray(path.read_bytes())
        data[20:22] = (3).to_bytes(2, "little")  # IEEE float, not PCM.
        path.write_bytes(data)
        with self.assertRaises(ValueError):
            harness.validate_wav(path)
        make_wav(path)
        path.write_bytes(path.read_bytes()[:-12])
        with self.assertRaises(ValueError):
            harness.validate_wav(path)

    def test_pcm_reads_are_bounded(self):
        path = make_wav(self.root / "long.wav", samples=160000)
        original = wave.Wave_read.readframes
        sizes = []

        def bounded(wav, count):
            sizes.append(count)
            return original(wav, count)

        with patch.object(wave.Wave_read, "readframes", bounded):
            fixture = harness.validate_wav(path)
            self.assertEqual(sum(len(b) for _, b in fixture.frames()), 320000)
        self.assertLessEqual(max(sizes), 32768)

    def test_silent_frames_preserve_100ms_pcm_and_partial_tail(self):
        fixture = harness.AudioFixture("silent", 4000)
        self.assertEqual([len(b) for _, b in fixture.frames()], [3200, 3200, 1600])
        self.assertTrue(all(not any(b) for _, b in fixture.frames()))

    def test_replay_detects_fixture_truncation(self):
        path = make_wav(self.root / "changed.wav")
        fixture = harness.validate_wav(path)
        path.write_bytes(path.read_bytes()[:-4000])
        with self.assertRaises(ValueError):
            list(fixture.frames())


class MetricTests(OfflineCase):
    def test_nearest_rank_small_samples_and_exact_95_boundary(self):
        values = list(range(1, 21))
        self.assertEqual(harness.nearest_rank(values, 95), 19)
        self.assertEqual(harness.nearest_rank([3, 1], 50), 1)
        self.assertEqual(harness.nearest_rank([3], 99), 3)
        self.assertIsNone(harness.nearest_rank([], 95))
        with self.assertRaises(ValueError):
            harness.nearest_rank([1], 0)

    def test_aggregation_does_not_turn_missing_into_zero(self):
        summary = harness.metric_summary([None, 10, 30, float("nan")])
        self.assertEqual(summary["valid_count"], 2)
        self.assertEqual(summary["missing_count"], 2)
        self.assertEqual(summary["mean"], 20)
        self.assertIsNone(harness.metric_summary([None])["p99"])

    def test_failure_attempts_remain_in_denominators(self):
        attempts = [harness.AttemptResult("1", outcome="success", admitted=True,
                                         handshake_completed=True, transport_handshake_ms=10),
                    harness.AttemptResult("2", outcome="auth_rejected"),
                    harness.AttemptResult("3", outcome="unexpected_disconnect", admitted=True,
                                         unexpected_disconnect=True)]
        summary = harness.aggregate(attempts, 2, "wav", 1)
        self.assertEqual(sum(summary["outcome_counts"].values()), 3)
        self.assertEqual(summary["successful_session_rate_attempted"], 1 / 3)
        self.assertEqual(summary["successful_session_rate_admitted"], 1 / 2)
        self.assertEqual(summary["unexpected_disconnect_rate_admitted"], 1 / 2)
        self.assertEqual(summary["latencies"]["transport_handshake_ms"]["missing_count"], 2)
        self.assertIsNone(harness.aggregate([], 0, "wav", 0)["successful_session_rate_admitted"])

    def test_silent_aggregation_omits_caption_latency(self):
        metrics = harness.aggregate([], 0, "silent", 0)["latencies"]
        self.assertNotIn("time_to_first_partial_ms", metrics)
        self.assertNotIn("time_to_first_final_ms", metrics)
        self.assertNotIn("finalized_caption_lag_ms", metrics)

    def test_timestamp_mapping_uses_actual_frame_timeline(self):
        attempt = harness.AttemptResult("1", frames=[
            harness.FrameTiming(0, 0, 1600, 1000, 1020, sent=True),
            harness.FrameTiming(1, 1600, 3200, 1100, 1140, sent=True)])
        segment = harness.SegmentResult("1", "seg-1", 0, .15, 1500)
        harness.map_audio_end(segment, attempt, harness.AudioFixture("wav", 4000))
        self.assertEqual(segment.lag_status, "valid")
        self.assertAlmostEqual(segment.mapped_audio_end_offset_ms, 1190)
        self.assertAlmostEqual(segment.finalized_caption_lag_ms, 310)
        boundary = harness.SegmentResult("1", "seg-1", 0, .1, 1500)
        harness.map_audio_end(boundary, attempt, harness.AudioFixture("wav", 4000))
        self.assertEqual(boundary.mapped_audio_end_offset_ms, 1120)

    def test_invalid_and_missing_timestamps_are_not_zero_lag(self):
        for end, status in ((None, "unavailable"), (0, "invalid"), (-1, "invalid"),
                            (.3, "invalid")):
            with self.subTest(end=end):
                segment = harness.SegmentResult("1", "seg-1", 0, end, 1500)
                harness.map_audio_end(segment, harness.AttemptResult("1"),
                                      harness.AudioFixture("wav", 4000))
                self.assertEqual(segment.lag_status, status)
                self.assertIsNone(segment.finalized_caption_lag_ms)
        for value in (None, "0.1", True, float("nan"), float("inf")):
            self.assertIsNone(harness.numeric_timestamp(value))

    def test_timestamp_for_not_yet_sent_audio_is_unavailable(self):
        attempt = harness.AttemptResult("1", frames=[
            harness.FrameTiming(0, 0, 1600, 1000, 1020, sent=True)])
        segment = harness.SegmentResult("1", "seg-1", 0, .1, 1000)
        harness.map_audio_end(segment, attempt, harness.AudioFixture("wav", 4000))
        self.assertEqual(segment.lag_reason, "audio_not_sent_at_receipt")

    def test_invalid_timestamp_order(self):
        segment = harness.SegmentResult("1", "seg-1", .2, .1, 1500)
        harness.map_audio_end(segment, harness.AttemptResult("1"),
                              harness.AudioFixture("wav", 4000))
        self.assertEqual(segment.lag_status, "invalid")

    def test_success_contracts_are_different(self):
        attempt = harness.AttemptResult("1", handshake_completed=True, admitted=True,
                                         full_audio_sent=True, stop_sent=True,
                                         session_end_received=True, session_end_after_stop=True)
        self.assertEqual(harness.terminal_outcome(attempt, "silent"), "success")
        self.assertEqual(harness.terminal_outcome(attempt, "wav"), "client_error")
        attempt.segments = [harness.SegmentResult(
            "1", "seg-1", 0, .1, 1000, source_text_present=True,
            target_text_present=True, valid_finalized_segment=True)]
        self.assertEqual(harness.terminal_outcome(attempt, "wav"), "success")
        attempt.segments[0].target_text_present = False
        self.assertEqual(harness.terminal_outcome(attempt, "wav"), "translation_degraded")
        attempt.full_audio_sent = False
        self.assertEqual(harness.terminal_outcome(attempt, "silent"), "client_error")

    def test_terminal_outcome_is_exclusive_with_post_admission_errors(self):
        for code, outcome in (("UNAUTHORIZED", "auth_rejected"),
                              ("TOO_MANY_SESSIONS", "limit_rejected"),
                              ("QUOTA_EXCEEDED", "quota_rejected"),
                              ("TRANSCRIBE_ERROR", "transcribe_failed"),
                              ("SESSION_TIMEOUT", "timeout"),
                              ("INTERNAL_ERROR", "client_error")):
            attempt = harness.AttemptResult("1", admitted=True, server_error_codes=[code],
                                             unexpected_disconnect=True)
            self.assertEqual(harness.terminal_outcome(attempt, "wav"), outcome)
            attempt.outcome = harness.terminal_outcome(attempt, "wav")
            self.assertEqual(sum(harness.aggregate([attempt], 1, "wav", 1)
                                 ["outcome_counts"].values()), 1)

    def test_only_nonempty_source_partials_start_caption_timer(self):
        attempt = harness.AttemptResult("1", audio_streaming_start_offset_ms=100)
        message = {"type": "partial_segment", "spoken_language": "vi", "text_vi": " "}
        self.assertFalse(harness.record_message(attempt, message, 150, "wav", ()))
        self.assertIsNone(attempt.time_to_first_partial_ms)
        message["text_vi"] = TRANSCRIPT
        harness.record_message(attempt, message, 170, "wav", ())
        self.assertEqual(attempt.time_to_first_partial_ms, 70)
        harness.record_message(attempt, message, 190, "wav", ())
        self.assertEqual(attempt.time_to_first_partial_ms, 70)


class SecurityTests(OfflineCase):
    def test_benchmark_correlation_query_is_validated_and_never_contains_token(self):
        from urllib.parse import parse_qsl, urlsplit

        config = harness.Config(URL, run_id="local.run-1", token=TOKEN)
        query = dict(parse_qsl(urlsplit(harness.connection_url(config)).query))
        self.assertEqual(query["benchmark_run_id"], "local.run-1")
        for run_id in ("bad run", "x" * 65, TOKEN):
            target = harness.connection_url(replace(config, run_id=run_id))
            self.assertNotIn("benchmark_run_id", dict(parse_qsl(urlsplit(target).query)))
            self.assertNotIn(TOKEN, target)

    def test_redaction_nested_encoded_and_jwt(self):
        value = {TOKEN: [TOKEN, "secret/a", "secret%2Fa", "eyJOTHER.body.signature"]}
        redacted = json.dumps(harness.redact(value, (TOKEN, "secret/a")))
        for secret in (TOKEN, "secret/a", "secret%2Fa", "eyJOTHER.body.signature"):
            self.assertNotIn(secret, redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_url_sanitization_and_rejecting_secret_cli_urls(self):
        value = harness.sanitized_url("wss://user:secret@host/ws?token=secret#fragment")
        self.assertEqual(value, "wss://host/ws")
        for url in (URL + "?token=" + TOKEN, "ws://user:secret@host/ws", URL + "#secret"):
            with self.assertRaises(ValueError):
                harness.connection_url(harness.Config(url))

    def test_custom_environment_and_empty_required_token(self):
        args = harness.parser().parse_args(["--url", URL, "--auth", "--token-env", "TEST_ACCESS"])
        with patch.dict("os.environ", {"TEST_ACCESS": TOKEN}):
            config, audio = harness.preflight(args)
        self.assertTrue(config.auth)
        self.assertEqual(config.token, TOKEN)
        self.assertNotIn(TOKEN, repr(config))
        self.assertEqual(audio.mode, "silent")
        with patch.dict("os.environ", {"TEST_ACCESS": " "}):
            with self.assertRaises(ValueError):
                harness.preflight(args)

    def test_legacy_defaults_and_token_auto_detection(self):
        args = harness.parser().parse_args(["--url", URL, "--concurrency", "12",
                                          "--duration", "8", "--ramp", "0.2"])
        with patch.dict("os.environ", {"LIVECAP_ACCESS_TOKEN": ""}):
            config, audio = harness.preflight(args)
        self.assertFalse(config.auth)
        self.assertEqual(config.concurrency, 12)
        self.assertEqual(audio.samples, 128000)
        with patch.dict("os.environ", {"LIVECAP_ACCESS_TOKEN": TOKEN}):
            config, _ = harness.preflight(args)
        self.assertTrue(config.auth)

    def test_cli_token_is_rejected_without_echo(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(SystemExit):
            harness.parser().parse_args(["--url", URL, "--token", TOKEN])
        self.assertNotIn(TOKEN, output.getvalue())

    def test_preflight_error_never_runs_benchmark(self):
        output = io.StringIO()
        with patch.dict("os.environ", {"LIVECAP_ACCESS_TOKEN": ""}), \
                patch.object(harness, "run_benchmark", new_callable=AsyncMock) as run, \
                contextlib.redirect_stdout(output):
            self.assertEqual(harness.main(["--url", URL, "--auth"]), 2)
        run.assert_not_called()

    def test_wav_validation_before_connections(self):
        with patch.object(harness, "run_benchmark", new_callable=AsyncMock) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(harness.main(["--url", URL, "--audio-file",
                                           str(self.root / "missing.wav")]), 2)
        run.assert_not_called()

    def test_runtime_console_never_echoes_exception_token_or_transcript(self):
        output = io.StringIO()
        with patch.dict("os.environ", {"LIVECAP_ACCESS_TOKEN": TOKEN}), \
                patch.object(harness, "run_benchmark", new_callable=Mock, return_value=None) as run, \
                patch.object(harness.asyncio, "run", side_effect=ValueError(TOKEN + TRANSCRIPT)) as runner, \
                contextlib.redirect_stdout(output):
            self.assertEqual(harness.main(["--url", URL, "--auth"]), 2)
        run.assert_called_once()
        runner.assert_called_once()
        self.assertNotIn(TOKEN, output.getvalue())
        self.assertNotIn(TRANSCRIPT, output.getvalue())

    def test_output_paths_cannot_collide_or_overwrite_fixture(self):
        path = make_wav(self.root / "speech.wav")
        for options in (["--audio-file", str(path), "--output-json", str(path)],
                        ["--output-json", str(self.root / "results-attempts.csv"),
                         "--output-csv", str(self.root / "results.csv")]):
            args = harness.parser().parse_args(["--url", URL, *options])
            with self.assertRaises(ValueError):
                harness.preflight(args)

    def test_invalid_numeric_options(self):
        for option, value in (("--duration", "nan"), ("--ramp", "-1"),
                              ("--concurrency", "0"), ("--shutdown-timeout", "0")):
            with self.subTest(option=option):
                args = harness.parser().parse_args(["--url", URL, option, value])
                with self.assertRaises(ValueError):
                    harness.preflight(args)

    def test_atomic_output_uses_replace_and_cleans_failed_tempfile(self):
        path = self.root / "output.json"
        path.write_text("previous", encoding="utf-8")
        with patch.object(harness.os, "replace", side_effect=OSError("test failure")):
            with self.assertRaises(OSError):
                harness.atomic_write(path, "new")
        self.assertEqual(path.read_text(), "previous")
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        harness.atomic_write(path, "new")
        self.assertEqual(path.read_text(), "new")


class SessionTests(unittest.IsolatedAsyncioTestCase, OfflineCase):
    async def asyncSetUp(self):
        self.clock = FakeClock()
        self.config = harness.Config(URL, concurrency=1, ramp=0, shutdown_timeout=.03,
                                     first_caption_timeout=.03, auth=True, token=TOKEN)
        self.fixture = harness.validate_wav(make_wav(self.root / "speech.wav"))

    async def run_socket(self, fake, audio=None, config=None):
        connector = AsyncMock(return_value=fake)
        tracker = harness.ConcurrencyTracker(self.clock, self.clock.now())
        result = await harness.one_session(config or self.config, audio or self.fixture,
                                           "attempt-1", tracker, connector, self.clock)
        return result, connector

    async def test_sender_receiver_run_together_with_auth_and_lifecycle(self):
        fake = FakeSocket(self.clock)
        attempt, connector = await self.run_socket(fake)
        self.assertEqual(attempt.outcome, "success")
        self.assertTrue(fake.partial_received_before_stop)
        self.assertTrue(attempt.expected_close)
        self.assertEqual(connector.call_args.kwargs["subprotocols"], ["livecap.v1", TOKEN])
        self.assertEqual(attempt.bytes_sent, 8000)
        self.assertEqual(attempt.audio_frames_sent, 3)
        self.assertEqual(attempt.audio_seconds_sent, .25)
        self.assertEqual(attempt.partial_segments_received, 1)
        self.assertEqual(attempt.finalized_segments_received, 1)
        self.assertEqual(attempt.unique_finalized_segments, 1)
        self.assertEqual(attempt.control_messages_received, 2)
        self.assertEqual(attempt.total_messages_received, 4)
        for name in ("handshake_complete_offset_ms", "session_start_received_offset_ms",
                     "audio_streaming_start_offset_ms", "audio_streaming_end_offset_ms",
                     "stop_sent_offset_ms", "session_end_received_offset_ms",
                     "socket_closed_offset_ms"):
            self.assertIsNotNone(getattr(attempt, name))
        self.assertNotIn(TOKEN, json.dumps(asdict(attempt)))
        self.assertNotIn(TRANSCRIPT, json.dumps(asdict(attempt)))

    async def test_pacing_uses_absolute_sample_schedule(self):
        origin = self.clock.now()
        await harness.pace(self.clock, harness.scheduled_send_time(origin, 1600))
        self.clock.value += .04  # Inject send/scheduling work; don't accumulate it.
        actual = await harness.pace(self.clock, harness.scheduled_send_time(origin, 3200))
        self.assertAlmostEqual(actual, origin + .2)
        self.assertAlmostEqual(self.clock.sleeps[-1], .06)
        self.clock.value += .3
        late = await harness.pace(self.clock, harness.scheduled_send_time(origin, 4800))
        self.assertAlmostEqual(late - (origin + .3), .2)
        self.assertEqual(self.clock.sleeps[-1], 0)

    async def test_handshake_metric_excludes_tls_context_setup(self):
        fake = FakeSocket(self.clock, captions=False)

        def tls_context():
            self.clock.value += .25  # Client pre-connect setup, not transport latency.
            return object()

        async def connect(*args, **kwargs):
            self.clock.value += .02
            return fake

        tracker = harness.ConcurrencyTracker(self.clock, self.clock.now())
        with patch.object(harness.ssl, "create_default_context", tls_context):
            attempt = await harness.one_session(
                replace(self.config, url="wss://localhost/ws/transcribe"),
                harness.AudioFixture("silent", 4000), "attempt-1", tracker, connect, self.clock)
        self.assertAlmostEqual(attempt.transport_handshake_ms, 20)
        self.assertAlmostEqual(attempt.connect_to_session_start_ms, 270)

    async def test_admission_metric_is_separate_from_handshake(self):
        fake = FakeSocket(self.clock, captions=False)
        original_recv = fake.recv
        first = True

        async def recv():
            nonlocal first
            if first:
                self.clock.value += .03
                first = False
            return await original_recv()

        fake.recv = recv

        async def connect(*args, **kwargs):
            self.clock.value += .02
            return fake

        tracker = harness.ConcurrencyTracker(self.clock, self.clock.now())
        attempt = await harness.one_session(self.config, harness.AudioFixture("silent", 4000),
                                             "attempt-1", tracker, connect, self.clock)
        self.assertAlmostEqual(attempt.transport_handshake_ms, 20)
        self.assertAlmostEqual(attempt.session_admission_ms, 30)
        self.assertAlmostEqual(attempt.connect_to_session_start_ms, 50)

    async def test_silent_success_has_no_caption_latency(self):
        attempt, _ = await self.run_socket(FakeSocket(self.clock, captions=False),
                                           harness.AudioFixture("silent", 4000))
        self.assertEqual(attempt.outcome, "success")
        self.assertIsNone(attempt.time_to_first_partial_ms)
        self.assertIsNone(attempt.time_to_first_final_ms)

    async def test_rejections_have_no_audio_or_double_outcome(self):
        for code, outcome in (("UNAUTHORIZED", "auth_rejected"),
                              ("TOO_MANY_SESSIONS", "limit_rejected"),
                              ("QUOTA_EXCEEDED", "quota_rejected")):
            attempt, _ = await self.run_socket(FakeSocket(self.clock, rejection=code))
            self.assertEqual(attempt.outcome, outcome)
            self.assertTrue(attempt.handshake_completed)
            self.assertFalse(attempt.admitted)
            self.assertEqual(attempt.bytes_sent, 0)

    async def test_post_admission_error_is_detected_while_sending(self):
        attempt, _ = await self.run_socket(FakeSocket(self.clock, error="TRANSCRIBE_ERROR"))
        self.assertTrue(attempt.admitted)
        self.assertEqual(attempt.outcome, "transcribe_failed")
        self.assertFalse(attempt.full_audio_sent)
        self.assertNotIn(TOKEN, json.dumps(asdict(attempt)))

    async def test_explicit_and_implicit_translation_degradation(self):
        for error in (None, "TRANSLATE_ERROR"):
            attempt, _ = await self.run_socket(FakeSocket(self.clock, error=error, target=False))
            self.assertEqual(attempt.outcome, "translation_degraded")

    async def test_unexpected_remote_disconnect(self):
        attempt, _ = await self.run_socket(FakeSocket(self.clock, disconnect=True))
        self.assertEqual(attempt.outcome, "unexpected_disconnect")
        self.assertTrue(attempt.unexpected_disconnect)
        self.assertFalse(attempt.expected_close)
        self.assertEqual(attempt.close_code, 1006)
        self.assertNotIn(TOKEN, attempt.close_reason)
        self.assertNotIn(TRANSCRIPT, attempt.close_reason)

    async def test_shutdown_timeout_cannot_be_silent_success(self):
        attempt, _ = await self.run_socket(FakeSocket(self.clock, captions=False, end=False),
                                           harness.AudioFixture("silent", 4000))
        self.assertEqual(attempt.outcome, "timeout")
        self.assertTrue(attempt.stop_sent)
        self.assertFalse(attempt.session_end_received)
        self.assertFalse(attempt.unexpected_disconnect)  # Local timeout != observed remote close.

    async def test_first_caption_deadline_cancels_sender(self):
        attempt, _ = await self.run_socket(FakeSocket(self.clock, captions=False, block_send=True))
        self.assertEqual(attempt.outcome, "timeout")
        self.assertFalse(attempt.full_audio_sent)

    async def test_blocked_send_is_bounded_even_after_first_caption(self):
        fake = FakeSocket(self.clock)
        original = fake.send

        async def send(value):
            if fake.frames_sent > 0 and isinstance(value, bytes):
                await asyncio.Event().wait()
            await original(value)

        fake.send = send
        attempt, _ = await self.run_socket(fake, config=replace(self.config, send_timeout=.005))
        self.assertEqual(attempt.outcome, "timeout")
        self.assertEqual(attempt.partial_segments_received, 1)

    async def test_handshake_timeout_releases_barrier(self):
        calls = 0

        async def connect(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                await asyncio.Event().wait()
            return FakeSocket(self.clock)

        with patch.object(harness, "git_state", return_value=(None, None)):
            report = await harness.run_benchmark(
                replace(self.config, concurrency=2, connect_timeout=.01),
                self.fixture, connect, self.clock)
        self.assertEqual(report["summary"]["outcome_counts"]["timeout"], 1)
        self.assertEqual(report["summary"]["outcome_counts"]["success"], 1)

    async def test_early_session_end_cannot_succeed(self):
        fake = FakeSocket(self.clock)
        fake.messages.put_nowait(json.dumps({"type": "session_end"}))
        attempt, _ = await self.run_socket(fake)
        self.assertEqual(attempt.outcome, "client_error")
        self.assertFalse(attempt.session_end_after_stop)

    async def test_abnormal_close_after_end_is_still_unexpected(self):
        fake = FakeSocket(self.clock, remote_close_code=1006)
        attempt, _ = await self.run_socket(fake)
        self.assertTrue(attempt.session_end_received)
        self.assertTrue(attempt.unexpected_disconnect)
        self.assertEqual(attempt.outcome, "unexpected_disconnect")

    async def test_modern_disconnect_does_not_read_deprecated_exception_properties(self):
        class ConnectionClosedError(Exception):
            rcvd = None  # Abrupt disconnect: no close frame received.

            @property
            def code(self):
                raise DeprecationWarning("Use rcvd instead")

            @property
            def reason(self):
                raise DeprecationWarning("Use rcvd instead")

        fake = FakeSocket(self.clock)
        original_send = fake.send

        async def send(value):
            await original_send(value)
            if isinstance(value, bytes):
                fake.messages.put_nowait(ConnectionClosedError())

        fake.send = send
        attempt, _ = await self.run_socket(fake)
        self.assertEqual(attempt.outcome, "unexpected_disconnect")
        self.assertTrue(attempt.unexpected_disconnect)
        self.assertEqual(attempt.close_code, 1006)
        self.assertIsNone(attempt.diagnostic)

    async def test_abnormal_close_verdict_during_cleanup_cannot_be_success(self):
        # Keep receive suspended after session_end, as a real close handshake
        # can be while the drain waiter wakes cleanup.
        fake = FakeSocket(self.clock, remote_close_code=None)

        async def close():
            fake.close_code = 1011
            fake.close_reason = TOKEN + TRANSCRIPT

        fake.close = close
        attempt, _ = await self.run_socket(fake)
        self.assertTrue(attempt.session_end_received)
        self.assertTrue(attempt.unexpected_disconnect)
        self.assertEqual(attempt.outcome, "unexpected_disconnect")
        self.assertEqual(attempt.close_code, 1011)
        self.assertEqual(attempt.close_reason, "[OMITTED]")

    async def test_replay_detects_changed_pcm_not_just_truncation(self):
        raw = bytearray(self.fixture.path.read_bytes())
        raw[-1] = 1
        self.fixture.path.write_bytes(raw)
        attempt, _ = await self.run_socket(FakeSocket(self.clock))
        self.assertEqual(attempt.outcome, "client_error")
        self.assertFalse(attempt.full_audio_sent)

    async def test_missing_caption_cannot_succeed_wav(self):
        attempt, _ = await self.run_socket(FakeSocket(self.clock, captions=False))
        self.assertEqual(attempt.outcome, "client_error")

    async def test_exception_and_invalid_json_do_not_export_secret(self):
        for kwargs in ({"send_failure": True}, {"malformed": True}):
            attempt, _ = await self.run_socket(FakeSocket(self.clock, **kwargs))
            self.assertEqual(attempt.outcome, "client_error")
            self.assertNotIn(TOKEN, json.dumps(asdict(attempt)))
            self.assertNotIn(TRANSCRIPT, json.dumps(asdict(attempt)))

    async def test_auth_required_empty_token_fails_before_connector(self):
        connector = AsyncMock()
        with self.assertRaises(ValueError):
            await harness.run_benchmark(replace(self.config, token=""), self.fixture, connector)
        connector.assert_not_called()

    async def test_generated_run_id_matches_query_for_every_attempt(self):
        from urllib.parse import parse_qsl, urlsplit

        urls = []
        async def connect(url, **kwargs):
            urls.append(url)
            return FakeSocket(self.clock)

        with patch.object(harness, "git_state", return_value=(None, None)):
            report = await harness.run_benchmark(replace(self.config, concurrency=2, warmup_sessions=1),
                                                 self.fixture, connect, self.clock)
        self.assertEqual(len(urls), 3)
        self.assertEqual({dict(parse_qsl(urlsplit(url).query))["benchmark_run_id"] for url in urls},
                         {report["metadata"]["run_id"]})
        self.assertNotIn(TOKEN, "".join(urls))

    async def test_auth_does_not_stream_if_subprotocol_is_not_selected(self):
        fake = FakeSocket(self.clock)
        fake.subprotocol = None
        attempt, _ = await self.run_socket(fake)
        self.assertEqual(attempt.outcome, "admission_error")
        self.assertEqual(attempt.diagnostic, "auth_subprotocol_not_negotiated")
        self.assertFalse(attempt.admitted)
        self.assertEqual(fake.frames_sent, 0)

    async def test_transport_logger_cannot_echo_auth_headers(self):
        with patch.object(harness.TRANSPORT_LOGGER, "_log") as log:
            harness.TRANSPORT_LOGGER.debug("Authorization %s", TOKEN)
            harness.TRANSPORT_LOGGER.error("Header %s", TOKEN)
        log.assert_not_called()
        _, connector = await self.run_socket(FakeSocket(self.clock))
        self.assertIs(connector.call_args.kwargs["logger"], harness.TRANSPORT_LOGGER)

    async def test_handshake_http_rejection_is_admission_error(self):
        class InvalidStatus(Exception):
            pass

        connector = AsyncMock(side_effect=InvalidStatus(TOKEN + TRANSCRIPT))
        tracker = harness.ConcurrencyTracker(self.clock, self.clock.now())
        attempt = await harness.one_session(self.config, self.fixture, "attempt-1",
                                             tracker, connector, self.clock)
        self.assertEqual(attempt.outcome, "admission_error")
        self.assertNotIn(TOKEN, json.dumps(asdict(attempt)))

    async def test_connection_refused_does_not_invent_an_open_socket_or_remote_disconnect(self):
        connector = AsyncMock(side_effect=ConnectionRefusedError(TOKEN + TRANSCRIPT))
        tracker = harness.ConcurrencyTracker(self.clock, self.clock.now())
        attempt = await harness.one_session(self.config, self.fixture, "attempt-1",
                                             tracker, connector, self.clock)
        self.assertEqual(attempt.outcome, "admission_error")
        self.assertFalse(attempt.handshake_completed)
        self.assertFalse(attempt.unexpected_disconnect)
        self.assertIsNone(attempt.socket_closed_offset_ms)
        self.assertIsNone(attempt.close_initiator)
        self.assertIsNone(attempt.close_code)
        self.assertNotIn(TOKEN, json.dumps(asdict(attempt)))

    async def test_barrier_releases_after_rejection_and_successes(self):
        sockets = []
        connected = []

        async def connect(*args, **kwargs):
            index = len(connected)
            connected.append(index)
            fake = FakeSocket(self.clock, rejection="TOO_MANY_SESSIONS" if index == 1 else None)
            original_send = fake.send

            async def send(value):
                self.assertEqual(len(connected), 3)
                await original_send(value)

            fake.send = send
            sockets.append(fake)
            return fake

        with patch.object(harness, "git_state", return_value=("test-only-sha", True)):
            report = await harness.run_benchmark(replace(self.config, concurrency=3, ramp=.01),
                                                 self.fixture, connect, self.clock)
        self.assertEqual(report["summary"]["attempts"], 3)
        self.assertEqual(report["summary"]["admitted"], 2)
        self.assertEqual(report["summary"]["peak_observed_concurrency"], 2)
        self.assertEqual(report["summary"]["outcome_counts"]["limit_rejected"], 1)
        self.assertEqual(report["summary"]["outcome_counts"]["success"], 2)
        self.assertEqual(report["observed_active_sessions"][-1]["observed_active_sessions"], 0)

    async def test_connect_failure_does_not_crash_other_sessions_or_barrier(self):
        calls = 0

        async def connect(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError(TOKEN)
            return FakeSocket(self.clock)

        with patch.object(harness, "git_state", return_value=(None, None)):
            report = await harness.run_benchmark(replace(self.config, concurrency=2),
                                                 self.fixture, connect, self.clock)
        self.assertEqual(report["summary"]["outcome_counts"]["client_error"], 1)
        self.assertEqual(report["summary"]["outcome_counts"]["success"], 1)

    async def test_warmup_raw_results_separate_and_json_csv_no_secrets(self):
        async def connect(*args, **kwargs):
            return FakeSocket(self.clock)

        with patch.object(harness, "git_state", return_value=("test-only-sha", True)):
            report = await harness.run_benchmark(
                replace(self.config, warmup_sessions=1, run_id=TOKEN, scenario=TOKEN),
                self.fixture, connect, self.clock)
        self.assertEqual(report["summary"]["attempts"], 1)
        self.assertEqual(len(report["warmup_attempts"]), 1)
        self.assertEqual(report["overall_summary"]["attempts"], 2)
        self.assertEqual(report["warmup_summary"]["attempts"], 1)
        paths = harness.write_outputs(report, self.root / "results.json",
                                      self.root / "results.csv", (TOKEN,))
        self.assertEqual([p.name for p in paths],
                         ["results.json", "results-attempts.csv", "results-segments.csv"])
        for path in paths:
            self.assertNotIn(TOKEN, path.read_text(encoding="utf-8"))
            self.assertNotIn(TRANSCRIPT, path.read_text(encoding="utf-8"))
        self.assertTrue(json.loads(paths[0].read_text())["metadata"]["git_dirty"])
        with paths[1].open(newline="", encoding="utf-8") as source:
            self.assertEqual(len(list(csv.DictReader(source))), 2)
        with paths[2].open(newline="", encoding="utf-8") as source:
            self.assertEqual(len(list(csv.DictReader(source))), 2)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            harness.print_summary(report, (TOKEN,))
        self.assertNotIn(TOKEN, output.getvalue())
        self.assertNotIn(TRANSCRIPT, output.getvalue())

    async def test_failed_warmup_remains_in_overall_counts(self):
        calls = 0

        async def connect(*args, **kwargs):
            nonlocal calls
            calls += 1
            return FakeSocket(self.clock, rejection="UNAUTHORIZED" if calls == 1 else None)

        with patch.object(harness, "git_state", return_value=(None, None)):
            report = await harness.run_benchmark(replace(self.config, warmup_sessions=1),
                                                 self.fixture, connect, self.clock)
        self.assertEqual(report["summary"]["outcome_counts"]["success"], 1)
        self.assertEqual(report["warmup_summary"]["outcome_counts"]["auth_rejected"], 1)
        self.assertEqual(report["overall_summary"]["outcome_counts"]["auth_rejected"], 1)
        self.assertEqual(report["overall_summary"]["successful_session_rate_attempted"], .5)


if __name__ == "__main__":
    unittest.main()
