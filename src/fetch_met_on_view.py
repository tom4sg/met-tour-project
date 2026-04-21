#!/usr/bin/env python3
"""
Fetch all on-display objects from the Met Collection API.

Strategy:
  1) GET /search?isOnView=true&q=* → objectIDs currently on view
    2) Reconcile output CSV           → drop rows for IDs no longer on view
    3) GET /objects/{id}             → full record for each remaining ID (serial, rate-limited)
    4) Append each row to CSV immediately as it's fetched; resume by skipping IDs already in output file.

Rate: Met asks for ≤80 req/s from a single IP. Default 10 req/s.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://collectionapi.metmuseum.org/public/collection/v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "data" / "processed" / "met_on_view.csv"

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MetOnViewFetcher/1.0; educational; "
        "+https://github.com/metmuseum/openaccess)"
    ),
    "Accept": "application/json",
}

_RESET = "\033[0m"
_COLORS = {
    "INFO": "\033[36m",
    "WARN": "\033[33m",
    "ERROR": "\033[31m",
    "SUCCESS": "\033[32m",
}

_COLOR_ENABLED = False


class RateLimiter:
    """Enforce a minimum interval between calls, with adaptive slowdown on 403s."""

    def __init__(self, max_rps: float) -> None:
        self._target_interval = 1.0 / max_rps if max_rps > 0 else 0.0
        self._interval = self._target_interval
        self._last = 0.0

    def wait(self) -> None:
        if self._interval <= 0:
            return
        now = time.monotonic()
        gap = self._last + self._interval - now
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()

    def on_403(self) -> None:
        """Double the interval (halve effective RPS) up to a max of 30s between requests."""
        self._interval = min(30.0, self._interval * 2)
        print(f"  rate limiter slowed to {1/self._interval:.2f} req/s", file=sys.stderr)

    def on_success(self) -> None:
        """Nudge interval back toward target by 10% each successful request."""
        if self._interval > self._target_interval:
            self._interval = max(self._target_interval, self._interval * 0.9)

    @property
    def current_rps(self) -> float:
        if self._interval <= 0:
            return float("inf")
        return 1.0 / self._interval


def fetch_json(
    url: str,
    *,
    timeout: float = 120,
    limiter: RateLimiter | None = None,
    retries: int = 8,
    metrics: dict[str, int] | None = None,
) -> dict:
    """GET JSON with retries on 403/429 and transient network errors."""
    if limiter is not None:
        limiter.wait()
    for attempt in range(max(1, retries)):
        req = Request(url, headers=_HTTP_HEADERS)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code == 404:
                if metrics is not None:
                    metrics["http_404"] = metrics.get("http_404", 0) + 1
                raise
            if e.code in (403, 429) and attempt + 1 < retries:
                wait = min(60.0, 2.0 * (2**attempt))
                if metrics is not None:
                    metrics["retries_total"] = metrics.get("retries_total", 0) + 1
                    key = f"http_{e.code}_retries"
                    metrics[key] = metrics.get(key, 0) + 1
                print(
                    f"  HTTP {e.code} on attempt {attempt+1}, backing off {wait:.0f}s…",
                    file=sys.stderr,
                )
                time.sleep(wait)
                if limiter is not None:
                    limiter.on_403()
                    limiter.wait()
                continue
            if metrics is not None:
                metrics["http_errors_terminal"] = (
                    metrics.get("http_errors_terminal", 0) + 1
                )
            raise
        except URLError:
            if attempt + 1 < retries:
                if metrics is not None:
                    metrics["retries_total"] = metrics.get("retries_total", 0) + 1
                    metrics["url_errors_retried"] = (
                        metrics.get("url_errors_retried", 0) + 1
                    )
                time.sleep(min(30.0, 1.0 * (2**attempt)))
                if limiter is not None:
                    limiter.wait()
                continue
            if metrics is not None:
                metrics["url_errors_terminal"] = (
                    metrics.get("url_errors_terminal", 0) + 1
                )
            raise
    raise RuntimeError(f"Exhausted retries for {url}")


def supports_color() -> bool:
    if not sys.stderr.isatty():
        return False
    if os.getenv("NO_COLOR") is not None:
        return False
    term = os.getenv("TERM", "")
    return term not in ("", "dumb")


def log_event(message: str, level: str = "INFO") -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] "
    msg = f"{message}"
    if _COLOR_ENABLED:
        color = _COLORS.get(level, "")
        if color:
            line = f"{color}{line}{_RESET}{msg}"
    print(line, file=sys.stderr)


def flatten(obj: dict) -> dict:
    row: dict = {}
    for k, v in obj.items():
        if isinstance(v, (list, dict)):
            row[k] = json.dumps(v, ensure_ascii=False) if v else ""
        elif v is None:
            row[k] = ""
        else:
            row[k] = v
    return row


def reconcile_output_with_on_view_ids(
    path: Path, valid_ids: set[int]
) -> tuple[set[int], list[str] | None, int]:
    """Keep only rows whose objectID is still in the current on-view set."""
    if not path.exists() or path.stat().st_size == 0:
        return set(), None, 0

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "objectID" not in reader.fieldnames:
            return set(), None, 0
        fieldnames = list(reader.fieldnames)
        kept_rows: list[dict[str, str]] = []
        kept_ids: set[int] = set()
        removed = 0

        for row in reader:
            try:
                oid = int(row.get("objectID", ""))
            except (TypeError, ValueError):
                # Malformed IDs are treated as stale rows.
                removed += 1
                continue

            if oid in valid_ids:
                kept_rows.append(row)
                kept_ids.add(oid)
            else:
                removed += 1

    if removed > 0:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(kept_rows)

    return kept_ids, fieldnames, removed


def fetch_on_view_ids(limiter: RateLimiter) -> list[int]:
    url = f"{BASE}/search?isOnView=true&q=*"
    log_event("Refreshing current on-view ID list…")
    try:
        data = fetch_json(url, limiter=limiter)
    except HTTPError:
        url = f"{BASE}/search?isOnView=true&q=%20"
        data = fetch_json(url, limiter=limiter)
    ids = data.get("objectIDs") or []
    log_event(f"On-view IDs: {len(ids)} (API total: {data.get('total')})")
    return ids


def main() -> int:
    p = argparse.ArgumentParser(
        description="Met Collection API → CSV (on-view objects only)"
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--limit", type=int, default=None, help="Only fetch first N IDs (test)"
    )
    p.add_argument(
        "--rps",
        type=float,
        default=2.3,
        metavar="N",
        help="Max requests per second (Met policy: ≤80; default 2.3)",
    )
    p.add_argument(
        "--progress-every",
        type=int,
        default=100,
        metavar="N",
        help="Emit progress every N fetched rows (default 100)",
    )
    p.add_argument(
        "--heartbeat-sec",
        type=float,
        default=30.0,
        metavar="SEC",
        help="Emit progress heartbeat every SEC seconds (default 30)",
    )
    p.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors in observability logs",
    )
    args = p.parse_args()

    global _COLOR_ENABLED
    _COLOR_ENABLED = supports_color() and not args.no_color

    args.out.parent.mkdir(parents=True, exist_ok=True)

    if args.rps > 80:
        log_event(
            "Warning: --rps above 80 violates Met guidance; clamping to 80.", "WARN"
        )
        args.rps = 80.0
    if args.rps <= 0:
        log_event("Error: --rps must be positive.", "ERROR")
        return 2
    if args.progress_every <= 0:
        log_event("Error: --progress-every must be positive.", "ERROR")
        return 2
    if args.heartbeat_sec <= 0:
        log_event("Error: --heartbeat-sec must be positive.", "ERROR")
        return 2

    limiter = RateLimiter(args.rps)
    metrics: dict[str, int] = {}
    run_start = time.monotonic()
    log_event(
        f"Start run: out={args.out}, rps_target={args.rps:.2f}, "
        f"progress_every={args.progress_every}, heartbeat_sec={args.heartbeat_sec:.1f}"
    )

    ids = fetch_on_view_ids(limiter)
    if not ids:
        log_event("No on-view IDs returned. Exiting.", "WARN")
        return 1

    on_view_set = set(ids)

    done, fieldnames, removed = reconcile_output_with_on_view_ids(args.out, on_view_set)
    if removed:
        log_event(
            f"Pruned {removed} stale rows not currently on view from {args.out}", "WARN"
        )

    if args.limit is not None:
        ids = ids[: args.limit]

    if done:
        log_event(f"Resume: {len(done)} IDs already in {args.out}")

    todo = [oid for oid in ids if oid not in done]
    if not todo:
        log_event(
            "All current on-view IDs are already present in the CSV; no object records to fetch.",
            "SUCCESS",
        )
        return 0

    log_event(f"Missing current IDs to fetch: {len(todo)}")

    def write_row(row: dict) -> None:
        nonlocal fieldnames
        if fieldnames is None:
            fieldnames = sorted(row.keys())
        file_exists = args.out.exists() and args.out.stat().st_size > 0
        with args.out.open(
            "a" if file_exists else "w", newline="", encoding="utf-8"
        ) as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in fieldnames})

    n_ok = n_skip = n_fail = 0
    n_skip_404 = n_skip_invalid = 0
    last_heartbeat = time.monotonic()
    total = len(todo)

    def emit_progress(force: bool = False) -> None:
        nonlocal last_heartbeat
        now = time.monotonic()
        if not force and (now - last_heartbeat) < args.heartbeat_sec:
            return
        elapsed = max(1e-9, now - run_start)
        processed = n_ok + n_skip + n_fail
        rate = processed / elapsed
        remaining = max(0, total - processed)
        eta_sec = remaining / rate if rate > 0 else math.inf
        eta_s = "inf" if not math.isfinite(eta_sec) else f"{eta_sec:.1f}s"
        log_event(
            "Progress: "
            f"processed={processed}/{total}, ok={n_ok}, skip={n_skip}, fail={n_fail}, "
            f"rate={rate:.2f}/s, limiter_rps={limiter.current_rps:.2f}, eta={eta_s}, "
            f"retries={metrics.get('retries_total', 0)}, "
            f"http403_retries={metrics.get('http_403_retries', 0)}, "
            f"http429_retries={metrics.get('http_429_retries', 0)}, "
            f"net_retries={metrics.get('url_errors_retried', 0)}"
        )
        last_heartbeat = now

    for i, oid in enumerate(todo):
        try:
            data = fetch_json(f"{BASE}/objects/{oid}", limiter=limiter, metrics=metrics)
        except HTTPError as e:
            if e.code == 404:
                n_skip += 1
                n_skip_404 += 1
                if n_skip_404 <= 5:
                    log_event(f"Skip objectID {oid}: HTTP 404 not found", "WARN")
                emit_progress()
                continue
            log_event(f"Error objectID {oid}: HTTP {e.code} - skipping", "ERROR")
            n_fail += 1
            emit_progress()
            continue
        except URLError as e:
            log_event(f"Error objectID {oid}: network {e} - skipping", "ERROR")
            n_fail += 1
            emit_progress()
            continue

        if not isinstance(data, dict) or "objectID" not in data:
            n_skip += 1
            n_skip_invalid += 1
            if n_skip_invalid <= 5:
                log_event(
                    f"Skip objectID {oid}: unexpected payload type={type(data).__name__}",
                    "WARN",
                )
            emit_progress()
            continue

        limiter.on_success()
        write_row(flatten(data))
        n_ok += 1
        if n_ok % args.progress_every == 0:
            emit_progress(force=True)
        else:
            emit_progress()

    emit_progress(force=True)
    elapsed = max(1e-9, time.monotonic() - run_start)
    processed = n_ok + n_skip + n_fail
    log_event(
        "Done. "
        f"new_rows={n_ok}, skipped={n_skip}, failed={n_fail}, "
        f"skip_404={n_skip_404}, skip_invalid={n_skip_invalid}, "
        f"processed={processed}, elapsed={elapsed:.1f}s, "
        f"avg_rate={processed/elapsed:.2f}/s, output={args.out}, "
        f"retries_total={metrics.get('retries_total', 0)}, "
        f"http403_retries={metrics.get('http_403_retries', 0)}, "
        f"http429_retries={metrics.get('http_429_retries', 0)}, "
        f"http_terminal_errors={metrics.get('http_errors_terminal', 0)}, "
        f"net_terminal_errors={metrics.get('url_errors_terminal', 0)}",
        "SUCCESS",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
