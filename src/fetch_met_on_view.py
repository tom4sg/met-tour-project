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

# Base URL for the Metropolitan Museum of Art's public Collection API.
BASE = "https://collectionapi.metmuseum.org/public/collection/v1"

# Resolve the project root as two levels up from this file (src/ → project root).
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Default output path for the CSV file containing on-view object records.
DEFAULT_OUT = PROJECT_ROOT / "data" / "processed" / "met_on_view.csv"

# HTTP headers sent with every request. The User-Agent identifies this script
# to the Met API and links to the open-access repo for transparency.
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MetOnViewFetcher/1.0; educational; "
        "+https://github.com/metmuseum/openaccess)"
    ),
    "Accept": "application/json",
}

# ANSI escape code to reset terminal color back to default.
_RESET = "\033[0m"

# Mapping of log level names to their ANSI color codes for terminal output.
_COLORS = {
    "INFO": "\033[36m",  # Cyan
    "WARN": "\033[33m",  # Yellow
    "ERROR": "\033[31m",  # Red
    "SUCCESS": "\033[32m",  # Green
}

# Global flag controlling whether ANSI color codes are emitted in log output.
# Set at runtime based on terminal capabilities and --no-color flag.
_COLOR_ENABLED = False


class RateLimiter:
    """Enforce a minimum interval between calls, with adaptive slowdown on 403s.

    The limiter tracks the time of the last request and sleeps as needed to
    maintain the configured requests-per-second rate. When the API responds
    with HTTP 403 (rate limit exceeded), the interval is doubled to back off.
    After each successful response, the interval is nudged back toward the
    original target to recover throughput gradually.
    """

    def __init__(self, max_rps: float) -> None:
        # Compute the minimum number of seconds that must elapse between requests.
        # If max_rps is 0 or negative, no delay is enforced (interval = 0).
        self._target_interval = 1.0 / max_rps if max_rps > 0 else 0.0
        # Current effective interval; starts at target and adapts at runtime.
        self._interval = self._target_interval
        # Monotonic timestamp of the most recent request; 0.0 means no request yet.
        self._last = 0.0

    def wait(self) -> None:
        """Block until enough time has passed since the last request.

        Calculates the remaining gap between now and when the next request is
        allowed, then sleeps for that duration. Updates _last after sleeping so
        subsequent calls measure from the correct baseline.
        """
        if self._interval <= 0:
            return  # No rate limiting configured; return immediately.
        now = time.monotonic()
        # How many seconds remain before we're allowed to fire the next request.
        gap = self._last + self._interval - now
        if gap > 0:
            time.sleep(gap)
        # Record the time after sleeping so the next call measures from here.
        self._last = time.monotonic()

    def on_403(self) -> None:
        """Double the interval (halve effective RPS) up to a max of 30s between requests.

        Called whenever the API returns HTTP 403 to signal that we are sending
        requests too quickly. Exponential back-off is capped at 30 seconds to
        avoid indefinitely stalling the run.
        """
        self._interval = min(30.0, self._interval * 2)
        print(f"  rate limiter slowed to {1/self._interval:.2f} req/s", file=sys.stderr)

    def on_success(self) -> None:
        """Nudge interval back toward target by 10% each successful request.

        After a successful response the API is clearly accepting our rate, so
        we incrementally recover toward the original target RPS. The 10% step
        prevents oscillation while still converging reasonably quickly.
        """
        if self._interval > self._target_interval:
            self._interval = max(self._target_interval, self._interval * 0.9)

    @property
    def current_rps(self) -> float:
        """Return the current effective requests-per-second rate.

        Returns infinity when no interval is configured (unlimited mode).
        """
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
    """GET a URL and return the parsed JSON response, with retries on transient errors.

    Handles two categories of failure:
      - HTTPError with code 403/429: rate-limit responses; backs off exponentially
        and notifies the limiter so it slows down future requests.
      - HTTPError with code 404: not-found; re-raised immediately (no retry).
      - URLError: network-level failures (DNS, connection refused, timeout);
        retried with exponential back-off.

    All retry counts and terminal error counts are recorded in the optional
    `metrics` dict so the caller can surface them in progress/summary logs.

    Args:
        url:     The fully-qualified URL to fetch.
        timeout: Socket timeout in seconds for each individual attempt.
        limiter: Optional RateLimiter; if provided, `wait()` is called before
                 the first attempt and after each back-off sleep.
        retries: Maximum number of attempts before giving up.
        metrics: Optional dict updated in-place with counters for retries and
                 terminal errors (keys: retries_total, http_404, http_4xx_retries,
                 http_errors_terminal, url_errors_retried, url_errors_terminal).

    Returns:
        Parsed JSON response as a Python dict.

    Raises:
        HTTPError: On 404 (immediately) or any non-retryable HTTP error after
                   all retries are exhausted.
        URLError:  After all retries are exhausted for network-level failures.
        RuntimeError: If the retry loop exits without returning (should not happen
                      under normal conditions).
    """
    # Honour the rate limiter before the very first attempt.
    if limiter is not None:
        limiter.wait()

    for attempt in range(max(1, retries)):
        req = Request(url, headers=_HTTP_HEADERS)
        try:
            with urlopen(req, timeout=timeout) as resp:
                # Successful response: decode bytes → str → dict.
                return json.loads(resp.read().decode())

        except HTTPError as e:
            # 404 means the object simply doesn't exist; no point retrying.
            if e.code == 404:
                if metrics is not None:
                    metrics["http_404"] = metrics.get("http_404", 0) + 1
                raise

            # 403 (Forbidden / rate-limited) and 429 (Too Many Requests) are
            # transient; back off and retry if we have attempts remaining.
            if e.code in (403, 429) and attempt + 1 < retries:
                # Exponential back-off: 2s, 4s, 8s … capped at 60s.
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
                # Inform the limiter so it reduces its target RPS going forward.
                if limiter is not None:
                    limiter.on_403()
                    limiter.wait()
                continue  # Retry the request.

            # Any other HTTP error (5xx, etc.) after exhausting retries is terminal.
            if metrics is not None:
                metrics["http_errors_terminal"] = (
                    metrics.get("http_errors_terminal", 0) + 1
                )
            raise

        except URLError:
            # Network-level error (DNS failure, connection refused, timeout, etc.).
            if attempt + 1 < retries:
                if metrics is not None:
                    metrics["retries_total"] = metrics.get("retries_total", 0) + 1
                    metrics["url_errors_retried"] = (
                        metrics.get("url_errors_retried", 0) + 1
                    )
                # Exponential back-off: 1s, 2s, 4s … capped at 30s.
                time.sleep(min(30.0, 1.0 * (2**attempt)))
                if limiter is not None:
                    limiter.wait()
                continue  # Retry the request.

            # All retries exhausted; record as a terminal network error.
            if metrics is not None:
                metrics["url_errors_terminal"] = (
                    metrics.get("url_errors_terminal", 0) + 1
                )
            raise

    # Should be unreachable: the loop always raises or returns before here.
    raise RuntimeError(f"Exhausted retries for {url}")


