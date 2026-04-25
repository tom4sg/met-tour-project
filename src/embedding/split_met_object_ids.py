#!/usr/bin/env python3
"""
Fetch the Met Collection object ID list (one GET) and assign each ID to a group
so teammates can split work without overlapping.

Groups are **contiguous slices** of the API order: group 1 = first ~1/k of the list,
group 2 = next slice, etc. Sizes differ by at most one when the count is not divisible by k.

Writes CSV columns: objectID, group (1 .. --groups).

Example:
  python src/split_met_object_ids.py --out data/processed/met_object_id_groups.csv
  # Member 3: filter rows where group == 3, or grep / pandas on that CSV.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

# Allow `python src/split_met_object_ids.py` from repo root
from src.embedding.fetch_met_collection import BASE, RateLimiter, fetch_json


def chunk_sizes(n: int, parts: int) -> list[int]:
    """Split n items into `parts` contiguous chunks; sizes differ by at most 1."""
    if parts <= 0:
        raise ValueError("parts must be positive")
    if n == 0:
        return [0] * parts
    base, rem = divmod(n, parts)
    return [base + (1 if i < rem else 0) for i in range(parts)]


def assign_groups(ids: list[int], groups: int) -> tuple[list[tuple[int, int]], dict]:
    """
    Map each object ID to a group index 1..groups (API list order preserved within CSV).
    Returns (rows, summary dict).
    """
    n = len(ids)
    sizes = chunk_sizes(n, groups)
    rows: list[tuple[int, int]] = []
    offset = 0
    counts: dict[str, int] = {}
    for g in range(groups):
        sz = sizes[g]
        gid = g + 1
        counts[f"group_{gid}"] = sz
        for j in range(sz):
            rows.append((ids[offset + j], gid))
        offset += sz
    summary = {
        "total_object_ids": n,
        "num_groups": groups,
        "chunk_sizes": sizes,
        "counts_by_group": counts,
        "api_total_field": None,  # filled by caller from listing JSON
    }
    return rows, summary


def main() -> int:
    p = argparse.ArgumentParser(description="Met object IDs → CSV with group assignment (split work across teammates)")
    p.add_argument(
        "--out",
        type=Path,
        default=Path("data/processed/met_object_id_groups.csv"),
        help="Output CSV path (objectID, group)",
    )
    p.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Optional JSON path for counts and chunk sizes (default: <out-stem>_summary.json)",
    )
    p.add_argument("--groups", type=int, default=5, metavar="K", help="Number of groups (default 5)")
    p.add_argument(
        "--rps",
        type=float,
        default=75.0,
        help="Rate limiter for the single listing request (default 75)",
    )
    args = p.parse_args()

    if args.groups < 1:
        print("Error: --groups must be at least 1.", file=sys.stderr)
        return 2
    if args.rps > 80:
        print("Warning: --rps above 80; clamping to 80.", file=sys.stderr)
        args.rps = 80.0
    if args.rps <= 0:
        print("Error: --rps must be positive.", file=sys.stderr)
        return 2

    limiter = RateLimiter(args.rps)
    print("Fetching object ID list…", file=sys.stderr)
    listing = fetch_json(f"{BASE}/objects", limiter=limiter)
    ids: list[int] = listing["objectIDs"]
    api_total = listing.get("total")
    print(f"  total in response: {len(ids)} (API total field: {api_total})", file=sys.stderr)

    rows, summary = assign_groups(ids, args.groups)
    summary["api_total_field"] = api_total

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["objectID", "group"])
        w.writerows(rows)

    summary_path = args.summary
    if summary_path is None:
        summary_path = args.out.with_name(args.out.stem + "_summary.json")
    with summary_path.open("w", encoding="utf-8") as sf:
        json.dump(summary, sf, indent=2)

    print(f"Wrote {len(rows)} rows → {args.out}", file=sys.stderr)
    print(f"Summary → {summary_path}", file=sys.stderr)
    for g in range(1, args.groups + 1):
        print(f"  group {g}: {summary['counts_by_group'].get(f'group_{g}', 0)} IDs", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
