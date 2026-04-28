"""
Cluster-filtered cosine search over joint embeddings, with Met tour routing.

Embeds a text query into the joint space, assigns it to GMM clusters,
runs cosine similarity only against embeddings in those clusters,
then routes the results into an efficient walking tour via met_tour_routing.

Usage:
    python -m src.search.retrieval "portrait of a woman"
    python -m src.search.retrieval "gold decorative vase" --top-clusters 2 --top-k 10
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.search.met_tour_routing import build_tour, group_by_stop
from src.search.query_cluster import assign_cluster, embed_query, load_gmm


def cosine_search(
    query_vec: np.ndarray,
    joint_embeddings: np.ndarray,
    candidate_indices: list[int],
    top_k: int,
) -> list[tuple[int, float]]:
    candidates = joint_embeddings[candidate_indices]
    norms = np.linalg.norm(candidates, axis=1, keepdims=True)
    candidates_norm = candidates / np.maximum(norms, 1e-12)
    q_norm = query_vec / max(np.linalg.norm(query_vec), 1e-12)
    scores = candidates_norm @ q_norm
    top = np.argsort(scores)[::-1][:top_k]
    return [(candidate_indices[i], float(scores[i])) for i in top]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cluster-filtered cosine search with tour routing")
    parser.add_argument("query", type=str, help="Text query")
    parser.add_argument("--gmm-dir", type=Path, default=Path("embeddings/metart"))
    parser.add_argument("--embeddings", type=Path, default=Path("embeddings/metart/joint_embeddings.npy"))
    parser.add_argument("--metadata", type=Path, default=Path("embeddings/metart/metadata.csv"))
    parser.add_argument("--top-clusters", type=int, default=1, help="GMM clusters to search within")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results to return")
    parser.add_argument("--clip-weight", type=float, default=1.0)
    parser.add_argument("--text-weight", type=float, default=1.0)
    parser.add_argument("--no-routing", action="store_true", help="Skip tour routing, print by score")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print(f'Query: "{args.query}"')
    query_vec = embed_query(args.query, clip_weight=args.clip_weight, text_weight=args.text_weight)
    print(f"  embedding shape: {query_vec.shape}")

    gmm = load_gmm(args.gmm_dir, space="joint")
    clusters = assign_cluster(query_vec, gmm, top_k=args.top_clusters)

    indices_path = args.gmm_dir / "gmm_joint_indices.json"
    with open(indices_path) as f:
        cluster_indices = json.load(f)

    print(f"\nLoading joint embeddings ...")
    joint_embeddings = np.load(args.embeddings).astype(np.float32)

    metadata = pd.read_csv(args.metadata) if args.metadata.exists() else None

    print(f"\nTop-{args.top_clusters} cluster(s) selected:")
    for cluster_id, prob in clusters:
        print(f"  cluster {cluster_id:>3d}  p={prob:.4f}  ({len(cluster_indices[str(cluster_id)])} items)")

    candidate_pool: list[int] = []
    for cluster_id, _ in clusters:
        candidate_pool.extend(cluster_indices[str(cluster_id)])

    results = cosine_search(query_vec, joint_embeddings, candidate_pool, top_k=args.top_k)

    # Build artwork dicts from metadata for routing
    score_by_idx = {idx: score for idx, score in results}
    artworks: list[dict] = []
    for idx, score in results:
        if metadata is not None:
            row = metadata.iloc[idx].to_dict()
        else:
            row = {}
        row["_score"] = score
        row["_index"] = idx
        artworks.append(row)

    if args.no_routing:
        print(f"\nTop-{args.top_k} results (by score):")
        for rank, art in enumerate(artworks, 1):
            title = str(art.get("title", ""))[:60]
            artist = str(art.get("artistDisplayName", ""))
            score = art["_score"]
            print(f"  #{rank:>2}  score={score:.4f}  {title}")
            if artist and artist != "nan":
                print(f"          {artist}")
    else:
        print(f"\nTour route ({len(artworks)} stops):")
        tour = group_by_stop(artworks)
        stop_num = 1
        for location, stop_artworks in tour.items():
            print(f"\n  Stop {stop_num} — {location}")
            stop_num += 1
            for art in stop_artworks:
                title = str(art.get("title", "Untitled"))[:60]
                artist = str(art.get("artistDisplayName", ""))
                score = art.get("_score", 0.0)
                print(f"    • {title}  (score={score:.4f})")
                if artist and artist != "nan":
                    print(f"      {artist}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
