"""Reproducible localhost research audit. No credentials, settings changes, or broker orders."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def fetch(base, path, method="GET", body=None, timeout=20):
    started = time.perf_counter()
    try:
        request = Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                          headers={"Accept": "application/json", "Content-Type": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
            return {"path": path, "status": response.status, "milliseconds": round((time.perf_counter()-started)*1000, 2), "payload": payload}
    except HTTPError as error:
        return {"path": path, "status": error.code, "milliseconds": round((time.perf_counter()-started)*1000, 2)}
    except Exception as error:
        return {"path": path, "status": "ERROR", "error": str(error), "milliseconds": round((time.perf_counter()-started)*1000, 2)}


def check_candles(result, timeframe):
    payload = result.get("payload", {})
    candles = payload.get("candles", [])
    opens = [datetime.fromisoformat(item["open_time_utc"].replace("Z", "+00:00")) for item in candles]
    now = datetime.now(UTC)
    duration = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}[timeframe]
    result["integrity"] = {
        "count": len(candles), "completed": sum(item["completed"] for item in candles),
        "forming": sum(not item["completed"] for item in candles),
        "strictly_ordered": bool(opens) and all(b > a for a, b in zip(opens, opens[1:])),
        "ohlc_valid": bool(candles) and all(0 < item["low"] <= min(item["open"], item["close"]) <= max(item["open"], item["close"]) <= item["high"] for item in candles),
        "no_future_completed": all(not item["completed"] or at + timedelta(seconds=duration) <= now + timedelta(seconds=2) for at, item in zip(opens, candles)),
    }


async def socket_probe(base):
    try:
        import websockets
        events = []
        async with websockets.connect(base.replace("http", "ws", 1) + "/ws/live", open_timeout=10) as socket:
            deadline = asyncio.get_running_loop().time() + 15
            while asyncio.get_running_loop().time() < deadline:
                packet = json.loads(await asyncio.wait_for(socket.recv(), timeout=12))
                events.append(packet)
                if {"quote", "bar_update"} <= {event["type"] for event in events}:
                    break
        return {"events": events, "types": sorted({event["type"] for event in events})}
    except Exception as error:
        return {"error": str(error)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=330)
    parser.add_argument("--validate-archive", action="store_true")
    args = parser.parse_args()
    if args.base != "http://127.0.0.1:8765":
        parser.error("The audit is restricted to this local research instance")
    report = {"started_at_utc": datetime.now(UTC).isoformat(), "source": "LIVE_LOCAL_HTTP_AND_MT5", "requests": [], "observations": []}
    paths = ["/api/health", "/api/connection", "/api/quote", "/api/analysis", "/api/events", "/api/research", "/api/research/live-watch", "/api/research/pipeline", "/api/research/validation", "/api/signals/history", "/api/research/models", "/api/research/operations", "/api/research/strategies", "/api/strategy-journal", "/api/macro/official", "/api/kronos/status", "/api/kronos/forecasts", "/api/sources/capabilities", "/api/market/scan"]
    report["requests"] = [fetch(args.base, path) for path in paths]
    for frame in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"):
        result = fetch(args.base, f"/api/candles?tf={frame}&limit=300")
        check_candles(result, frame)
        report["requests"].append(result)
    report["protected_routes"] = [fetch(args.base, "/api/research/pipeline/control", "POST", {"enabled": False}), fetch(args.base, "/api/hfm/account/financials")]
    report["manual_review"] = fetch(args.base, "/api/research/analyze", "POST")
    report["socket"] = asyncio.run(socket_probe(args.base))
    with ThreadPoolExecutor(max_workers=4) as pool:
        report["concurrent_health"] = list(pool.map(lambda _: fetch(args.base, "/api/health"), range(12)))
    if args.validate_archive:
        report["historical_validation"] = fetch(args.base, "/api/backtests/validate", "POST", timeout=240)
        report["historical_backtest"] = fetch(args.base, "/api/backtests/run", "POST", timeout=120)
    deadline = time.monotonic() + max(0, args.seconds)
    while True:
        observation = {"at_utc": datetime.now(UTC).isoformat(), "pipeline": fetch(args.base, "/api/research/pipeline"), "watch": fetch(args.base, "/api/research/live-watch"), "history": fetch(args.base, "/api/signals/history")}
        report["observations"].append(observation)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        pipeline = observation["pipeline"].get("payload", {})
        print(json.dumps({"observation": len(report["observations"]), "last_run": pipeline.get("latest_run"), "worker_error": pipeline.get("last_error")}), flush=True)
        if time.monotonic() >= deadline:
            break
        time.sleep(min(15, max(0, deadline - time.monotonic())))
    report["finished_at_utc"] = datetime.now(UTC).isoformat()
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Saved", args.output, flush=True)


if __name__ == "__main__":
    main()
