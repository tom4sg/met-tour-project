"""
GMM-filtered cosine search over the joint embedding space.

Instead of brute-forcing all 44k artworks, we assign the query to its top-N
GMM clusters, collect only those candidates, then run cosine similarity within
that pool — matching the retrieval logic in src/search/retrieval.py.
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from models import SearchHit, SearchMode

DEFAULT_TOP_CLUSTERS = 2


def _logsumexp(arr: np.ndarray) -> float:
    m = float(arr.max())
    return m + float(np.log(np.sum(np.exp(arr - m))))


def _l2_normalize(vec: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / max(norm, eps)


class EmbeddingIndex:
    joint_matrix: np.ndarray         # (N, 896) float32, unit-normalized
    gmm: dict                        # means, covariances, weights, scaler_mean, scaler_scale
    cluster_indices: dict            # str(cluster_id) -> list[int]
    metadata: pd.DataFrame

    def load(self, embeddings_dir: Path, metadata_path: Path) -> None:
        # Joint embeddings
        joint_path = embeddings_dir / "joint_embeddings.npy"
        if not joint_path.exists():
            print(f"Missing: {joint_path}", file=sys.stderr)
            sys.exit(1)
        raw = np.load(joint_path).astype(np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        self.joint_matrix = raw / norms

        # GMM parameters — resolve filenames via manifest
        manifest_path = embeddings_dir / "gmm_manifest.json"
        if not manifest_path.exists():
            print(f"Missing: {manifest_path} — run cluster_gmm first", file=sys.stderr)
            sys.exit(1)
        manifests = json.loads(manifest_path.read_text(encoding="utf-8"))
        joint_entry = next((m for m in reversed(manifests) if m["space"] == "joint"), None)
        if joint_entry is None:
            print("gmm_manifest.json has no joint space entry — run cluster_gmm first", file=sys.stderr)
            sys.exit(1)
        gmm_path = embeddings_dir / joint_entry["artifacts"]["npz"]
        idx_path = embeddings_dir / joint_entry["artifacts"]["indices_json"]

        if not gmm_path.exists():
            print(f"Missing: {gmm_path} — run cluster_gmm first", file=sys.stderr)
            sys.exit(1)
        gmm_data = np.load(gmm_path)
        required = {"means", "covariances", "weights", "scaler_mean", "scaler_scale"}
        missing = required - set(gmm_data.files)
        if missing:
            print(f"GMM file missing keys: {missing}", file=sys.stderr)
            sys.exit(1)
        self.gmm = {k: gmm_data[k].astype(np.float64) for k in required}

        # Cluster membership index
        if not idx_path.exists():
            print(f"Missing: {idx_path}", file=sys.stderr)
            sys.exit(1)
        with open(idx_path) as f:
            self.cluster_indices = json.load(f)

        # Metadata
        if not metadata_path.exists():
            print(f"Missing: {metadata_path}", file=sys.stderr)
            sys.exit(1)
        self.metadata = pd.read_csv(metadata_path).reset_index(drop=True)

    # ── GMM assignment ─────────────────────────────────────────────────────

    def _top_cluster_ids(self, query_vec: np.ndarray, top_k: int = DEFAULT_TOP_CLUSTERS) -> list[int]:
        x = (query_vec.astype(np.float64) - self.gmm["scaler_mean"]) / self.gmm["scaler_scale"]
        means = self.gmm["means"]
        covs = self.gmm["covariances"]
        weights = self.gmm["weights"]
        log_ll = -0.5 * np.sum(((x - means) ** 2) / covs + np.log(2 * np.pi * covs), axis=1)
        log_post = np.log(weights) + log_ll
        log_post -= _logsumexp(log_post)
        return [int(k) for k in np.argsort(log_post)[::-1][:top_k]]

    # ── Search ─────────────────────────────────────────────────────────────

    def search(
        self,
        query_vec: np.ndarray,
        mode: SearchMode,
        top_k: int,
        top_clusters: int = DEFAULT_TOP_CLUSTERS,
    ) -> list[SearchHit]:
        """GMM-filtered cosine search. `mode` is accepted for API compatibility but unused
        — all queries go through the joint embedding space."""
        cluster_ids = self._top_cluster_ids(query_vec, top_clusters)

        candidate_pool: list[int] = []
        for cid in cluster_ids:
            candidate_pool.extend(self.cluster_indices[str(cid)])

        if not candidate_pool:
            return []

        candidates = self.joint_matrix[candidate_pool]
        q = _l2_normalize(query_vec.astype(np.float32))
        scores = candidates @ q

        sorted_local = np.argsort(scores)[::-1][:top_k]
        return [
            SearchHit(row_index=candidate_pool[i], score=float(scores[i]))
            for i in sorted_local
        ]

    # ── Metadata lookup ────────────────────────────────────────────────────

    def get_artwork(self, row_index: int, mode: SearchMode) -> dict:
        row = self.metadata.iloc[row_index]

        def _str_or_none(col: str) -> str | None:
            val = row.get(col)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            s = str(val).strip()
            return s if s and s.lower() != "nan" else None

        def _bool_val(col: str) -> bool:
            val = row.get(col)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return False
            if isinstance(val, bool):
                return val
            return str(val).strip().lower() in ("true", "1", "yes", "public domain")

        object_url = str(row.get("objectURL", ""))
        m = re.search(r"/(\d+)$", object_url)
        object_id = int(m.group(1)) if m else int(row.get("objectID") or row_index)

        begin = _str_or_none("objectBeginDate")
        end = _str_or_none("objectEndDate")
        if begin and end and begin != end:
            object_date = f"{begin}–{end}"
        else:
            object_date = begin or end

        return {
            "object_id": object_id,
            "title": _str_or_none("title") or "",
            "artist_display_name": _str_or_none("artistDisplayName"),
            "object_date": object_date,
            "department": _str_or_none("department"),
            "medium": _str_or_none("medium"),
            "primary_image_small": _str_or_none("primaryImageSmall"),
            "primary_image": _str_or_none("primaryImage"),
            "object_url": object_url,
            "is_highlight": _bool_val("isHighlight_converted"),
            "gallery_number": _str_or_none("GalleryNumber"),
        }