def supports_color() -> bool:
    """Return True if the current stderr terminal supports ANSI color codes.

    Checks three conditions:
      1. stderr must be a real TTY (not redirected to a file or pipe).
      2. The NO_COLOR environment variable must not be set (respects the
         https://no-color.org convention).
      3. The TERM variable must not be empty or "dumb" (basic terminals that
         don't understand escape sequences).
    """
    if not sys.stderr.isatty():
        return False
    if os.getenv("NO_COLOR") is not None:
        return False
    term = os.getenv("TERM", "")
    return term not in ("", "dumb")


def log_event(message: str, level: str = "INFO") -> None:
    """Write a timestamped, optionally colorized log line to stderr.

    Format: [YYYY-MM-DD HH:MM:SS] [LEVEL] <message>

    When color is enabled (_COLOR_ENABLED is True), the level prefix is wrapped
    in the ANSI color code for that level. The message itself is left uncolored
    so it remains readable in log files if stderr is later inspected.

    Args:
        message: Human-readable description of the event.
        level:   Severity label; one of INFO, WARN, ERROR, SUCCESS.
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] "
    msg = f"{message}"
    if _COLOR_ENABLED:
        color = _COLORS.get(level, "")
        if color:
            # Apply color only to the prefix; reset before the message body.
            line = f"{color}{line}{_RESET}{msg}"
    print(line, file=sys.stderr)


def flatten(obj: dict) -> dict:
    """Convert a nested Met API object record into a flat dict suitable for CSV.

    The Met API returns some fields as lists or nested dicts (e.g. tags,
    constituents). CSV rows must be scalar, so this function serialises any
    list or dict value to a compact JSON string. Empty lists/dicts become an
    empty string. None values also become empty strings. All other values are
    passed through unchanged.

    Args:
        obj: A raw object record dict as returned by the Met API.

    Returns:
        A new dict with the same keys but all values coerced to scalars.
    """
    row: dict = {}
    for k, v in obj.items():
        if isinstance(v, (list, dict)):
            # Serialise complex types to JSON; use "" for empty containers.
            row[k] = json.dumps(v, ensure_ascii=False) if v else ""
        elif v is None:
            # Represent missing values as empty strings in the CSV.
            row[k] = ""
        else:
            # Scalars (int, float, bool, str) are written as-is.
            row[k] = v
    return row


def reconcile_output_with_on_view_ids(
    path: Path, valid_ids: set[int]
) -> tuple[set[int], list[str] | None, int]:
    """Keep only rows whose objectID is still in the current on-view set.

    Reads the existing output CSV (if any), discards rows for objects that are
    no longer on display at the Met, and rewrites the file in-place with only
    the surviving rows. This prevents the CSV from accumulating stale records
    for objects that have been taken off view since the last run.

    Args:
        path:      Path to the output CSV file.
        valid_ids: Set of objectIDs currently reported as on-view by the API.

    Returns:
        A 3-tuple of:
          - kept_ids:   Set of objectIDs that were retained in the CSV.
          - fieldnames: Column headers from the existing CSV, or None if the
                        file was absent/empty/missing the objectID column.
          - removed:    Number of rows that were pruned (stale or malformed).
    """
    # If the file doesn't exist or is empty there's nothing to reconcile.
    if not path.exists() or path.stat().st_size == 0:
        return set(), None, 0

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # If the file has no headers or is missing the objectID column we can't
        # reconcile; treat it as if it were empty.
        if not reader.fieldnames or "objectID" not in reader.fieldnames:
            return set(), None, 0
        fieldnames = list(reader.fieldnames)
        kept_rows: list[dict[str, str]] = []
        kept_ids: set[int] = set()
        removed = 0  # Counter for rows that will be pruned.

        for row in reader:
            try:
                oid = int(row.get("objectID", ""))
            except (TypeError, ValueError):
                # Row has a non-integer objectID; treat as stale and discard.
                removed += 1
                continue

            if oid in valid_ids:
                # Object is still on view; keep the row.
                kept_rows.append(row)
                kept_ids.add(oid)
            else:
                # Object is no longer on view; discard the row.
                removed += 1

    # Only rewrite the file if we actually removed something, to avoid
    # unnecessary disk I/O on runs where nothing changed.
    if removed > 0:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(kept_rows)

    return kept_ids, fieldnames, removed


def fetch_on_view_ids(limiter: RateLimiter) -> list[int]:
    """Retrieve the list of objectIDs currently on view at the Met.

    Calls the /search endpoint with isOnView=true and a wildcard query to get
    all on-view IDs. Falls back to a URL-encoded space query if the bare `*`
    wildcard triggers an HTTP error (some API versions reject it).

    Args:
        limiter: RateLimiter instance used to throttle the search request.

    Returns:
        List of integer objectIDs for all objects currently on display.
    """
    url = f"{BASE}/search?isOnView=true&q=*"
    log_event("Refreshing current on-view ID list…")
    try:
        data = fetch_json(url, limiter=limiter)
    except HTTPError:
        # Fallback: some API versions reject bare `*`; try a URL-encoded space.
        url = f"{BASE}/search?isOnView=true&q=%20"
        data = fetch_json(url, limiter=limiter)
    ids = data.get("objectIDs") or []
    log_event(f"On-view IDs: {len(ids)} (API total: {data.get('total')})")
    return ids


def main() -> int:
    """Entry point: parse arguments, orchestrate fetching, and write the CSV.

    Workflow:
      1. Parse CLI arguments and validate them.
      2. Fetch the current list of on-view objectIDs from the API.
      3. Reconcile the existing output CSV: remove rows for objects no longer
         on view so the file stays current.
      4. Determine which IDs still need to be fetched (not yet in the CSV).
      5. Fetch each missing object record from /objects/{id}, flatten it, and
         append it to the CSV immediately (crash-safe incremental writes).
      6. Emit periodic progress heartbeats and a final summary log line.

    Returns:
        0 on success (including "nothing to do" case).
        1 if the API returned no on-view IDs.
        2 if CLI argument validation failed.
    """
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

    # Configure the global color flag based on terminal capabilities and the
    # --no-color flag. Must be set before any log_event() calls below.
    global _COLOR_ENABLED
    _COLOR_ENABLED = supports_color() and not args.no_color

    # Ensure the output directory exists; create intermediate dirs as needed.
    args.out.parent.mkdir(parents=True, exist_ok=True)

    # --- Argument validation ---
    if args.rps > 80:
        # The Met's API terms ask for ≤80 req/s per IP; clamp silently with a warning.
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

    # Initialise the rate limiter and metrics accumulator for this run.
    limiter = RateLimiter(args.rps)
    metrics: dict[str, int] = {}
    run_start = time.monotonic()
    log_event(
        f"Start run: out={args.out}, rps_target={args.rps:.2f}, "
        f"progress_every={args.progress_every}, heartbeat_sec={args.heartbeat_sec:.1f}"
    )

    # Step 1: Get the current set of on-view objectIDs from the API.
    ids = fetch_on_view_ids(limiter)
    if not ids:
        log_event("No on-view IDs returned. Exiting.", "WARN")
        return 1

    # Build a set for O(1) membership checks during reconciliation.
    on_view_set = set(ids)

    # Step 2: Reconcile the existing CSV against the fresh on-view ID list.
    # `done` = IDs already written to the CSV and still valid (no need to re-fetch).
    # `fieldnames` = column order from the existing file (preserved for consistency).
    # `removed` = number of stale rows that were pruned.
    done, fieldnames, removed = reconcile_output_with_on_view_ids(args.out, on_view_set)
    if removed:
        log_event(
            f"Pruned {removed} stale rows not currently on view from {args.out}", "WARN"
        )

    # If --limit is set, truncate the ID list for a quick test run.
    if args.limit is not None:
        ids = ids[: args.limit]

    if done:
        log_event(f"Resume: {len(done)} IDs already in {args.out}")

    # Step 3: Build the work list — IDs that are on view but not yet in the CSV.
    todo = [oid for oid in ids if oid not in done]
    if not todo:
        log_event(
            "All current on-view IDs are already present in the CSV; no object records to fetch.",
            "SUCCESS",
        )
        return 0

    log_event(f"Missing current IDs to fetch: {len(todo)}")

    def write_row(row: dict) -> None:
        """Append a single flattened object record to the output CSV.

        On the very first write (file absent or empty) the header row is written
        first and the column order is locked in. Subsequent calls open the file
        in append mode so each row is persisted immediately — if the process is
        interrupted, already-written rows are not lost and the run can resume.

        Uses `nonlocal fieldnames` so the first call can initialise the column
        list from the keys of the first row when no prior CSV exists.
        """
        nonlocal fieldnames
        # If no prior CSV existed, derive column order from the first row's keys.
        if fieldnames is None:
            fieldnames = sorted(row.keys())
        # Determine whether to write a header: only when creating a new file.
        file_exists = args.out.exists() and args.out.stat().st_size > 0
        with args.out.open(
            "a" if file_exists else "w", newline="", encoding="utf-8"
        ) as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                w.writeheader()
            # Fill missing keys with empty strings to keep columns aligned.
            w.writerow({k: row.get(k, "") for k in fieldnames})

    # Counters for the final summary and progress heartbeats.
    n_ok = n_skip = n_fail = 0  # Successful writes, skipped, and failed fetches.
    n_skip_404 = n_skip_invalid = 0  # Breakdown of skip reasons.
    last_heartbeat = time.monotonic()
    total = len(todo)

    def emit_progress(force: bool = False) -> None:
        """Log a progress line if enough time has passed since the last one.

        Calculates throughput (rows/sec), estimated time remaining, and current
        limiter RPS, then delegates to log_event(). Skips the log if the
        heartbeat interval hasn't elapsed, unless `force=True` (used at
        progress_every milestones and at the end of the run).

        Args:
            force: If True, emit regardless of the heartbeat timer.
        """
        nonlocal last_heartbeat
        now = time.monotonic()
        # Respect the heartbeat interval unless forced.
        if not force and (now - last_heartbeat) < args.heartbeat_sec:
            return
        elapsed = max(1e-9, now - run_start)
        processed = n_ok + n_skip + n_fail
        rate = processed / elapsed
        remaining = max(0, total - processed)
        # Avoid division by zero if no rows have been processed yet.
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

    # Step 4: Main fetch loop — iterate over every ID that still needs fetching.
    for i, oid in enumerate(todo):
        try:
            data = fetch_json(f"{BASE}/objects/{oid}", limiter=limiter, metrics=metrics)
        except HTTPError as e:
            if e.code == 404:
                # Object ID is valid but the record doesn't exist in the API;
                # skip silently after the first few to avoid log spam.
                n_skip += 1
                n_skip_404 += 1
                if n_skip_404 <= 5:
                    log_event(f"Skip objectID {oid}: HTTP 404 not found", "WARN")
                emit_progress()
                continue
            # Non-404 HTTP error (e.g. 500); log and count as a failure.
            log_event(f"Error objectID {oid}: HTTP {e.code} - skipping", "ERROR")
            n_fail += 1
            emit_progress()
            continue
        except URLError as e:
            # Network-level failure after all retries; log and move on.
            log_event(f"Error objectID {oid}: network {e} - skipping", "ERROR")
            n_fail += 1
            emit_progress()
            continue

        # Sanity-check the response: it must be a dict containing objectID.
        # Malformed payloads are skipped with a warning (capped at 5 messages).
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

        # Successful fetch: notify the limiter so it can recover toward target RPS,
        # flatten the nested record, and append it to the CSV immediately.
        limiter.on_success()
        write_row(flatten(data))
        n_ok += 1

        # Emit a forced progress log every `progress_every` successful rows,
        # or a time-based heartbeat check on every other iteration.
        if n_ok % args.progress_every == 0:
            emit_progress(force=True)
        else:
            emit_progress()

    # Final forced progress log and summary line.
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
