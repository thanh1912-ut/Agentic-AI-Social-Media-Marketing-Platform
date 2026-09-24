"""Run a bounded readiness-load smoke against a local disposable stack only."""

from __future__ import annotations

import argparse
import concurrent.futures
import ipaddress
import json
import statistics
import time
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


def _is_loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _request(url: str, timeout: float) -> tuple[int | None, float, bool, str | None]:
    started = time.perf_counter()
    try:
        with urlopen(url, timeout=timeout) as response:
            status = response.status
            payload = json.loads(response.read(1024 * 1024))
        dependencies = payload.get("dependencies") if isinstance(payload, dict) else None
        ready = (
            status == 200
            and isinstance(payload, dict)
            and payload.get("status") == "ready"
            and dependencies == {"database": True, "redis": True, "object_storage": True}
        )
        return status, (time.perf_counter() - started) * 1000, ready, None
    except HTTPError as error:
        status = error.code
        error.close()
        return status, (time.perf_counter() - started) * 1000, False, "http_error"
    except (URLError, TimeoutError, OSError, ValueError) as error:
        return None, (time.perf_counter() - started) * 1000, False, type(error).__name__


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * fraction)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/readyz")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()

    parsed = urlsplit(args.url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or not _is_loopback(parsed.hostname)
        or parsed.path != "/readyz"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        parser.error("--url must be a loopback HTTP(S) origin with exactly the /readyz path")
    if args.requests < 1 or args.concurrency < 1 or args.warmup < 0 or args.timeout <= 0:
        parser.error("requests/concurrency must be positive, warmup non-negative, timeout positive")

    url = args.url
    warmup = [_request(url, args.timeout) for _ in range(args.warmup)]
    if any(not ready for _, _, ready, _ in warmup):
        print(json.dumps({"phase": "warmup", "results": [status for status, _, _, _ in warmup]}))
        return 1

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(executor.map(lambda _: _request(url, args.timeout), range(args.requests)))
    elapsed_seconds = time.perf_counter() - started
    latencies = [duration for _, duration, _, _ in results]
    statuses = Counter(str(status) if status is not None else "error" for status, _, _, _ in results)
    errors = Counter(error for _, _, _, error in results if error)
    ready_count = sum(1 for _, _, ready, _ in results if ready)

    report = {
        "endpoint": "/readyz",
        "requests": args.requests,
        "concurrency": min(args.concurrency, args.requests),
        "warmup": args.warmup,
        "statuses": dict(statuses),
        "ready_payloads": ready_count,
        "errors": dict(errors),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "requests_per_second": round(args.requests / elapsed_seconds, 2),
        "latency_ms": {
            "min": round(min(latencies), 2),
            "mean": round(statistics.mean(latencies), 2),
            "p50": round(_percentile(latencies, 0.50), 2),
            "p95": round(_percentile(latencies, 0.95), 2),
            "max": round(max(latencies), 2),
        },
        "retries": 0,
        "scope": "readiness endpoint only; not a campaign/API or production-capacity benchmark",
    }
    print(json.dumps(report, indent=2))
    return 0 if ready_count == args.requests else 1


if __name__ == "__main__":
    raise SystemExit(main())
