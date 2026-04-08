#!/usr/bin/env python3
"""
Fetch all on-display objects from the Met Collection API.

Strategy:
  1) GET /search?isOnView=true&q=* → objectIDs currently on view
  2) GET /objects/{id}             → full record for each ID (serial, rate-limited)
  3) Append each row to CSV immediately as it's fetched; resume by skipping IDs already in output file.

Rate: Met asks for ≤80 req/s from a single IP. Default 75 req/s.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://collectionapi.metmuseum.org/public/collection/v1"

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MetOnViewFetcher/1.0; educational; "
        "+https://github.com/metmuseum/openaccess)"
    ),
    "Accept": "application/json",
}


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


def fetch_json(
    url: str,
    *,
    timeout: float = 120,
    limiter: RateLimiter | None = None,
    retries: int = 8,
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
                raise
            if e.code in (403, 429) and attempt + 1 < retries:
                wait = min(60.0, 2.0 * (2**attempt))
                print(
                    f"  HTTP {e.code} on attempt {attempt+1}, backing off {wait:.0f}s…",
                    file=sys.stderr,
                )
                time.sleep(wait)
                if limiter is not None:
                    limiter.on_403()
                    limiter.wait()
                continue
            raise
        except URLError:
            if attempt + 1 < retries:
                time.sleep(min(30.0, 1.0 * (2**attempt)))
                if limiter is not None:
                    limiter.wait()
                continue
            raise
    raise RuntimeError(f"Exhausted retries for {url}")


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


def existing_ids_and_columns(path: Path) -> tuple[set[int], list[str] | None]:
    if not path.exists() or path.stat().st_size == 0:
        return set(), None
    ids: set[int] = set()
    cols: list[str] | None = None
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "objectID" not in reader.fieldnames:
            return set(), None
        cols = list(reader.fieldnames)
        for row in reader:
            try:
                ids.add(int(row["objectID"]))
            except (TypeError, ValueError):
                pass
    return ids, cols


def fetch_on_view_ids(limiter: RateLimiter) -> list[int]:
    url = f"{BASE}/search?isOnView=true&q=*"
    print("Fetching on-view object IDs…", file=sys.stderr)
    try:
        data = fetch_json(url, limiter=limiter)
    except HTTPError:
        url = f"{BASE}/search?isOnView=true&q=%20"
        data = fetch_json(url, limiter=limiter)
    ids = data.get("objectIDs") or []
    print(
        f"  on-view IDs: {len(ids)} (API total: {data.get('total')})", file=sys.stderr
    )
    return ids


def main() -> int:
    p = argparse.ArgumentParser(
        description="Met Collection API → CSV (on-view objects only)"
    )
    p.add_argument("--out", type=Path, default=Path("data/processed/met_on_view.csv"))
    p.add_argument(
        "--limit", type=int, default=None, help="Only fetch first N IDs (test)"
    )
    p.add_argument(
        "--rps",
        type=float,
        default=75.0,
        metavar="N",
        help="Max requests per second (Met policy: ≤80; default 75)",
    )
    args = p.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    if args.rps > 80:
        print(
            "Warning: --rps above 80 violates Met guidance; clamping to 80.",
            file=sys.stderr,
        )
        args.rps = 80.0
    if args.rps <= 0:
        print("Error: --rps must be positive.", file=sys.stderr)
        return 2

    limiter = RateLimiter(args.rps)

    ids = fetch_on_view_ids(limiter)
    if not ids:
        print("No on-view IDs returned. Exiting.", file=sys.stderr)
        return 1

    if args.limit is not None:
        ids = ids[: args.limit]

    done, fieldnames = existing_ids_and_columns(args.out)
    if done:
        print(f"Resume: {len(done)} IDs already in {args.out}", file=sys.stderr)

    todo = [oid for oid in ids if oid not in done]
    print(f"IDs to fetch: {len(todo)}", file=sys.stderr)

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
    for i, oid in enumerate(todo):
        try:
            data = fetch_json(f"{BASE}/objects/{oid}", limiter=limiter)
        except HTTPError as e:
            if e.code == 404:
                n_skip += 1
                continue
            print(f"  error objectID {oid}: HTTP {e.code} — skipping", file=sys.stderr)
            n_fail += 1
            continue
        except URLError as e:
            print(f"  error objectID {oid}: network {e} — skipping", file=sys.stderr)
            n_fail += 1
            continue

        if not isinstance(data, dict) or "objectID" not in data:
            n_skip += 1
            continue

        limiter.on_success()
        write_row(flatten(data))
        n_ok += 1
        if n_ok % 100 == 0:
            print(f"  fetched {n_ok} rows…", file=sys.stderr)

    print(
        f"Done. New rows: {n_ok}, skipped: {n_skip}, failed: {n_fail}. Output: {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
