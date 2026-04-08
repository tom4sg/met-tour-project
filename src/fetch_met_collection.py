#!/usr/bin/env python3
"""
Fetch every object from the Met Collection API:
  1) GET /public/collection/v1/objects  → all objectIDs
  2) GET /public/collection/v1/objects/{id} → one record each

Writes CSV in chunks (nested list/dict fields → JSON strings). Resume: skips IDs
already present in the output file.

Rate: Met asks for at most ~80 requests per second; this script spaces requests evenly
(default 75/s) so bursts do not trip WAF (403). Use --rps to lower further if needed.
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

# Avoid Python-urllib default User-Agent; some CDNs return 403 for it.
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MetCollectionFetcher/1.0; educational; "
        "+https://github.com/metmuseum/openaccess)"
    ),
    "Accept": "application/json",
}


class RateLimiter:
    """Enforce a minimum interval between calls (max RPS = 1 / interval)."""

    def __init__(self, max_rps: float) -> None:
        self._min_interval = 1.0 / max_rps if max_rps > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        gap = self._last + self._min_interval - now
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()


def fetch_json(
    url: str,
    *,
    timeout: float = 120,
    limiter: RateLimiter | None = None,
    retries: int = 6,
) -> dict:
    """GET JSON with retries for rate limits (403/429), SSL handshake timeouts, and other transient network errors."""
    # Keep all API calls going through one helper so rate limiting and retries
    # behave the same for the ID-list request and each object detail request.
    if limiter is not None:
        limiter.wait()
    attempts = max(1, retries)
    for attempt in range(attempts):
        req = Request(url, headers=_HTTP_HEADERS)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            if e.code == 404:
                raise
            if e.code in (403, 429) and attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
                if limiter is not None:
                    limiter.wait()
                continue
            raise
        except URLError as e:
            # SSL handshake timeout, connection reset, etc. (HTTPError subclasses URLError — handled above)
            if attempt + 1 < attempts:
                time.sleep(min(30.0, 1.0 * (2**attempt)))
                if limiter is not None:
                    limiter.wait()
                continue
            raise


def flatten(obj: dict) -> dict:
    # CSV cells must be scalar values, so nested API fields are serialized to JSON.
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
    # Resume support: if the output CSV already exists, read the objectIDs we
    # have already written so the fetch loop can skip them.
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


def main() -> int:
    # CLI arguments control output path, whether to fetch only on-view objects,
    # optional sharding across multiple machines, and fetch/write pacing.
    p = argparse.ArgumentParser(description="Met Collection API → CSV (all objects)")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV path",
    )
    p.add_argument(
        "--on-view-only",
        action="store_true",
        help="Fetch only object IDs currently on view",
    )
    p.add_argument(
        "--part",
        type=int,
        default=None,
        help="1-indexed shard number to process from the fetched ID list",
    )
    p.add_argument(
        "--total-parts",
        type=int,
        default=None,
        help="Total number of shards to split the fetched ID list into",
    )
    p.add_argument("--limit", type=int, default=None, help="Only fetch first N IDs (test)")
    p.add_argument("--chunk", type=int, default=500, help="Flush to disk every N rows")
    p.add_argument(
        "--rps",
        type=float,
        default=75.0,
        metavar="N",
        help="Max requests per second (Met policy: ≤80; default 75 for safety)",
    )
    args = p.parse_args()
    out_explicit = args.out is not None

    # If the user does not provide --out, choose a default filename. Sharded
    # runs get a shard-specific filename so each laptop writes to a different CSV.
    if args.out is None:
        if args.part is not None and args.total_parts is not None:
            args.out = Path(
                f"data/processed/met_collection_api_part{args.part}of{args.total_parts}.csv"
            )
        else:
            args.out = Path("data/processed/met_collection_api.csv")
    args.out.parent.mkdir(parents=True, exist_ok=True)

    if args.rps > 80:
        print("Warning: --rps above 80 violates Met guidance; clamping to 80.", file=sys.stderr)
        args.rps = 80.0
    if args.rps <= 0:
        print("Error: --rps must be positive.", file=sys.stderr)
        return 2
    if (args.part is None) != (args.total_parts is None):
        print("Error: --part and --total-parts must be provided together.", file=sys.stderr)
        return 2
    if args.total_parts is not None and args.total_parts < 1:
        print("Error: --total-parts must be at least 1.", file=sys.stderr)
        return 2
    if args.part is not None and not (1 <= args.part <= args.total_parts):
        print("Error: --part must be between 1 and --total-parts.", file=sys.stderr)
        return 2

    # One limiter instance is reused for the whole run so requests stay evenly spaced.
    limiter = RateLimiter(args.rps)

    print("Fetching object ID list…", file=sys.stderr)
    listing_url = f"{BASE}/objects"
    if args.on_view_only:
        # Priority mode: ask the API for the smaller "currently on view" ID set.
        listing_url = f"{listing_url}?isOnView=true"
    listing = fetch_json(listing_url, limiter=limiter)
    ids: list[int] = listing["objectIDs"]
    print(f"  total in response: {len(ids)} (API total field: {listing.get('total')})", file=sys.stderr)

    if args.part is not None and args.total_parts is not None:
        # Split the fetched ID list into roughly equal contiguous slices.
        # Example with 5 parts:
        #   part 1 => [0 : 1/5 of list)
        #   part 2 => [1/5 : 2/5 of list)
        #   ...
        #
        # This is the section to change if you ever want a different sharding
        # strategy than the current "equal contiguous ranges" approach.
        start = ((args.part - 1) * len(ids)) // args.total_parts
        end = (args.part * len(ids)) // args.total_parts
        ids = ids[start:end]
        if not out_explicit:
            print(
                f"  processing part {args.part}/{args.total_parts}: indices [{start}:{end})",
                file=sys.stderr,
            )

    if args.limit is not None:
        # Optional testing shortcut after sharding: fetch only the first N IDs
        # from this run's assigned slice.
        ids = ids[: args.limit]

    done, header_cols = existing_ids_and_columns(args.out)
    if done:
        print(f"Resume: {len(done)} IDs already in {args.out}", file=sys.stderr)

    fieldnames: list[str] | None = header_cols
    buffer: list[dict] = []

    def flush() -> None:
        nonlocal fieldnames, buffer
        # Write buffered rows to disk in batches so the script does not keep
        # everything in memory and can resume from partial progress later.
        if not buffer:
            return
        if fieldnames is None:
            fieldnames = sorted(buffer[0].keys())
        file_exists = args.out.exists() and args.out.stat().st_size > 0
        mode = "a" if file_exists else "w"
        write_header = not file_exists
        with args.out.open(mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if write_header:
                w.writeheader()
            for row in buffer:
                w.writerow({k: row.get(k, "") for k in fieldnames})
        buffer.clear()

    n_ok = 0
    n_skip = 0
    n_fail = 0
    for i, oid in enumerate(ids):
        # Resume behavior: skip IDs already present in the current output CSV.
        if oid in done:
            n_skip += 1
            continue
        url = f"{BASE}/objects/{oid}"
        try:
            data = fetch_json(url, limiter=limiter)
        except HTTPError as e:
            if e.code == 404:
                n_skip += 1
                continue
            print(f"HTTP {e.code} for objectID {oid} after retries — skipping", file=sys.stderr)
            n_fail += 1
            continue
        except URLError as e:
            print(f"Network error for objectID {oid} after retries — skipping ({e})", file=sys.stderr)
            n_fail += 1
            continue

        if not isinstance(data, dict) or "objectID" not in data:
            n_skip += 1
            continue

        # Flatten the API payload into a one-row CSV record.
        row = flatten(data)
        if fieldnames is None:
            fieldnames = sorted(row.keys())
        buffer.append(row)
        n_ok += 1

        if len(buffer) >= args.chunk:
            # Periodic flush keeps the output file current during long runs.
            flush()
            print(f"  fetched {n_ok} new rows…", file=sys.stderr)

    flush()
    print(
        f"Done. Wrote new rows: {n_ok}, skipped (resume/404/bad): {n_skip}, "
        f"failed HTTP/network (skipped): {n_fail}. Output: {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
