"""
This module implements every function that requires the cosine similiarty score to be caltulated 

1. Input: query vector, cluter means, fulla artwork embedding matrix and the cluster assignment telling which artwork belongs to which cluster
2. It is assumed that all embeddings are L2-normalized in the embedding file. MOST importantly it assuems that the centroids are already normalized. 
3. Retrieval logic assumes embeddings, cluster means, and query vectors all live
in the same joint embedding space
4. Cosine similarity is computed between one and many stored vectors 
5. top_k_indices return top k indices based on the cosine simliarty scores
6. Top 5 clusters are found and among them the top 7 artworks 
7. Output is selected cluster_id, cluster_score, artwork_indices and artowkr_scores that can be used to map indices back to artowkr rows
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

def l2_normalize(array: np.ndarray, *, axis: int = -1, eps: float = 1e-12) -> np.ndarray:
    """Return an L2-normalized copy while keeping zero vectors stable."""
    arr = np.asarray(array, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=axis, keepdims=True)
    norms = np.maximum(norms, eps)
    return arr / norms


def _prepare_query(query: np.ndarray, expected_dim: int, *, assume_normalized: bool) -> np.ndarray:
    """Validate and optionally normalize a query vector."""
    q = np.asarray(query, dtype=np.float32)
    if q.ndim == 2:
        if q.shape[0] != 1:
            raise ValueError("query must be 1D or shape (1, d)")
        q = q[0]
    if q.ndim != 1:
        raise ValueError("query must be 1D or shape (1, d)")
    if q.shape[0] != expected_dim:
        raise ValueError(
            f"query has dim {q.shape[0]}, but embeddings expect dim {expected_dim}"
        )
    if not assume_normalized:
        q = l2_normalize(q, axis=0)
    return q


def _prepare_matrix(
    matrix: np.ndarray,
    *,
    name: str,
    assume_normalized: bool,
) -> np.ndarray:
    """Validate and optionally row-normalize an embedding matrix."""
    arr = np.asarray(matrix, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be a 2D array")
    if not assume_normalized:
        arr = l2_normalize(arr, axis=1)
    return arr


def cosine_similarity(
    query: np.ndarray,
    matrix: np.ndarray,
    *,
    assume_normalized: bool = True,
) -> np.ndarray:
    """
    Compute cosine similarity between one query vector and many stored vectors.

    If the inputs are already L2-normalized, cosine similarity is just a dot product.
    """
    rows = _prepare_matrix(matrix, name="matrix", assume_normalized=assume_normalized)
    q = _prepare_query(query, rows.shape[1], assume_normalized=assume_normalized)
    return rows @ q


def top_k_indices(scores: np.ndarray, k: int) -> np.ndarray:
    """Return indices of the top-k scores in descending order."""
    values = np.asarray(scores, dtype=np.float32)
    if values.ndim != 1:
        raise ValueError("scores must be a 1D array")
    if k <= 0:
        raise ValueError("k must be positive")
    if values.size == 0:
        return np.empty(0, dtype=np.int64)

    k = min(k, values.size)
    if k == values.size:
        return np.argsort(values)[::-1]

    idx = np.argpartition(values, -k)[-k:]
    return idx[np.argsort(values[idx])[::-1]]


def hard_assignments(assignments: np.ndarray) -> np.ndarray:
    """
    Convert saved cluster assignments into a 1D hard-assignment array.

    Supports either:
    - shape (n,) integer cluster ids
    - shape (n, k) responsibility matrix, converted via argmax
    """
    arr = np.asarray(assignments)
    if arr.ndim == 1:
        return arr.astype(np.int64, copy=False)
    if arr.ndim == 2:
        return np.argmax(arr, axis=1).astype(np.int64, copy=False)
    raise ValueError("assignments must be shape (n,) or (n, k)")


@dataclass(frozen=True)
class ClusterRetrievalResult:
    """Ranked retrieval results for one selected cluster."""

    cluster_id: int
    cluster_score: float
    artwork_indices: np.ndarray
    artwork_scores: np.ndarray

    def with_metadata(self, metadata: pd.DataFrame) -> pd.DataFrame:
        """Attach human-readable metadata rows for this cluster result."""
        rows = metadata.iloc[self.artwork_indices].copy()
        rows.insert(0, "artwork_score", self.artwork_scores)
        rows.insert(0, "rank_within_cluster", np.arange(1, len(rows) + 1))
        rows.insert(0, "cluster_score", np.float32(self.cluster_score))
        rows.insert(0, "cluster_id", np.int64(self.cluster_id))
        return rows


def score_clusters(
    query: np.ndarray,
    centroids: np.ndarray,
    *,
    assume_normalized: bool = True,
) -> np.ndarray:
    """Score the query against every cluster mean."""
    return cosine_similarity(query, centroids, assume_normalized=assume_normalized)


def select_top_clusters(
    query: np.ndarray,
    centroids: np.ndarray,
    *,
    top_k: int = 5,
    assume_normalized: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the top cluster ids and their scores."""
    scores = score_clusters(query, centroids, assume_normalized=assume_normalized)
    ids = top_k_indices(scores, top_k)
    return ids, scores[ids]


