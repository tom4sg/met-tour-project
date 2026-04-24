"""
GMM clustering over pre-built embedding spaces.

For each space (clip, text, joint) this script:
  1. Loads the corresponding .npy file from --embedding-dir
  2. Fits a GaussianMixture model
  3. Assigns every point to its MAP cluster (argmax posterior)
  4. Saves the artifacts needed for cluster-filtered search:
       gmm_<space>.npz  — means (K×D), assignments (N,), weights (K,)
       gmm_<space>_indices.json — {cluster_id: [row_indices]} for fast lookup

Example:
    python -m src.cluster_gmm --embedding-dir embeddings/metart --n-components 64
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
from tqdm.auto import tqdm


SPACES = {
    "clip": "clip_embeddings.npy",
    "text": "text_embeddings.npy",
    "joint": "joint_embeddings.npy",
}


def fit_gmm(
    vectors: np.ndarray,
    *,
    n_components: int,
    covariance_type: str,
    max_iter: int,
    n_init: int,
    random_state: int,
    reg_covar: float,
) -> GaussianMixture:
    gmm = GaussianMixture(
        n_components=n_components,
        covariance_type=covariance_type,
        max_iter=max_iter,
        n_init=n_init,
        random_state=random_state,
        reg_covar=reg_covar,
        verbose=0,
    )
    # float64 required — float32 causes ill-conditioned covariance in high dims
    gmm.fit(vectors.astype(np.float64))
    return gmm


def save_space_artifacts(
    gmm: GaussianMixture,
    scaler: StandardScaler,
    assignments: np.ndarray,
    *,
    output_dir: Path,
    space: str,
    n_components: int,
    covariance_type: str,
) -> None:
    npz_path = output_dir / f"gmm_{space}.npz"
    np.savez(
        npz_path,
        means=gmm.means_.astype(np.float32),              # (K, D) — in scaled space
        weights=gmm.weights_.astype(np.float32),           # (K,)
        assignments=assignments.astype(np.int32),           # (N,)
        scaler_mean=scaler.mean_.astype(np.float32),        # (D,)
        scaler_scale=scaler.scale_.astype(np.float32),      # (D,)
    )

    cluster_indices: dict[str, list[int]] = {}
    for k in range(n_components):
        mask = assignments == k
        cluster_indices[str(k)] = np.where(mask)[0].tolist()

    indices_path = output_dir / f"gmm_{space}_indices.json"
    indices_path.write_text(json.dumps(cluster_indices), encoding="utf-8")

    sizes = [len(v) for v in cluster_indices.values()]
    print(
        f"  [{space}] saved {npz_path.name} + {indices_path.name}  "
        f"| clusters: min={min(sizes)} max={max(sizes)} mean={np.mean(sizes):.0f}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit GMM clusters on embedding spaces")
    parser.add_argument(
        "--embedding-dir",
        type=Path,
        default=Path("embeddings/metart"),
        help="Directory containing clip/text/joint .npy files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write GMM artifacts (defaults to --embedding-dir)",
    )
    parser.add_argument(
        "--spaces",
        nargs="+",
        default=list(SPACES.keys()),
        choices=list(SPACES.keys()),
        help="Which embedding spaces to cluster",
    )
    parser.add_argument(
        "--n-components",
        type=int,
        default=64,
        help="Number of GMM components (clusters)",
    )
    parser.add_argument(
        "--covariance-type",
        default="diag",
        choices=["full", "tied", "diag", "spherical"],
        help="GMM covariance structure (diag is fastest for high-dim data)",
    )
    parser.add_argument("--max-iter", type=int, default=200)
    parser.add_argument("--n-init", type=int, default=1)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--reg-covar",
        type=float,
        default=1e-3,
        help="Covariance regularization added to diagonal (increase if GMM collapses)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or args.embedding_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict] = []

    for space in args.spaces:
        npy_path = args.embedding_dir / SPACES[space]
        if not npy_path.exists():
            print(f"[{space}] {npy_path} not found — skipping")
            continue

        print(f"\n[{space}] Loading {npy_path} ...", flush=True)
        vectors = np.load(npy_path).astype(np.float32)
        print(f"  shape: {vectors.shape}")

        print(f"  Scaling with StandardScaler ...", flush=True)
        scaler = StandardScaler()
        scaled = scaler.fit_transform(vectors)

        print(f"  Fitting GMM (K={args.n_components}, cov={args.covariance_type}) ...", flush=True)
        t0 = time.perf_counter()
        gmm = fit_gmm(
            scaled,
            n_components=args.n_components,
            covariance_type=args.covariance_type,
            max_iter=args.max_iter,
            n_init=args.n_init,
            random_state=args.random_state,
            reg_covar=args.reg_covar,
        )
        elapsed = time.perf_counter() - t0
        print(f"  converged={gmm.converged_}  iterations={gmm.n_iter_}  ({elapsed:.1f}s)")

        assignments = gmm.predict(scaled.astype(np.float64))  # hard MAP assignment

        save_space_artifacts(
            gmm,
            scaler,
            assignments,
            output_dir=output_dir,
            space=space,
            n_components=args.n_components,
            covariance_type=args.covariance_type,
        )

        manifest_entries.append(
            {
                "space": space,
                "n_rows": int(vectors.shape[0]),
                "embedding_dim": int(vectors.shape[1]),
                "n_components": args.n_components,
                "covariance_type": args.covariance_type,
                "scaled": True,
                "converged": bool(gmm.converged_),
                "n_iter": int(gmm.n_iter_),
                "fit_seconds": round(elapsed, 2),
                "artifacts": {
                    "npz": f"gmm_{space}.npz",
                    "indices_json": f"gmm_{space}_indices.json",
                },
            }
        )

    manifest_path = output_dir / "gmm_manifest.json"
    manifest_path.write_text(json.dumps(manifest_entries, indent=2), encoding="utf-8")
    print(f"\nWrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
