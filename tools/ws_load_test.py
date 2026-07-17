#!/usr/bin/env python3
"""LiveCap WebSocket load test.

Opens many concurrent WebSocket sessions against the ``/ws/transcribe`` endpoint,
streams valid silent PCM for a short time, then stops. Use it to validate the
shared active-session limit across ECS tasks (Phase 3) and to watch the service
scale out under concurrency.

It sends structurally valid audio (3200-byte zero-filled 16-bit mono 16 kHz
frames) so the backend does not reject frames as malformed. It does NOT verify
transcription output — the goal is connection admission and scaling behaviour.

Usage
-----
    pip install websockets
    python tools/ws_load_test.py \
        --url wss://<host>/ws/transcribe \
        --concurrency 12 --duration 8 --ramp 0.2

Notes
-----
* Wake the backend first (open the app once, or hit the wake endpoint) if it has
  scaled to zero, otherwise the first connections race the cold start.
* "Admitted" connections that exceed the configured global limit are expected to
  be rejected with code TOO_MANY_SESSIONS — that is the limit working.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import statistics
import time
from dataclasses import dataclass, field

try:
    import websockets
except ImportError:  # pragma: no cover
    raise SystemExit("This tool requires the 'websockets' package: pip install websockets")

# 100 ms of 16 kHz, 16-bit, mono PCM = 3200 bytes. Zero-filled = silence.
_FRAME = bytes(3200)
_FRAME_INTERVAL_S = 0.1


@dataclass
class Result:
    admitted: int = 0
    rejected_limit: int = 0
    errors: int = 0
    connect_latencies: list[float] = field(default_factory=list)
    error_details: list[str] = field(default_factory=list)


async def _one_session(
    idx: int,
    url: str,
    duration: float,
    ssl_ctx: ssl.SSLContext | None,
    result: Result,
) -> None:
    started = time.monotonic()
    try:
        async with websockets.connect(url, ssl=ssl_ctx, max_size=None) as ws:
            # Wait for the first server message: session_start or an error.
            first = await asyncio.wait_for(ws.recv(), timeout=30)
            msg = json.loads(first) if isinstance(first, str) else {}
            mtype = msg.get("type")

            if mtype == "error":
                if msg.get("code") == "TOO_MANY_SESSIONS":
                    result.rejected_limit += 1
                else:
                    result.errors += 1
                    result.error_details.append(f"[{idx}] error {msg.get('code')}")
                return
            if mtype != "session_start":
                result.errors += 1
                result.error_details.append(f"[{idx}] unexpected first message {mtype}")
                return

            result.admitted += 1
            result.connect_latencies.append(time.monotonic() - started)

            # Stream silent frames for the requested duration.
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                await ws.send(_FRAME)
                await asyncio.sleep(_FRAME_INTERVAL_S)

            await ws.send(json.dumps({"type": "stop"}))
            # Drain until the socket closes or session_end arrives.
            try:
                while True:
                    reply = await asyncio.wait_for(ws.recv(), timeout=10)
                    if isinstance(reply, str):
                        rmsg = json.loads(reply)
                        if rmsg.get("type") == "session_end":
                            break
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                pass
    except Exception as exc:  # noqa: BLE001
        result.errors += 1
        result.error_details.append(f"[{idx}] {type(exc).__name__}: {exc}")


async def _run(args: argparse.Namespace) -> Result:
    ssl_ctx: ssl.SSLContext | None = None
    if args.url.startswith("wss://"):
        ssl_ctx = ssl.create_default_context()
        if args.insecure:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

    sep = "&" if "?" in args.url else "?"
    url = f"{args.url}{sep}source={args.source}&target={args.target}"

    result = Result()
    tasks: list[asyncio.Task] = []
    for i in range(args.concurrency):
        tasks.append(asyncio.create_task(_one_session(i, url, args.duration, ssl_ctx, result)))
        if args.ramp > 0:
            await asyncio.sleep(args.ramp)
    await asyncio.gather(*tasks)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="LiveCap WebSocket load test")
    parser.add_argument("--url", required=True, help="wss://<host>/ws/transcribe")
    parser.add_argument("--concurrency", type=int, default=8, help="Concurrent sessions")
    parser.add_argument("--duration", type=float, default=8.0, help="Seconds of audio per session")
    parser.add_argument("--ramp", type=float, default=0.2, help="Seconds between new connections")
    parser.add_argument("--source", default="vi-VN", help="Source language code")
    parser.add_argument("--target", default="en", help="Target language code")
    parser.add_argument("--insecure", action="store_true", help="Skip TLS verification")
    args = parser.parse_args()

    print(f"Opening {args.concurrency} sessions to {args.url} (ramp {args.ramp}s)...")
    start = time.monotonic()
    result = asyncio.run(_run(args))
    elapsed = time.monotonic() - start

    print("\n=== Load test summary ===")
    print(f"Total attempted     : {args.concurrency}")
    print(f"Admitted            : {result.admitted}")
    print(f"Rejected (limit)    : {result.rejected_limit}")
    print(f"Errors              : {result.errors}")
    if result.connect_latencies:
        lat = sorted(result.connect_latencies)
        p50 = statistics.median(lat)
        p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
        print(f"Connect latency     : p50={p50:.2f}s p95={p95:.2f}s max={lat[-1]:.2f}s")
    print(f"Wall time           : {elapsed:.1f}s")
    for detail in result.error_details[:10]:
        print(f"  ! {detail}")


if __name__ == "__main__":
    main()
