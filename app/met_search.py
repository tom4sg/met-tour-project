"""
Local Streamlit UI: search Met collection by text embedding (MiniLM) and CLIP.

Run from project root:
  streamlit run app/met_search.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import requests
import pandas as pd
import streamlit as st
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import CLIPModel, CLIPProcessor

# project root = parent of app/
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.embed_prep import load_pil_image  # noqa: E402

TEXT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"
DEFAULT_CSV = ROOT / "data/processed/embeddings.csv"
MET_OBJECT_API = "https://collectionapi.metmuseum.org/public/collection/v1/objects"

DISPLAY_COLS = [
    "objectID",
    "title",
    "objectName",
    "department",
    "classification",
    "culture",
    "medium",
    "objectDate",
    "artistDisplayName",
    "creditLine",
    "city",
    "country",
    "objectURL",
]

TOUR_CARD_COLS = [
    "title",
    "artistDisplayName",
    "objectDate",
    "medium",
    "culture",
    "period",
    "department",
    "objectURL",
]


def parse_embedding_str(val) -> np.ndarray | None:
    """Parse numpy-printed vector stored in CSV (multiline allowed)."""
    if pd.isna(val):
        return None
    t = str(val).strip()
    if not t or t.lower() == "nan":
        return None
    t = t.replace("[", "").replace("]", "").replace("\n", " ")
    try:
        arr = np.fromstring(t, sep=" ")
    except Exception:
        return None
    if arr.size == 0:
        return None
    if not np.isfinite(arr).all():
        return None
    return arr.astype(np.float64)


@st.cache_resource(show_spinner="Loading models…")
def load_models():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    text_model = SentenceTransformer(TEXT_MODEL_NAME)
    clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME).to(device).eval()
    clip_proc = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
    return text_model, clip_model, clip_proc, device


@st.cache_data(show_spinner="Loading embeddings table…")
def load_embedding_matrix(csv_path: str):
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    if "text_embedding" not in df.columns:
        raise ValueError("CSV must contain a column 'text_embedding'")
    if "clip_embedding" not in df.columns:
        raise ValueError("CSV must contain a column 'clip_embedding'")

    n = len(df)
    text_rows: list[np.ndarray] = []
    clip_rows: list[np.ndarray | None] = []
    text_ok = np.zeros(n, dtype=bool)

    for i in range(n):
        te = parse_embedding_str(df["text_embedding"].iloc[i])
        if te is not None:
            text_rows.append(te)
            text_ok[i] = True
        else:
            text_rows.append(np.zeros(384, dtype=np.float64))

        ce = parse_embedding_str(df["clip_embedding"].iloc[i])
        clip_rows.append(ce)

    text_mat = np.stack(text_rows)
    # L2-normalize rows (safe for zero rows)
    t_norm = np.linalg.norm(text_mat, axis=1, keepdims=True)
    t_norm = np.maximum(t_norm, 1e-12)
    text_mat = text_mat / t_norm

    clip_dim = 512
    clip_mat = np.full((n, clip_dim), np.nan, dtype=np.float64)
    clip_ok = np.zeros(n, dtype=bool)
    for i, ce in enumerate(clip_rows):
        if ce is not None and ce.shape[0] == clip_dim:
            clip_mat[i] = ce
            clip_ok[i] = True
    c_norm = np.linalg.norm(clip_mat, axis=1, keepdims=True)
    c_norm = np.maximum(c_norm, 1e-12)
    clip_mat = np.where(clip_ok[:, None], clip_mat / c_norm, np.nan)

    return df, text_mat, clip_mat, text_ok, clip_ok


def encode_query_text(text_model: SentenceTransformer, q: str) -> np.ndarray:
    v = text_model.encode([q], convert_to_numpy=True)[0].astype(np.float64)
    v = v / max(np.linalg.norm(v), 1e-12)
    return v


def encode_query_clip(clip_model, clip_proc, device: str, q: str) -> np.ndarray:
    inputs = clip_proc(text=[q], return_tensors="pt", padding=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        t = clip_model.get_text_features(**inputs)
    t = t / t.norm(dim=-1, keepdim=True)
    return t.cpu().numpy().squeeze(0)


def top_k_indices(sim: np.ndarray, k: int = 5) -> np.ndarray:
    k = min(k, len(sim))
    return np.argsort(-sim)[:k]


def _image_url_from_row(row: pd.Series) -> str | None:
    """Resolve Met image URL; handle NaN / bad types from CSV."""
    for key in ("primaryImageSmall", "primaryImage"):
        if key not in row.index:
            continue
        v = row[key]
        if pd.isna(v):
            continue
        s = str(v).strip()
        if not s or s.lower() == "nan":
            continue
        if s.startswith("http"):
            return s
    return None


@st.cache_data(ttl=3600, max_entries=5000)
def _fetch_met_image_urls_from_api(object_id: int) -> tuple[str | None, str | None]:
    """
    When CSV has no image columns, Met API still returns primaryImage URLs for many objects.
    Cached per objectID to avoid repeat calls.
    """
    try:
        oid = int(object_id)
    except (TypeError, ValueError):
        return None, None
    url = f"{MET_OBJECT_API}/{oid}"
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MetOpenAccessSearch/1.0)",
                "Accept": "application/json",
            },
            timeout=45,
        )
        if r.status_code != 200:
            return None, None
        data: Any = r.json()
    except Exception:
        return None, None
    if not isinstance(data, dict) or "objectID" not in data:
        return None, None
    sm = data.get("primaryImageSmall") or ""
    lg = data.get("primaryImage") or ""
    sm = sm.strip() if isinstance(sm, str) else ""
    lg = lg.strip() if isinstance(lg, str) else ""
    small = sm if sm.startswith("http") else None
    full = lg if lg.startswith("http") else None
    return small, full


def _resolve_image_url(row: pd.Series) -> str | None:
    """Prefer CSV; if missing, ask Met Collection API by objectID."""
    u = _image_url_from_row(row)
    if u:
        return u
    oid = row.get("objectID")
    if pd.isna(oid):
        return None
    try:
        oid_int = int(oid)
    except (TypeError, ValueError):
        return None
    small, full = _fetch_met_image_urls_from_api(oid_int)
    return small or full


def _display_met_image(url: str) -> None:
    """Load Met CDN images with browser-like headers (403 without Referer/UA on some networks)."""
    im = load_pil_image(url, timeout=90)
    if im is not None:
        im.thumbnail((480, 480))
        st.image(im, use_container_width=True)
    else:
        # Fallback: Streamlit can fetch some URLs directly (different HTTP stack)
        try:
            st.image(url, use_container_width=True)
        except Exception:
            st.caption("Image failed to load — check network or URL.")


def _as_department(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "Unknown department"
    s = str(value).strip()
    return s if s else "Unknown department"

def _gallery_number_from_row(row: pd.Series) -> int | None:
    """
    Try to extract a numeric gallery number from either `GalleryNumber` (API-style)
    or `galleryNumber` (bulk-style).
    """
    for key in ("GalleryNumber", "galleryNumber"):
        if key not in row.index:
            continue
        v = row.get(key)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        s = str(v).strip()
        if not s or s.lower() == "nan":
            continue
        try:
            return int(float(s))
        except (TypeError, ValueError):
            continue
    return None


def _as_gallery_label(g: int | None) -> str:
    return f"Gallery {g}" if g is not None else "Gallery unknown"


def _order_galleries(gallery_numbers: list[int | None]) -> list[int | None]:
    # numeric galleries first, then unknown
    uniq = list(dict.fromkeys(gallery_numbers))
    known = sorted([g for g in uniq if isinstance(g, int)])
    unknown = [g for g in uniq if g is None]
    return known + unknown


def _tour_department_order_template() -> list[str]:
    """
    A user-editable template. This is NOT a real floorplan order; it's a clean
    "walking order" you can customize based on how you want to tour The Met.
    """
    return [
        "The American Wing",
        "European Paintings",
        "European Sculpture and Decorative Arts",
        "Modern Art",
        "Asian Art",
        "Islamic Art",
        "Egyptian Art",
        "Greek and Roman Art",
        "Arms and Armor",
        "Drawings and Prints",
        "Photographs",
        "The Costume Institute",
        "The Robert Lehman Collection",
        "Arts of Africa, Oceania, and the Americas",
        "Ancient Near Eastern Art",
        "The Cloisters",
        "The Libraries",
        "Musical Instruments",
    ]


def _order_departments(depts: list[str], preferred_order: list[str]) -> list[str]:
    pref_index = {d: i for i, d in enumerate(preferred_order)}
    return sorted(
        set(depts),
        key=lambda d: (0, pref_index[d]) if d in pref_index else (1, d.lower()),
    )


def _graphviz_tour_path(departments: list[str]) -> str:
    """Graphviz DOT for a simple directed path through departments."""
    nodes = ["Start"] + list(departments) + ["End"]
    lines = [
        "digraph tour {",
        '  rankdir="LR";',
        "  node [shape=box, style=rounded];",
    ]
    for n in nodes:
        label = n.replace('"', '\\"')
        lines.append(f'  "{label}";')
    for a, b in zip(nodes[:-1], nodes[1:]):
        a_l = a.replace('"', '\\"')
        b_l = b.replace('"', '\\"')
        lines.append(f'  "{a_l}" -> "{b_l}";')
    lines.append("}")
    return "\n".join(lines)


def _render_stop_card(row: pd.Series, *, similarity: float) -> None:
    title = str(row.get("title", "")).strip()
    oid = row.get("objectID", "")
    dept = _as_department(row.get("department"))
    header = title if title else f"objectID {oid}"

    with st.expander(f"{header}  ·  sim={similarity:.4f}  ·  {dept}", expanded=False):
        cols = st.columns([1, 2])
        with cols[0]:
            url = _resolve_image_url(row)
            if url:
                _display_met_image(url)
        with cols[1]:
            for c in TOUR_CARD_COLS:
                if c not in row.index:
                    continue
                v = row.get(c)
                if pd.notna(v) and str(v).strip() != "":
                    st.markdown(f"**{c}:** {v}")
            # Also show gallery number(s) when present
            for key in ("GalleryNumber", "galleryNumber"):
                if key in row.index:
                    v = row.get(key)
                    if pd.notna(v) and str(v).strip() != "":
                        st.markdown(f"**{key}:** {v}")


def show_results(df: pd.DataFrame, indices: np.ndarray, sims: np.ndarray, title: str) -> None:
    st.subheader(title)
    for rank, idx in enumerate(indices, start=1):
        row = df.iloc[int(idx)]
        st.markdown(f"**#{rank}** · similarity **{float(sims[int(idx)]):.4f}** · objectID **{row.get('objectID', '')}**")
        cols = st.columns([1, 2])
        with cols[0]:
            url = _resolve_image_url(row)
            if url:
                _display_met_image(url)
            else:
                st.caption("No image URL (CSV + Met API had none for this object)")
        with cols[1]:
            for c in DISPLAY_COLS:
                if c not in df.columns:
                    continue
                v = row.get(c)
                if pd.notna(v) and str(v).strip() != "":
                    st.markdown(f"**{c}:** {v}")
        st.divider()


def main() -> None:
    st.set_page_config(page_title="Met collection search", layout="wide")
    st.title("Met collection · search + tour")

    csv_default = str(DEFAULT_CSV)
    csv_path = st.sidebar.text_input("embeddings.csv path", value=csv_default)

    try:
        df, text_mat, clip_mat, text_ok, clip_ok = load_embedding_matrix(csv_path)
    except Exception as e:
        st.error(f"Could not load CSV: {e}")
        st.stop()

    st.sidebar.caption(f"Rows: **{len(df):,}** · text OK: **{text_ok.sum():,}** · CLIP OK: **{clip_ok.sum():,}**")

    with st.form("search_form"):
        q = st.text_input("Search", placeholder='e.g. pastel golden paintings', value="")
        k = st.number_input("Top K", min_value=1, max_value=50, value=5, step=1)
        submitted = st.form_submit_button("Search")

    if not submitted:
        st.stop()
    if not q.strip():
        st.warning("Enter a query.")
        st.stop()

    text_model, clip_model, clip_proc, device = load_models()

    with st.spinner("Embedding query…"):
        q_text = encode_query_text(text_model, q.strip())
        q_clip = encode_query_clip(clip_model, clip_proc, device, q.strip())

    sim_text = np.full(len(df), -np.inf, dtype=np.float64)
    sim_text[text_ok] = text_mat[text_ok] @ q_text

    sim_clip = np.full(len(df), -np.inf, dtype=np.float64)
    sim_clip[clip_ok] = np.nansum(clip_mat[clip_ok] * q_clip, axis=1)

    idx_text = top_k_indices(sim_text, int(k))
    idx_clip = top_k_indices(sim_clip, int(k))

    tab_search, tab_tour = st.tabs(["Search results", "Tour (by department)"])

    with tab_search:
        with st.expander("What attributes are used for search?", expanded=False):
            st.markdown("**Text ranking (sentence-transformers)**")
            st.markdown(
                "- Query is embedded with `" + TEXT_MODEL_NAME + "`\n"
                "- Ranked against precomputed column `text_embedding`\n"
                "- The *content* that was embedded is stored in column `embed_text` (if present)."
            )

            st.markdown("**Image ranking (CLIP)**")
            st.markdown(
                "- Query text is embedded with `" + CLIP_MODEL_NAME + "` (CLIP text encoder)\n"
                "- Ranked against precomputed column `clip_embedding` (image vectors)."
            )

            st.markdown("**Images shown in results**")
            st.markdown("- Prefer `primaryImageSmall`, fall back to `primaryImage`, else fetch via Met API by `objectID`.")

            st.markdown("**Metadata shown in result cards**")
            st.code(", ".join(DISPLAY_COLS))

            if "embed_text" in df.columns:
                st.markdown("**Preview the embedded text (`embed_text`) for the current results**")
                st.caption("This is the exact text blob your `text_embedding` vectors came from.")
                preview_n = st.number_input("How many to preview", min_value=1, max_value=int(k), value=min(3, int(k)), step=1)
                for j in range(int(preview_n)):
                    r = df.iloc[int(idx_text[j])]
                    oid = r.get("objectID", "")
                    title = str(r.get("title", "")).strip()
                    with st.expander(f"embed_text · objectID {oid} · {title[:60]}", expanded=False):
                        st.text(str(r.get("embed_text", "")))
            else:
                st.caption("Column `embed_text` is not present in this CSV, so the app can’t show what text was embedded.")

        c1, c2 = st.columns(2)
        with c1:
            show_results(df, idx_text, sim_text, "Top · sentence-transformers (text embedding index)")
        with c2:
            show_results(df, idx_clip, sim_clip, "Top · CLIP (text query vs image embeddings)")

    with tab_tour:
        st.markdown(
            "This is a **schematic tour** built from search results grouped by **department** "
            "(`department`). It’s not a true floorplan; the route is based on a user-editable "
            "walking order list."
        )

        default_order = "\n".join(_tour_department_order_template())
        dept_order_text = st.sidebar.text_area(
            "Tour walking order (one department per line)",
            value=default_order,
            height=240,
        )
        preferred = [line.strip() for line in dept_order_text.splitlines() if line.strip()]

        per_group = st.sidebar.number_input("Max stops per department", min_value=1, max_value=10, value=3, step=1)
        probe = st.sidebar.number_input(
            "Candidate pool per ranker (top-N)",
            min_value=max(int(k), 5),
            max_value=200,
            value=max(int(k), 25),
            step=5,
        )

        cand_text = top_k_indices(sim_text, int(probe))
        cand_clip = top_k_indices(sim_clip, int(probe))
        cand_idx = list(dict.fromkeys([*map(int, cand_text), *map(int, cand_clip)]))

        cand_df = df.iloc[cand_idx].copy()
        cand_df["_sim_text"] = sim_text[cand_idx]
        cand_df["_sim_clip"] = sim_clip[cand_idx]
        if "department" in cand_df.columns:
            cand_df["_department"] = cand_df["department"].apply(_as_department)
        else:
            cand_df["_department"] = "Unknown department"
        cand_df["_best_sim"] = np.maximum(cand_df["_sim_text"].values, cand_df["_sim_clip"].values)

        departments_all = _order_departments(cand_df["_department"].tolist(), preferred)
        chosen = st.sidebar.multiselect(
            "Departments to include",
            options=departments_all,
            default=departments_all,
        )
        departments = [d for d in departments_all if d in set(chosen)]
        st.graphviz_chart(_graphviz_tour_path(departments), use_container_width=True)

        st.subheader("Recommended stops (grouped by department)")
        for dept in departments:
            dsub = (
                cand_df[cand_df["_department"] == dept]
                .sort_values("_best_sim", ascending=False)
                .head(int(per_group))
            )
            if dsub.empty:
                continue
            st.markdown(f"### {dept}  ·  {len(dsub)} stop(s)")
            for _, row in dsub.iterrows():
                _render_stop_card(row, similarity=float(row["_best_sim"]))


if __name__ == "__main__":
    main()
