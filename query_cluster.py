"""
Assign a text query to its GMM cluster.

Embeds the query into the same joint space used to build joint_embeddings.npy:
  - CLIP text features (openai/clip-vit-base-patch32, 512-dim)
  - Sentence-transformer metadata features (all-MiniLM-L6-v2, 384-dim)
  - Weighted concatenation then L2-normalized → 896-dim

Usage:
    python -m src.query_cluster "a serene landscape with mountains"
    python -m src.query_cluster "portrait of a woman" --top 3 --show-size
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from scipy.special import logsumexp
from sentence_transformers import SentenceTransformer
from transformers import AutoProcessor, CLIPModel


DEFAULT_TEXT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_CLIP_MODEL = "openai/clip-vit-base-patch32"


def _resolve_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _l2_normalize(arr: np.ndarray, *, eps: float = 1e-12) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float32)
    norm = np.linalg.norm(arr)
    return arr / max(norm, eps)


def embed_query(
    text: str,
    *,
    clip_model_name: str = DEFAULT_CLIP_MODEL,
    text_model_name: str = DEFAULT_TEXT_MODEL,
    clip_weight: float = 1.0,
    text_weight: float = 1.0,
) -> np.ndarray:
    """
    Embed a text query into the joint space, matching embed_pipeline.build_joint_embeddings.

    Artworks use CLIP image + sentence-transformer text.
    Queries use CLIP text + sentence-transformer text so both sides share the
    same CLIP semantic space alongside the richer metadata dimensions.
    """
    device = _resolve_device()

    # CLIP text features
    clip_model = CLIPModel.from_pretrained(clip_model_name).eval().to(device)
    clip_proc = AutoProcessor.from_pretrained(clip_model_name)
    inputs = clip_proc(text=[text], return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.inference_mode():
        clip_feat = clip_model.get_text_features(**inputs)
    clip_vec = clip_feat.cpu().numpy().squeeze(0).astype(np.float32)  # (512,)

    # Sentence-transformer text features
    st_model = SentenceTransformer(text_model_name, device=device)
    text_vec = st_model.encode(
        [text],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )[0].astype(np.float32)  # (384,)

    # Replicate build_joint_embeddings: weight, concat, normalize
    weighted_clip = _l2_normalize(clip_vec) * np.float32(clip_weight)
    weighted_text = _l2_normalize(text_vec) * np.float32(text_weight)
    joint = np.concatenate([weighted_clip, weighted_text])  # (896,)
    return _l2_normalize(joint)


def load_gmm(gmm_dir: Path, space: str = "joint") -> dict:
    npz_path = gmm_dir / f"gmm_{space}.npz"
    if not npz_path.exists():
        raise FileNotFoundError(f"{npz_path} not found — run cluster_gmm first")
    data = np.load(npz_path)
    required = {"means", "covariances", "weights", "scaler_mean", "scaler_scale"}
    missing = required - set(data.files)
    if missing:
        raise KeyError(
            f"GMM artifact missing keys: {missing}. "
            "Re-run cluster_gmm to regenerate with covariances saved."
        )
    return {k: data[k].astype(np.float64) for k in required}


def assign_cluster(
    query_vec: np.ndarray,
    gmm: dict,
    top_k: int = 1,
) -> list[tuple[int, float]]:
    x = (query_vec.astype(np.float64) - gmm["scaler_mean"]) / gmm["scaler_scale"]

    means   = gmm["means"]        # (K, D)
    covs    = gmm["covariances"]  # (K, D) diagonal
    weights = gmm["weights"]      # (K,)

    # log p(x | k) under diagonal Gaussian
    log_likelihoods = -0.5 * np.sum(
        ((x - means) ** 2) / covs + np.log(2 * np.pi * covs), axis=1
    )

    log_posteriors = np.log(weights) + log_likelihoods
    log_posteriors -= logsumexp(log_posteriors)

    ranked = np.argsort(log_posteriors)[::-1][:top_k]
    return [(int(k), float(np.exp(log_posteriors[k]))) for k in ranked]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assign a text query to a GMM cluster")
    parser.add_argument("query", type=str, help="Text query to embed and assign")
    parser.add_argument(
        "--gmm-dir",
        type=Path,
        default=Path("embeddings/metart"),
    )
    parser.add_argument(
        "--space",
        default="joint",
        choices=["clip", "text", "joint"],
    )
    parser.add_argument(
        "--top",
        type=int,
        default=1,
        help="Show top-N clusters by posterior probability",
    )
    parser.add_argument(
        "--clip-weight",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--text-weight",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--show-size",
        action="store_true",
        help="Print how many items are in each assigned cluster",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print(f'Embedding query: "{args.query}"')
    query_vec = embed_query(
        args.query,
        clip_weight=args.clip_weight,
        text_weight=args.text_weight,
    )
    print(f"  joint embedding shape: {query_vec.shape}")

    gmm = load_gmm(args.gmm_dir, space=args.space)
    results = assign_cluster(query_vec, gmm, top_k=args.top)

    indices = None
    if args.show_size:
        indices_path = args.gmm_dir / f"gmm_{args.space}_indices.json"
        with open(indices_path) as f:
            indices = json.load(f)

    print(f"\nTop-{args.top} cluster assignment(s):")
    for rank, (cluster_id, prob) in enumerate(results, 1):
        size_str = ""
        if indices is not None:
            size_str = f"  ({len(indices[str(cluster_id)])} items in cluster)"
        print(f"  #{rank}  cluster {cluster_id:>3d}  p={prob:.4f}{size_str}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
