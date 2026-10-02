"""Opt-in loopback/mock validation; generated timing/audio is NOT performance evidence.

LIVECAP_RUN_LOCAL_VALIDATION=1 enables real sockets bound to 127.0.0.1 only.
This never imports the application, Cognito, an AWS SDK, or calls a wake endpoint.
"""
from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import io
import json
import logging
import math
import os
import socket
import tempfile
import time
import unittest
import uuid
import wave
from collections import Counter
from dataclasses import replace
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

from tools import ws_load_test as harness

TOKEN_ENV = "LIVECAP_VALIDATION_ONLY_TOKEN"
TOKEN = "eyJLOCAL.validation.fake_signature"
TEXT = "MOCK_TRANSCRIPT_NEVER_EXPORT"
LOGGER = logging.Logger("livecap.validation.mock")
LOGGER.disabled = True
LOGGER.propagate = False


@unittest.skipUnless(os.getenv("LIVECAP_RUN_LOCAL_VALIDATION") == "1",
                     "Opt in to localhost/mock sockets with LIVECAP_RUN_LOCAL_VALIDATION=1")
class LoopbackValidation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import websockets
        from websockets.asyncio.server import serve

        self.websockets = websockets
        self.serve = serve
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.wav_path = self.root / "generated-validation-only.wav"
        # 250 ms, 8000 PCM bytes. No ASR or real speech is involved.
        with wave.open(str(self.wav_path), "wb") as wav:
            wav.setparams((1, 2, 16000, 4000, "NONE", "not compressed"))
            wav.writeframes(bytes(8000))
        self.audio = harness.validate_wav(self.wav_path)
        self.trace = []
        self.server_errors = []
        self.taps = []
        self.connections = 0

        def guarded(original):
            def call(sock, address):
                if not isinstance(address, tuple) or address[0] != "127.0.0.1":
                    raise AssertionError("Local validation forbids non-loopback connections")
                return original(sock, address)
            return call

        for name in ("connect", "connect_ex"):
            guard = patch.object(socket.socket, name, guarded(getattr(socket.socket, name)))
            guard.start()
            self.addCleanup(guard.stop)

    async def asyncTearDown(self):
        self.assertEqual(self.server_errors, [], "Mock server itself must not fail")

    async def handler(self, ws):
        index = self.connections
        self.connections += 1
        scenario = self.scenarios[index % len(self.scenarios)]
        trace = {"scenario": scenario, "pcm": bytearray(), "frames": [],
                 "sent": [], "stop": None, "admission": None,
                 "session_id": None,
                 "protocols": ws.request.headers.get("Sec-WebSocket-Protocol", "")}
        self.trace.append(trace)

        async def emit(message):
            trace["sent"].append((time.monotonic(), message))
            await ws.send(json.dumps(message))

        try:
            if scenario in {"auth_rejected", "limit_rejected", "quota_rejected"}:
                code = {"auth_rejected": "UNAUTHORIZED", "limit_rejected": "TOO_MANY_SESSIONS",
                        "quota_rejected": "QUOTA_EXCEEDED"}[scenario]
                await emit({"type": "error", "code": code, "message": TOKEN + TEXT})
                await ws.close(code=1008, reason=TOKEN + TEXT)
                return
            if scenario == "admission_timeout":
                await ws.wait_closed()
                return
            await asyncio.sleep(.04)  # Independently controlled admission delay.
            trace["admission"] = time.monotonic()
            trace["session_id"] = str(uuid.uuid4())
            await emit({"type": "session_start", "session_id": trace["session_id"]})
            if scenario == "early_end":
                await emit({"type": "session_end"})
                await ws.close()
                return

            final = {"type": "finalized_segment", "segment_id": "vi-seg-1",
                     "spoken_language": "vi", "text_vi": TEXT, "text_en": TEXT,
                     "timestamp_start": 0.0, "timestamp_end": .1, "is_final": True}
            async for raw in ws:
                if isinstance(raw, bytes):
                    trace["frames"].append((time.monotonic(), len(raw)))
                    trace["pcm"].extend(raw)
                    if len(trace["frames"]) == 1:
                        if scenario == "transcribe_failed":
                            await emit({"type": "error", "code": "TRANSCRIBE_ERROR",
                                        "message": TOKEN + TEXT})
                            await ws.close(code=1011, reason=TOKEN + TEXT)
                            return
                        if scenario == "unexpected_disconnect":
                            ws.transport.abort()
                            return
                        if scenario == "malformed":
                            await ws.send("INVALID_JSON " + TOKEN + TEXT)
                            await ws.wait_closed()
                            return
                        if scenario != "silent" and scenario != "caption_timeout":
                            await emit({"type": "pong"})
                            await emit({"type": "partial_segment", "spoken_language": "vi",
                                        "text_vi": "", "text_en": TEXT})
                            await asyncio.sleep(.04)
                            await emit({"type": "partial_segment", "spoken_language": "vi",
                                        "text_vi": TEXT, "text_en": ""})
                    if len(trace["frames"]) == 2 and scenario == "timing":
                        await asyncio.sleep(.03)
                        await emit(final)
                else:
                    if json.loads(raw).get("type") != "stop":
                        raise AssertionError("Only PCM and stop are expected")
                    trace["stop"] = time.monotonic()
                    if scenario in {"shutdown_timeout", "caption_timeout"}:
                        await ws.wait_closed()
                        return
                    if scenario not in {"silent", "no_final"}:
                        if scenario == "translation_degraded":
                            await emit({"type": "error", "code": "TRANSLATE_ERROR",
                                        "message": TOKEN + TEXT})
                            final["text_en"] = ""
                        await emit(final)
                        if scenario == "timing":
                            await emit({**final, "segment_id": "vi-seg-2", "timestamp_end": None})
                            await emit({**final, "segment_id": "vi-seg-3", "timestamp_end": 0})
                    await emit({"type": "session_end"})
                    if scenario == "abnormal_after_end":
                        await ws.close(code=1011, reason=TOKEN + TEXT)
                    else:
                        await ws.close()
                    return
        except self.websockets.exceptions.ConnectionClosed:
            # Expected in timeout/client-error scenarios when harness cleans up.
            pass
        except Exception as exc:
            self.server_errors.append(type(exc).__name__)

    @contextlib.asynccontextmanager
    async def server(self, scenarios, *, auth=True, delayed_handshake=False):
        self.scenarios = scenarios

        async def process_request(connection, request):
            if scenarios == ["http_rejection"]:
                return connection.respond(HTTPStatus.SERVICE_UNAVAILABLE, TOKEN + TEXT)
            if delayed_handshake:
                await asyncio.sleep(.06)

        async with self.serve(self.handler, "127.0.0.1", 0,
                             subprotocols=["livecap.v1"] if auth else None,
                             process_request=process_request, logger=LOGGER) as server:
            port = server.sockets[0].getsockname()[1]
            yield harness.Config(f"ws://127.0.0.1:{port}/ws/transcribe", concurrency=1,
                                 ramp=0, auth=auth, token=TOKEN if auth else "",
                                 connect_timeout=1, first_caption_timeout=1,
                                 shutdown_timeout=.15, send_timeout=1,
                                 run_id=self._testMethodName, scenario="mock-validation-not-performance")

    async def tapped_connector(self, url, **kwargs):
        # Independent transport/receive observations, not harness timestamps.
        connect_start = time.monotonic()
        ws = await self.websockets.connect(url, proxy=None, **kwargs)
        tap = {"connect_start": connect_start, "handshake": time.monotonic(), "received": []}
        self.taps.append(tap)

        class Tap:
            def __getattr__(self, name):
                return getattr(ws, name)

            async def recv(self):
                raw = await ws.recv()
                tap["received"].append((time.monotonic(), json.loads(raw)))
                return raw

        return Tap()

    def verify_summary(self, report):
        """Recompute summaries independently from raw rows, without harness helpers."""
        attempts = report["attempts"]
        summary = report["summary"]
        counts = Counter(a["outcome"] for a in attempts)
        self.assertEqual(sum(summary["outcome_counts"].values()), len(attempts))
        self.assertEqual({k: v for k, v in summary["outcome_counts"].items() if v}, dict(counts))
        admitted = sum(a["admitted"] for a in attempts)
        self.assertEqual(summary["successful_session_rate_attempted"], counts["success"] / len(attempts))
        self.assertEqual(summary["successful_session_rate_admitted"],
                         counts["success"] / admitted if admitted else None)
        self.assertEqual(summary["unexpected_disconnect_rate_admitted"],
                         sum(a["unexpected_disconnect"] for a in attempts if a["admitted"]) / admitted
                         if admitted else None)
        for count, throughput in (("partial_segments_received", "partial_messages_per_second"),
                                  ("finalized_segments_received", "final_messages_per_second"),
                                  ("bytes_sent", "audio_bytes_sent_per_second")):
            self.assertEqual(summary[throughput], sum(a[count] for a in attempts) /
                             summary["throughput_window_seconds"])
        for metric, stats in summary["latencies"].items():
            if metric == "pacing_drift_ms":
                values = [f["pacing_drift_ms"] for a in attempts for f in a["frames"]]
            elif metric == "finalized_caption_lag_ms":
                values = [s[metric] for a in attempts for s in a["segments"]]
            else:
                values = [a[metric] for a in attempts]
            valid = sorted(v for v in values if v is not None and math.isfinite(v))
            self.assertEqual(stats["valid_count"], len(valid))
            self.assertEqual(stats["missing_count"], len(values) - len(valid))
            self.assertEqual(stats["min"], min(valid) if valid else None)
            self.assertEqual(stats["max"], max(valid) if valid else None)
            if valid:
                self.assertAlmostEqual(stats["mean"], sum(valid) / len(valid))
                for p in (50, 95, 99):
                    self.assertEqual(stats[f"p{p}"], valid[math.ceil(len(valid) * p / 100) - 1])

    def verify_exports(self, report, label=None):
        target = os.getenv("LIVECAP_LOCAL_VALIDATION_OUTPUT_DIR")
        output = ((Path(target) / self._testMethodName) if target else self.root / "exports") / \
            (label or report["metadata"]["audio_mode"])
        paths = harness.write_outputs(report, output / "results.json", output / "results.csv", (TOKEN,))
        for path in paths:
            contents = path.read_text(encoding="utf-8")
            self.assertNotIn(TOKEN, contents)
            self.assertNotIn(TEXT, contents)
        reloaded = json.loads(paths[0].read_text(encoding="utf-8"))
        self.assertEqual(reloaded, report)
        with paths[1].open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(len(rows), len(report["attempts"]) + len(report["warmup_attempts"]))
        self.assertEqual([r["outcome"] for r in rows],
                         [a["outcome"] for a in report["warmup_attempts"] + report["attempts"]])
        with paths[2].open(encoding="utf-8", newline="") as source:
            segments = list(csv.DictReader(source))
        self.assertEqual(len(segments), sum(len(a["segments"]) for a in
                                           report["warmup_attempts"] + report["attempts"]))
        self.assertTrue(report["metadata"]["target_url"].startswith("ws://127.0.0.1:"))
        return output

    async def test_controlled_timing_pcm_pacing_lag_and_exports(self):
        async with self.server(["timing"], delayed_handshake=True) as config:
            report = await harness.run_benchmark(config, self.audio, self.tapped_connector)
        a = report["attempts"][0]
        trace, tap = self.trace[0], self.taps[0]
        self.assertEqual(a["outcome"], "success")
        self.assertEqual([size for _, size in trace["frames"]], [3200, 3200, 1600])
        self.assertEqual(a["bytes_sent"], len(trace["pcm"]))
        self.assertEqual(hashlib.sha256(trace["pcm"]).hexdigest(), hashlib.sha256(bytes(8000)).hexdigest())
        self.assertEqual(a["audio_seconds_sent"], .25)
        self.assertEqual(a["total_messages_received"], len(tap["received"]))
        self.assertEqual(a["partial_segments_received"], 2)
        self.assertEqual(a["finalized_segments_received"], 4)
        self.assertEqual(a["unique_finalized_segments"], 3)
        self.assertEqual(a["control_messages_received"], 3)
        self.assertAlmostEqual(a["transport_handshake_ms"],
                               (tap["handshake"] - tap["connect_start"]) * 1000, delta=2)
        admission = next(t for t, m in tap["received"] if m["type"] == "session_start")
        self.assertAlmostEqual(a["session_admission_ms"], (admission - tap["handshake"]) * 1000, delta=2)
        self.assertGreaterEqual(a["transport_handshake_ms"], 55)
        self.assertGreaterEqual(a["session_admission_ms"], 35)
        audio_origin = tap["connect_start"] - a["transport_connect_started_offset_ms"] / 1000 + \
            a["audio_streaming_start_offset_ms"] / 1000
        partial = next(t for t, m in tap["received"]
                       if m["type"] == "partial_segment" and m.get("text_vi"))
        final = next(t for t, m in tap["received"] if m["type"] == "finalized_segment")
        self.assertAlmostEqual(a["time_to_first_partial_ms"], (partial - audio_origin) * 1000, delta=2)
        self.assertAlmostEqual(a["time_to_first_final_ms"], (final - audio_origin) * 1000, delta=2)
        self.assertLess(final, trace["stop"], "Final must be received while audio still streams")
        self.assertLess(partial, trace["stop"])
        frames = a["frames"]
        self.assertEqual([round(f["scheduled_send_offset_ms"] - frames[0]["scheduled_send_offset_ms"])
                          for f in frames], [0, 100, 200])
        for observed, expected in zip(trace["frames"], (0, .1, .2)):
            self.assertAlmostEqual(observed[0] - trace["frames"][0][0], expected, delta=.06)
        self.assertGreaterEqual(trace["stop"] - trace["frames"][0][0], .24)
        self.assertEqual([s["lag_status"] for s in a["segments"]],
                         ["valid", "valid", "unavailable", "invalid"])
        mapped = frames[0]["actual_send_offset_ms"] + 100
        self.assertAlmostEqual(a["segments"][0]["mapped_audio_end_offset_ms"], mapped)
        self.assertAlmostEqual(a["segments"][0]["finalized_caption_lag_ms"],
                               a["segments"][0]["received_offset_ms"] - mapped)
        self.assertEqual(report["summary"]["final_segments_with_valid_lag"], 2)
        self.assertEqual(report["summary"]["final_segments_without_valid_lag"], 2)
        self.assertEqual(trace["protocols"].split(", "), ["livecap.v1", TOKEN])
        self.verify_summary(report)
        self.verify_exports(report)

    async def test_mixed_outcomes_barrier_denominators_and_disconnects(self):
        scenarios = ["timing", "auth_rejected", "limit_rejected", "quota_rejected",
                     "transcribe_failed", "translation_degraded", "unexpected_disconnect"]
        async with self.server(scenarios) as config:
            report = await harness.run_benchmark(replace(config, concurrency=7, ramp=.015), self.audio)
        attempts = report["attempts"]
        self.verify_exports(report)
        self.assertCountEqual([a["outcome"] for a in attempts], ["success", *scenarios[1:]])
        self.assertEqual(report["summary"]["admitted"], 4)
        self.assertEqual(report["summary"]["peak_observed_concurrency"], 4)
        self.assertEqual(report["observed_active_sessions"][-1]["observed_active_sessions"], 0)
        for attempt in attempts:
            trace = next(t for t in self.trace if
                         (t["session_id"] == attempt["session_id"] if attempt["admitted"] else
                          t["scenario"] == attempt["outcome"]))
            self.assertEqual(attempt["bytes_sent"], len(trace["pcm"]))
            if attempt["admitted"]:
                self.assertGreaterEqual(trace["frames"][0][0], max(t["admission"] for t in self.trace
                                                                   if t["admission"] is not None))
            else:
                self.assertEqual(trace["frames"], [])
        self.verify_summary(report)
        self.verify_exports(report)

    async def test_timeout_and_invalid_completion_matrix(self):
        scenarios = ["admission_timeout", "shutdown_timeout", "caption_timeout", "no_final", "early_end"]
        async with self.server(scenarios) as config:
            report = await harness.run_benchmark(replace(config, concurrency=5, connect_timeout=.2,
                                                         first_caption_timeout=.12), self.audio)
        self.verify_exports(report)
        self.assertCountEqual([a["outcome"] for a in report["attempts"]],
                              ["timeout", "timeout", "timeout", "client_error", "client_error"])
        self.assertEqual(report["summary"]["outcome_counts"]["success"], 0)
        by_id = {a["session_id"]: a for a in report["attempts"] if a["admitted"]}
        by_scenario = {t["scenario"]: by_id[t["session_id"]] for t in self.trace if t["session_id"]}
        caption = by_scenario["caption_timeout"]
        self.assertFalse(caption["full_audio_sent"])
        self.assertFalse(caption["stop_sent"])
        shutdown = by_scenario["shutdown_timeout"]
        self.assertTrue(shutdown["full_audio_sent"])
        self.assertTrue(shutdown["stop_sent"])
        self.assertFalse(shutdown["session_end_received"])
        self.verify_summary(report)
        self.verify_exports(report)

    async def test_abnormal_close_after_end_is_not_success(self):
        async with self.server(["abnormal_after_end"]) as config:
            report = await harness.run_benchmark(config, self.audio)
        attempt = report["attempts"][0]
        self.verify_exports(report)
        self.assertTrue(attempt["session_end_received"])
        self.assertTrue(attempt["unexpected_disconnect"])
        self.assertEqual(attempt["outcome"], "unexpected_disconnect")
        self.verify_summary(report)
        self.verify_exports(report)

    async def test_warmup_failures_are_visible(self):
        async with self.server(["quota_rejected", "timing"]) as config:
            report = await harness.run_benchmark(replace(config, warmup_sessions=1), self.audio)
        self.assertEqual(report["summary"]["outcome_counts"]["success"], 1)
        self.assertEqual(report["overall_summary"]["attempts"], 2)
        self.assertEqual(report["overall_summary"]["successful_session_rate_attempted"], .5)
        self.assertEqual(report["warmup_attempts"][0]["outcome"], "quota_rejected")
        self.verify_exports(report)

    async def test_http_handshake_rejection_and_malformed_json(self):
        for scenario, outcome in (("http_rejection", "admission_error"), ("malformed", "client_error")):
            self.connections = 0
            async with self.server([scenario]) as config:
                report = await harness.run_benchmark(config, self.audio)
            attempt = report["attempts"][0]
            self.assertEqual(attempt["outcome"], outcome)
            if scenario == "http_rejection":
                self.assertFalse(attempt["handshake_completed"])
                self.assertEqual(attempt["bytes_sent"], 0)
            else:
                self.assertTrue(attempt["admitted"])
            self.verify_summary(report)
            self.verify_exports(report, scenario)

    async def test_auth_negotiation_is_required_before_audio(self):
        async with self.server(["timing"], auth=False) as config:
            report = await harness.run_benchmark(replace(config, auth=True, token=TOKEN), self.audio)
        attempt = report["attempts"][0]
        self.assertEqual(attempt["outcome"], "admission_error")
        self.assertEqual(attempt["diagnostic"], "auth_subprotocol_not_negotiated")
        self.assertFalse(attempt["admitted"])
        self.assertEqual(attempt["bytes_sent"], 0)
        self.assertEqual(self.trace[0]["frames"], [])
        self.verify_exports(report)

    async def test_refused_loopback_connection_has_no_disconnect_observation(self):
        # Reserve a loopback port without listening: cannot reach any service.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
            config = harness.Config(f"ws://127.0.0.1:{port}/ws/transcribe", concurrency=1,
                                    ramp=0, connect_timeout=5, run_id=self._testMethodName,
                                    scenario="mock-validation-not-performance")
            report = await harness.run_benchmark(config, self.audio)
        attempt = report["attempts"][0]
        self.assertEqual(attempt["outcome"], "admission_error")
        self.assertFalse(attempt["handshake_completed"])
        self.assertFalse(attempt["unexpected_disconnect"])
        self.assertIsNone(attempt["socket_closed_offset_ms"])
        self.assertIsNone(attempt["close_code"])
        self.verify_summary(report)
        self.verify_exports(report)

    async def test_cli_exit_codes_privacy_and_exports(self):
        for scenario, auth, expected_code in (("silent", False, 0), ("timing", True, 0),
                                               ("auth_rejected", True, 1)):
            self.connections = 0
            async with self.server([scenario], auth=auth) as config:
                output = self.root / scenario
                args = ["--url", config.url, "--concurrency", "1", "--ramp", "0",
                        "--token-env", TOKEN_ENV, "--output-json", str(output / "results.json"),
                        "--output-csv", str(output / "results.csv"),
                        "--run-id", "cli-local-validation-only-" + scenario,
                        "--scenario", "mock-validation-not-performance"]
                args += ["--auth", "--audio-file", str(self.wav_path)] if auth else ["--no-auth", "--duration", ".25"]
                stdout = io.StringIO()
                with patch.dict(os.environ, {TOKEN_ENV: TOKEN, "NO_PROXY": "127.0.0.1"}), \
                        contextlib.redirect_stdout(stdout):
                    code = await asyncio.to_thread(harness.main, args)
                self.assertEqual(code, expected_code)
                self.assertNotIn(TOKEN, stdout.getvalue())
                self.assertNotIn(TEXT, stdout.getvalue())
                report = json.loads((output / "results.json").read_text(encoding="utf-8"))
                if not auth:
                    self.assertNotIn("time_to_first_partial_ms", report["summary"]["latencies"])
                self.verify_summary(report)
                self.verify_exports(report, scenario)


if __name__ == "__main__":
    unittest.main()
