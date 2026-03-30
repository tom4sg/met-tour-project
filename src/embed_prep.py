"""
Prepare Met collection rows for semantic search:

- **Text:** one string per object from titles, metadata, tags (for sentence-transformers).
- **Image:** load PIL image from `primaryImage` / `primaryImageSmall` (for CLIP).

Usage in a notebook::

    from embed_prep import build_embedding_text, load_image_for_row, image_url
    import pandas as pd

    df = pd.read_csv("data/processed/met_1k_api_test.csv")
    df["embed_text"] = df.apply(build_embedding_text, axis=1)
    img = load_image_for_row(df.iloc[0])
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Mapping
from urllib.request import Request, urlopen

from PIL import Image

# Column labels for the text blob (human-readable; helps the model disambiguate fields)
DEFAULT_TEXT_FIELDS: list[str] = [
    "title",
    "objectName",
    "department",
    "classification",
    "culture",
    "period",
    "dynasty",
    "medium",
    "objectDate",
    "artistDisplayName",
    "creditLine",
    "city",
    "state",
    "country",
    "region",
    "subregion",
    "geographyType",
    "dimensions",
    "repository",
]


def _is_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and not val.strip():
        return True
    try:
        import pandas as pd

        if pd.isna(val):
            return True
    except Exception:
        pass
    return False


def _tags_to_text(tags_val: Any) -> str | None:
    if _is_empty(tags_val):
        return None
    raw = tags_val
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw
    elif isinstance(raw, list):
        data = raw
    else:
        return None
    terms: list[str] = []
    for item in data:
        if isinstance(item, dict) and item.get("term"):
            terms.append(str(item["term"]))
        elif isinstance(item, str):
            terms.append(item)
    return ", ".join(terms) if terms else None


def _constituents_to_text(val: Any) -> str | None:
    if _is_empty(val):
        return None
    raw = val
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
    elif isinstance(raw, list):
        data = raw
    else:
        return None
    names: list[str] = []
    for item in data:
        if isinstance(item, dict) and item.get("name"):
            role = (item.get("role") or "").strip()
            name = str(item["name"]).strip()
            if role:
                names.append(f"{name} ({role})")
            else:
                names.append(name)
    return "; ".join(names) if names else None


def build_embedding_text(
    row: Mapping[str, Any],
    *,
    fields: list[str] | None = None,
    include_tags: bool = True,
    include_constituents: bool = True,
) -> str:
    """
    Build a single string for dense text embedding (e.g. sentence-transformers).

    Each non-empty field is a line ``fieldName: value`` so the model sees field
    context. Tags / constituents JSON from the API are flattened into text.
    """
    fields = fields or DEFAULT_TEXT_FIELDS
    parts: list[str] = []

    for key in fields:
        if key not in row:
            continue
        val = row[key]
        if _is_empty(val):
            continue
        parts.append(f"{key}: {str(val).strip()}")

    if include_constituents:
        c = _constituents_to_text(row.get("constituents"))
        if c:
            parts.append(f"constituents: {c}")

    if include_tags:
        t = _tags_to_text(row.get("tags"))
        if t:
            parts.append(f"tags: {t}")

    return "\n".join(parts) if parts else ""


def image_url(
    row: Mapping[str, Any],
    *,
    prefer: str = "primaryImageSmall",
) -> str | None:
    """
    Pick an image URL for CLIP / image embedding.

    Default uses ``primaryImageSmall`` (smaller download); falls back to
    ``primaryImage``.
    """
    keys = list(dict.fromkeys([prefer, "primaryImageSmall", "primaryImage"]))
    for key in keys:
        u = row.get(key)
        if not _is_empty(u):
            return str(u).strip()
    return None


def load_pil_image(url: str, *, timeout: float = 60.0) -> Image.Image | None:
    """Download image and return RGB PIL image, or None on failure."""
    if not url or not str(url).strip():
        return None
    req = Request(
        url.strip(),
        headers={"User-Agent": "Mozilla/5.0 (compatible; MetEmbed/1.0)"},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        im = Image.open(BytesIO(data)).convert("RGB")
        return im
    except Exception:
        return None


def load_image_for_row(
    row: Mapping[str, Any],
    *,
    prefer: str = "primaryImageSmall",
    timeout: float = 60.0,
) -> Image.Image | None:
    """Resolve URL from row and load image for CLIP."""
    url = image_url(row, prefer=prefer)
    if not url:
        return None
    return load_pil_image(url, timeout=timeout)


def add_embedding_text_column(df: Any, *, column: str = "embed_text") -> Any:
    """``df[column] = df.apply(build_embedding_text, axis=1)`` — returns df for chaining."""
    df = df.copy()
    df[column] = df.apply(lambda r: build_embedding_text(r), axis=1)
    return df
