"""
Met Museum semantic search + tour routing.

Run from project root:
    streamlit run app/met_search.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.embedding.embed_prep import load_pil_image
from src.search.met_tour_routing import FLOOR_PENALTY, build_tour, get_coords, group_by_stop
from src.search.query_cluster import assign_cluster, embed_query, load_gmm
from src.search.retrieval import cosine_search

CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"
TEXT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
GMM_DIR = ROOT / "embeddings/metart"
EMBEDDINGS_PATH = ROOT / "embeddings/metart/joint_embeddings.npy"
METADATA_PATH = ROOT / "data/processed/metadata.csv"

DISPLAY_FIELDS = [
    "objectName",
    "artistDisplayName",
    "medium",
    "objectBeginDate",
    "objectEndDate",
    "department",
    "culture",
    "country",
    "classification",
    "isHighlight_converted",
    "isPublicDomain_converted",
    "parsedTags",
    "met_description",
    "embed_text",
    "objectURL",
]


# ── Cached resources ──────────────────────────────────────────────────────────

@st.cache_resource(show_spinner="Loading CLIP model...")
def _load_clip():
    import torch
    from transformers import AutoProcessor, CLIPModel
    device = "cuda" if torch.cuda.is_available() else ("mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu")
    model = CLIPModel.from_pretrained(CLIP_MODEL_NAME).eval().to(device)
    processor = AutoProcessor.from_pretrained(CLIP_MODEL_NAME)
    return model, processor, device


@st.cache_resource(show_spinner="Loading text model...")
def _load_text_model():
    import torch
    from sentence_transformers import SentenceTransformer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(TEXT_MODEL_NAME, device=device)


@st.cache_resource(show_spinner="Loading GMM...")
def _load_gmm():
    return load_gmm(GMM_DIR, space="joint")


@st.cache_resource(show_spinner="Loading embeddings...")
def _load_embeddings():
    return np.load(EMBEDDINGS_PATH).astype(np.float32)


@st.cache_resource(show_spinner="Loading cluster index...")
def _load_cluster_indices():
    with open(GMM_DIR / "gmm_joint_indices.json") as f:
        return json.load(f)


@st.cache_data(show_spinner="Loading metadata...")
def _load_metadata():
    return pd.read_csv(METADATA_PATH)


# ── Image display ─────────────────────────────────────────────────────────────

def _show_image(row: dict) -> None:
    url = row.get("primaryImageSmall") or row.get("primaryImage") or row.get("embed_image_url")
    if not url or str(url) == "nan":
        st.caption("No image")
        return
    im = load_pil_image(str(url), timeout=15)
    if im:
        im.thumbnail((400, 400))
        st.image(im, use_container_width=True)
    else:
        st.caption("Image failed to load")


# ── Main app ──────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="Met Museum Search", layout="wide")
    st.title("Met Museum · Semantic Search + Tour")

    with st.sidebar:
        st.header("Search settings")
        top_clusters = st.slider("Clusters to search", 1, 5, 2)
        top_k = st.slider("Results to return", 5, 30, 10)
        clip_weight = st.slider("CLIP weight", 0.0, 2.0, 1.0, 0.1)
        text_weight = st.slider("Text weight", 0.0, 2.0, 1.0, 0.1)

    query = st.text_input("Search the Met collection", placeholder="e.g. portrait of a woman in blue")

    if not query.strip():
        st.stop()

    clip_model, clip_proc, device = _load_clip()
    st_model = _load_text_model()

    with st.spinner("Embedding query..."):
        query_vec = embed_query(
            query.strip(),
            clip_weight=clip_weight,
            text_weight=text_weight,
            clip_model=clip_model,
            clip_processor=clip_proc,
            text_model=st_model,
            device=device,
        )

    gmm = _load_gmm()
    clusters = assign_cluster(query_vec, gmm, top_k=top_clusters)
    cluster_indices = _load_cluster_indices()
    joint_embeddings = _load_embeddings()
    metadata = _load_metadata()

    candidate_pool: list[int] = []
    for cluster_id, _ in clusters:
        candidate_pool.extend(cluster_indices[str(cluster_id)])

    results = cosine_search(query_vec, joint_embeddings, candidate_pool, top_k=top_k)

    # Build artwork dicts for routing
    artworks: list[dict] = []
    for idx, score in results:
        art = metadata.iloc[idx].to_dict()
        art["_score"] = score
        art["_index"] = idx
        artworks.append(art)

    tour = group_by_stop(artworks)

    # Cluster info
    with st.expander("Cluster assignment", expanded=False):
        for cluster_id, prob in clusters:
            size = len(cluster_indices[str(cluster_id)])
            st.write(f"Cluster **{cluster_id}** — p={prob:.4f} — {size} artworks")

    st.markdown(f"### Tour route · {len(artworks)} artworks across {len(tour)} stop(s)")

    tab_visual, tab_itinerary = st.tabs(["Visual tour", "Itinerary"])

    with tab_itinerary:
        routed = build_tour(artworks)
        lines = ["  MET MUSEUM TOUR ROUTE", "  " + "=" * 58]
        for i, art in enumerate(routed, 1):
            loc = str(art.get("GalleryNumber", "")).strip() or art.get("department") or "?"
            coords = get_coords(art)
            floor = int(coords[2] // FLOOR_PENALTY)
            title = art.get("title", "Untitled")
            lines.append(f"\n  {i:2}.  {title}")
            lines.append(f"       Gallery {loc}  •  Floor {floor}")
        st.code("\n".join(lines), language=None)

    with tab_visual:
        for location, stop_artworks in tour.items():
            st.markdown(f"## {location}")
            for art in stop_artworks:
                title = str(art.get("title", "Untitled"))
                score = art.get("_score", 0.0)
                artist = str(art.get("artistDisplayName", ""))
                label = f"**{title}**" + (f" · {artist}" if artist and artist != "nan" else "") + f"  ·  sim={score:.4f}"
                with st.expander(label, expanded=False):
                    cols = st.columns([1, 2])
                    with cols[0]:
                        _show_image(art)
                    with cols[1]:
                        for field in DISPLAY_FIELDS:
                            val = art.get(field)
                            if val and str(val) != "nan":
                                if field == "objectURL":
                                    st.markdown(f"[Met page]({val})")
                                else:
                                    st.markdown(f"**{field}:** {val}")


if __name__ == "__main__":
    main()
