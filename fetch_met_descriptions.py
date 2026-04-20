from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag
from tqdm import tqdm

INPUT_CSV = Path("data/processed/df_onview_toembed.csv")
OUTPUT_CSV = Path("data/met_descriptions.csv")
CHECKPOINT_EVERY = 500
REQUEST_DELAY = 0.3
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (research project)"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch curatorial descriptions from Met object pages.",
    )
    parser.add_argument(
        "--object-ids",
        nargs="+",
        type=int,
        help="Optional list of objectIDs to fetch, useful for a small test run.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY,
        help=f"Delay between requests in seconds. Default: {REQUEST_DELAY}",
    )
    return parser.parse_args()


def load_source_dataframe(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {path}")

    df = pd.read_csv(path)
    required_columns = {"objectID", "objectURL"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    columns = ["objectID", "objectURL"]
    if "met_description" in df.columns:
        columns.append("met_description")

    df = df.loc[:, columns].copy()
    df["objectID"] = pd.to_numeric(df["objectID"], errors="raise").astype(int)

    if "met_description" not in df.columns:
        df["met_description"] = pd.Series([pd.NA] * len(df), dtype="object")
    else:
        df["met_description"] = df["met_description"].astype(object)

    return df


def clean_text(text: str) -> str:
    return " ".join(text.split())


def iter_paragraphs_before_artwork_details(soup: BeautifulSoup) -> Iterable[str]:
    artwork_details = soup.find("h2", string=lambda s: s and "Artwork Details" in s)
    if artwork_details is None:
        return []

    candidates: list[str] = []
    root = soup.body or soup
    for node in root.descendants:
        if node is artwork_details:
            break
        if isinstance(node, Tag) and node.name == "p":
            text = clean_text(node.get_text(" ", strip=True))
            if text:
                candidates.append(text)
    return candidates


def is_valid_description(text: str) -> bool:
    return len(text) > 50 and not text.startswith("Skip") and "©" not in text


def iter_overview_text_candidates(soup: BeautifulSoup) -> Iterable[str]:
    main = soup.find("main", attrs={"data-testid": "object-page-top-main-el"})
    if main is None:
        return []

    candidates: list[str] = []
    for tag in main.find_all(["p", "div"]):
        if tag.find(["p", "div"]):
            continue
        text = clean_text(tag.get_text(" ", strip=True))
        if text:
            candidates.append(text)
    return candidates


def fetch_met_description(object_url: str, delay: float) -> str | None:
    try:
        response = requests.get(
            object_url,
            headers=REQUEST_HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup.select("nav, footer, .related, #feedback, .slider"):
            tag.decompose()

        for text in iter_overview_text_candidates(soup):
            if is_valid_description(text):
                return text

        for text in iter_paragraphs_before_artwork_details(soup):
            if is_valid_description(text):
                return text
        return None
    finally:
        time.sleep(delay)


def checkpoint(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def export_descriptions(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.loc[:, ["objectID", "met_description"]].to_csv(path, index=False)


def main() -> None:
    args = parse_args()
    df = load_source_dataframe(INPUT_CSV)

    if args.object_ids:
        requested_ids = set(args.object_ids)
        matching_mask = df["objectID"].isin(requested_ids)
        if not matching_mask.any():
            raise ValueError("None of the requested objectIDs were found in the input CSV.")
        pending_mask = matching_mask
    else:
        pending_mask = df["met_description"].isna()

    pending_indices = df.index[pending_mask].tolist()

    processed_in_run = 0
    for idx in tqdm(pending_indices, desc="Fetching Met descriptions"):
        object_id = int(df.at[idx, "objectID"])
        object_url = df.at[idx, "objectURL"]

        try:
            description = fetch_met_description(object_url, delay=args.delay)
        except Exception as exc:
            print(f"Error fetching objectID {object_id}: {exc}", file=sys.stderr)
            description = None

        df.at[idx, "met_description"] = description
        processed_in_run += 1

        if processed_in_run % CHECKPOINT_EVERY == 0:
            checkpoint(df, INPUT_CSV)
            export_descriptions(df, OUTPUT_CSV)

    checkpoint(df, INPUT_CSV)
    export_descriptions(df, OUTPUT_CSV)

    summary_df = df[df["objectID"].isin(args.object_ids)].copy() if args.object_ids else df
    total_rows = len(summary_df)
    descriptions_found = int(summary_df["met_description"].notna().sum())
    descriptions_missing = total_rows - descriptions_found

    print(f"Total fetched this run: {processed_in_run}")
    print(f"Rows in output: {total_rows}")
    print(f"Descriptions found: {descriptions_found}")
    print(f"Descriptions missing (None): {descriptions_missing}")


if __name__ == "__main__":
    main()
