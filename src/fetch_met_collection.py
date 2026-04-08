#!/usr/bin/env python3
"""
Fetch every object from the Met Collection API:
  1) GET /public/collection/v1/objects  → all objectIDs
  2) GET /public/collection/v1/objects/{id} → one record each

Writes CSV in chunks (nested list/dict fields → JSON strings). Default: append to
the CSV every ``--chunk`` new rows so a long run does not lose progress if it stops.

**Resume:** On start, reads every ``objectID`` already in ``--out`` and skips those IDs
(so you can re-run the same command; it continues where it left off).

**Direction:** ``--direction forward`` walks the current ID list from the beginning (default).
``--direction reverse`` walks from the end: with ``--limit N``, uses the **last N** IDs in that
list and fetches from the end of the window toward the start; without ``--limit``, reverses
the full list.

**Group:** ``--group`` is required: ``1``–``5`` or ``ALL``. For ``1``–``5``, object IDs come from
``--groups-csv`` (default ``data/processed/met_object_id_groups.csv``); ``forward`` / ``reverse``
/ ``--limit`` apply only within that group’s IDs (CSV row order). For ``ALL``, IDs come from the
API listing; direction/limit apply to the full list as before.

Rate: Met asks for at most ~80 requests per second; use ``--rps`` (default 75).
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
    row: dict = {}
    for k, v in obj.items():
        if isinstance(v, (list, dict)):
            row[k] = json.dumps(v, ensure_ascii=False) if v else ""
        elif v is None:
            row[k] = ""
        else:
            row[k] = v
    return row


def apply_direction_and_limit(
    ids: list[int],
    *,
    direction: str,
    limit: int | None,
) -> list[int]:
    """Slice and/or reverse ``ids`` (API order or group CSV order)."""
    if limit is not None:
        if direction == "reverse":
            return list(reversed(ids[-limit:]))
        return ids[:limit]
    if direction == "reverse":
        return list(reversed(ids))
    return ids


def load_object_ids_for_group(path: Path, group: int) -> list[int]:
    """Load object IDs for one group from split_met_object_ids CSV (preserves file order)."""
    if not path.exists():
        raise FileNotFoundError(f"Groups CSV not found: {path}")
    out: list[int] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "objectID" not in reader.fieldnames or "group" not in reader.fieldnames:
            raise ValueError(f"Groups CSV must have objectID and group columns: {path}")
        for row in reader:
            try:
                g = int(row["group"])
                oid = int(row["objectID"])
            except (KeyError, TypeError, ValueError):
                continue
            if g == group:
                out.append(oid)
    return out


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


def _parse_group_arg(value: str) -> int | str:
    t = value.strip().upper()
    if t == "ALL":
        return "ALL"
    try:
        n = int(t, 10)
    except ValueError as e:
        raise argparse.ArgumentTypeError("must be 1–5 or ALL") from e
    if n not in (1, 2, 3, 4, 5):
        raise argparse.ArgumentTypeError("numeric group must be 1, 2, 3, 4, or 5")
    return n


def main() -> int:
    p = argparse.ArgumentParser(description="Met Collection API → CSV (all objects)")
    p.add_argument(
        "--group",
        type=_parse_group_arg,
        required=True,
        help="Shard to fetch: 1–5 (uses --groups-csv) or ALL (full API object ID list)",
    )
    p.add_argument(
        "--groups-csv",
        type=Path,
        default=Path("data/processed/met_object_id_groups.csv"),
        help="objectID→group mapping; required for --group 1–5",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("data/processed/met_collection_api.csv"),
        help="Output CSV path",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="With forward: first N IDs in scope. With reverse: last N in scope (e.g. 10000)",
    )
    p.add_argument(
        "--direction",
        choices=("forward", "reverse"),
        default="forward",
        help="Within current scope (group or ALL): forward = start of list; reverse = end of list",
    )
    p.add_argument(
        "--chunk",
        type=int,
        default=100,
        metavar="N",
        help="Append to CSV every N new rows (checkpoint; default 100)",
    )
    p.add_argument(
        "--rps",
        type=float,
        default=75.0,
        metavar="N",
        help="Max requests per second (Met policy: ≤80; default 75 for safety)",
    )
    args = p.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    if args.rps > 80:
        print("Warning: --rps above 80 violates Met guidance; clamping to 80.", file=sys.stderr)
        args.rps = 80.0
    if args.rps <= 0:
        print("Error: --rps must be positive.", file=sys.stderr)
        return 2

    limiter = RateLimiter(args.rps)

    if args.group == "ALL":
        print("Fetching object ID list…", file=sys.stderr)
        listing = fetch_json(f"{BASE}/objects", limiter=limiter)
        ids: list[int] = listing["objectIDs"]
        print(f"  total in response: {len(ids)} (API total field: {listing.get('total')})", file=sys.stderr)
    else:
        gnum = args.group
        assert isinstance(gnum, int)
        try:
            ids = load_object_ids_for_group(args.groups_csv, gnum)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        if not ids:
            print(
                f"Error: no object IDs for group {gnum} in {args.groups_csv} (regenerate with split_met_object_ids.py).",
                file=sys.stderr,
            )
            return 2
        print(
            f"  group={gnum}  ·  loaded {len(ids)} IDs from {args.groups_csv} (API order within group)",
            file=sys.stderr,
        )

    ids = apply_direction_and_limit(ids, direction=args.direction, limit=args.limit)

    scope = "ALL" if args.group == "ALL" else str(args.group)
    print(
        f"  scope={scope}  direction={args.direction!r}  ·  will consider {len(ids)} IDs (before resume skips)",
        file=sys.stderr,
    )

    done, header_cols = existing_ids_and_columns(args.out)
    if done:
        print(f"Resume: {len(done)} IDs already in {args.out}", file=sys.stderr)

    fieldnames: list[str] | None = header_cols
    buffer: list[dict] = []

    def flush() -> None:
        nonlocal fieldnames, buffer
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

        row = flatten(data)
        if fieldnames is None:
            fieldnames = sorted(row.keys())
        buffer.append(row)
        n_ok += 1

        if len(buffer) >= args.chunk:
            flush()
            print(
                f"  checkpoint: wrote {args.chunk} rows to disk (total new this run: {n_ok}) → {args.out}",
                file=sys.stderr,
            )

    flush()
    print(
        f"Done. Wrote new rows: {n_ok}, skipped (resume/404/bad): {n_skip}, "
        f"failed HTTP/network (skipped): {n_fail}. Output: {args.out}",
        file=sys.stderr,
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())