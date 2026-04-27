"""
Projection of joint embeddings into 2D for cluster visualization.

UMAP query projection is approximated as the centroid of the top-k
result positions — nearby in 896-dim space → nearby in UMAP space.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

SAMPLE_PER_CLUSTER = 50


class VizProjector:
    umap_2d: np.ndarray              # (N, 2) float32
    cluster_assignments: np.ndarray  # (N,) int32
    n_clusters: int
    backdrop_umap: list

    def load(self, embeddings_dir: Path) -> None:
        required = ("umap_2d.npy", "cluster_assignments.npy")
        for fname in required:
            if not (embeddings_dir / fname).exists():
                print(
                    f"Missing viz file: {embeddings_dir / fname} "
                    "— run compute_projections first",
                    file=sys.stderr,
                )
                sys.exit(1)

        self.umap_2d = np.load(embeddings_dir / "umap_2d.npy")
        self.cluster_assignments = np.load(embeddings_dir / "cluster_assignments.npy")

        cluster_ids = sorted(int(c) for c in np.unique(self.cluster_assignments) if c >= 0)
        self.n_clusters = len(cluster_ids)
        self.backdrop_umap = self._sample(self.umap_2d, cluster_ids)

    def _sample(self, coords: np.ndarray, cluster_ids: list[int]) -> list:
        rng = np.random.default_rng(42)
        points: list = []
        for cid in cluster_ids:
            idx = np.where(self.cluster_assignments == cid)[0]
            n = min(SAMPLE_PER_CLUSTER, len(idx))
            for i in rng.choice(idx, size=n, replace=False):
                points.append([float(coords[i, 0]), float(coords[i, 1]), cid])
        return points

    def result_positions(self, row_indices: list[int]) -> list[list[float]]:
        return [[float(self.umap_2d[i, 0]), float(self.umap_2d[i, 1])] for i in row_indices]

    def approx_umap_query(self, row_indices: list[int]) -> list[float]:
        """Approximate query UMAP position as centroid of its top-k results."""
        if not row_indices:
            return [0.0, 0.0]
        positions = self.umap_2d[row_indices]
        centroid = positions.mean(axis=0)
        return [float(centroid[0]), float(centroid[1])]