def retrieve_top_artworks_in_cluster(
    query: np.ndarray,
    embeddings: np.ndarray,
    artwork_indices: np.ndarray,
    *,
    top_k: int = 7,
    assume_normalized: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the top artwork indices and scores within one cluster."""
    indices = np.asarray(artwork_indices, dtype=np.int64)
    if indices.ndim != 1:
        raise ValueError("artwork_indices must be a 1D array")
    if indices.size == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float32)

    cluster_embeddings = np.asarray(embeddings, dtype=np.float32)[indices]
    scores = cosine_similarity(query, cluster_embeddings, assume_normalized=assume_normalized)
    local_top = top_k_indices(scores, top_k)
    return indices[local_top], scores[local_top]


def retrieve_from_clusters(
    query: np.ndarray,
    embeddings: np.ndarray,
    assignments: np.ndarray,
    centroids: np.ndarray,
    *,
    top_clusters: int = 5,
    top_per_cluster: int = 7,
    assume_normalized: bool = True,
) -> list[ClusterRetrievalResult]:
    """
    Run the full two-stage retrieval pass described in the project writeup.

    Returns one `ClusterRetrievalResult` per selected cluster, ordered by cluster score.
    """
    embedding_matrix = _prepare_matrix(
        embeddings,
        name="embeddings",
        assume_normalized=assume_normalized,
    )
    centroid_matrix = _prepare_matrix(
        centroids,
        name="centroids",
        assume_normalized=assume_normalized,
    )
    hard = hard_assignments(assignments)

    if embedding_matrix.shape[0] != hard.shape[0]:
        raise ValueError(
            "embeddings and assignments must have the same number of rows"
        )
    if embedding_matrix.shape[1] != centroid_matrix.shape[1]:
        raise ValueError(
            "embeddings and centroids must share the same embedding dimension"
        )

    cluster_ids, cluster_scores = select_top_clusters(
        query,
        centroid_matrix,
        top_k=top_clusters,
        assume_normalized=assume_normalized,
    )

    results: list[ClusterRetrievalResult] = []
    for cluster_id, cluster_score in zip(cluster_ids, cluster_scores, strict=True):
        member_indices = np.flatnonzero(hard == cluster_id)
        top_indices, top_scores = retrieve_top_artworks_in_cluster(
            query,
            embedding_matrix,
            member_indices,
            top_k=top_per_cluster,
            assume_normalized=assume_normalized,
        )
        results.append(
            ClusterRetrievalResult(
                cluster_id=int(cluster_id),
                cluster_score=float(cluster_score),
                artwork_indices=top_indices,
                artwork_scores=top_scores.astype(np.float32, copy=False),
            )
        )
    return results


def results_table(
    results: Sequence[ClusterRetrievalResult],
    metadata: pd.DataFrame,
) -> pd.DataFrame:
    """Flatten per-cluster retrieval results into one dataframe."""
    frames = [result.with_metadata(metadata) for result in results]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_query_vector(path: Path) -> np.ndarray:
    """Load a query vector from a .npy file."""
    arr = np.load(path)
    if arr.ndim == 2:
        if arr.shape[0] != 1:
            raise ValueError("query vector file must contain shape (d,) or (1, d)")
        arr = arr[0]
    return np.asarray(arr, dtype=np.float32)


def encode_query_text(
    query_text: str,
    *,
    text_model_name: str,
    clip_model_name: str | None,
    batch_size: int,
    device: str,
    clip_weight: float,
    text_weight: float,
) -> np.ndarray:
    """Encode one free-text query into the joint space used at retrieval time."""
    try:
        from .embed_pipeline import embed_queries
    except ImportError:
        from embed_pipeline import embed_queries

    vectors = embed_queries(
        [query_text],
        text_model_name=text_model_name,
        clip_model_name=clip_model_name,
        batch_size=batch_size,
        device=device,
        clip_weight=clip_weight,
        text_weight=text_weight,
    )
    return vectors[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cosine-similarity retrieval for Met embeddings")
    parser.add_argument("--embeddings", type=Path, required=True, help="Path to embeddings.npy")
    parser.add_argument("--assignments", type=Path, required=True, help="Path to cluster assignments")
    parser.add_argument("--centroids", type=Path, required=True, help="Path to cluster means")
    parser.add_argument("--metadata", type=Path, default=None, help="Optional metadata CSV")
    parser.add_argument("--top-clusters", type=int, default=5, help="How many clusters to retrieve")
    parser.add_argument("--top-per-cluster", type=int, default=7, help="How many artworks per cluster")
    parser.add_argument(
        "--query-vector",
        type=Path,
        default=None,
        help="Optional .npy file containing one encoded query vector",
    )
    parser.add_argument(
        "--query-text",
        default=None,
        help="Optional raw text query to encode with the embedding pipeline",
    )
    parser.add_argument(
        "--text-model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Sentence-transformer used when --query-text is provided",
    )
    parser.add_argument(
        "--clip-model",
        default="openai/clip-vit-base-patch32",
        help="CLIP model used when --query-text is provided",
    )
    parser.add_argument(
        "--disable-clip-query",
        action="store_true",
        help="Encode query text without the CLIP component",
    )
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size for query encoding")
    parser.add_argument("--device", default="auto", help="Torch device for query encoding")
    parser.add_argument("--clip-weight", type=float, default=1.0, help="CLIP weight for query encoding")
    parser.add_argument("--text-weight", type=float, default=1.0, help="Text weight for query encoding")
    parser.add_argument(
        "--normalize-at-query-time",
        dest="assume_normalized",
        action="store_false",
        help="L2-normalize embeddings, centroids, and query inside the retrieval call",
    )
    parser.set_defaults(assume_normalized=True)
    args = parser.parse_args()

    if bool(args.query_vector) == bool(args.query_text):
        parser.error("Provide exactly one of --query-vector or --query-text")
    return args


def main() -> int:
    args = parse_args()
    embeddings = np.load(args.embeddings)
    assignments = np.load(args.assignments)
    centroids = np.load(args.centroids)

    if args.query_vector is not None:
        query = load_query_vector(args.query_vector)
    else:
        query = encode_query_text(
            args.query_text,
            text_model_name=args.text_model,
            clip_model_name=None if args.disable_clip_query else args.clip_model,
            batch_size=args.batch_size,
            device=args.device,
            clip_weight=args.clip_weight,
            text_weight=args.text_weight,
        )

    results = retrieve_from_clusters(
        query,
        embeddings,
        assignments,
        centroids,
        top_clusters=args.top_clusters,
        top_per_cluster=args.top_per_cluster,
        assume_normalized=args.assume_normalized,
    )

    if args.metadata is None:
        for result in results:
            print(
                f"cluster_id={result.cluster_id} "
                f"cluster_score={result.cluster_score:.4f} "
                f"indices={result.artwork_indices.tolist()}"
            )
        return 0

    metadata = pd.read_csv(args.metadata)
    if len(metadata) != embeddings.shape[0]:
        raise ValueError(
            "metadata.csv must have the same number of rows as embeddings.npy for positional alignment"
        )
    table = results_table(results, metadata)
    if table.empty:
        print("No results found.")
        return 0

    display_cols = [
        col
        for col in [
            "cluster_id",
            "rank_within_cluster",
            "cluster_score",
            "artwork_score",
            "objectID",
            "title",
            "department",
            "objectURL",
        ]
        if col in table.columns
    ]
    print(table.loc[:, display_cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
