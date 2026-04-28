"""
Offline embedding pipeline for Met Museum objects.

This module turns a CSV of Met object metadata into reusable embedding artifacts:

- sentence-transformer text embeddings built from metadata fields
- CLIP image embeddings built from object images
- a normalized joint vector formed by weighted concatenation

The same module also exposes query-embedding helpers so search code can place a
natural-language prompt into the same joint space later on.

Example:
    python -m src.embed_pipeline ^
        --input-csv data/processed/met_on_view.csv ^
        --output-dir embeddings ^
        --limit 500
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoProcessor, CLIPModel

try:
    from .embed_prep import build_embedding_text, image_url, load_pil_image
except ImportError:
    from embed_prep import build_embedding_text, image_url, load_pil_image

DEFAULT_TEXT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_CLIP_MODEL = "openai/clip-vit-base-patch32"
KNOWN_CLIP_PROJECTION_DIMS = {
    DEFAULT_CLIP_MODEL: 512,
}
DEFAULT_METADATA_COLUMNS = [
    "objectID",
    "title",
    "artistDisplayName",
    "department",
    "GalleryNumber",
    "objectDate",
    "culture",
    "medium",
    "primaryImageSmall",
    "primaryImage",
    "objectURL",
]


def l2_normalize(array: np.ndarray, *, axis: int = 1, eps: float = 1e-12) -> np.ndarray:
    """Return an L2-normalized copy while keeping zero vectors stable."""
    array = np.asarray(array, dtype=np.float32)
    norms = np.linalg.norm(array, axis=axis, keepdims=True)
    norms = np.maximum(norms, eps)
    return array / norms


def resolve_device(requested: str) -> str:
    """Resolve a user device hint into a concrete torch device string."""
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def batched(sequence: Sequence[object], batch_size: int) -> Iterable[tuple[int, Sequence[object]]]:
    """Yield (start_index, batch_slice) pairs."""
    for start in range(0, len(sequence), batch_size):
        yield start, sequence[start : start + batch_size]


def build_embedding_dataframe(df: pd.DataFrame, *, prefer_image_field: str) -> pd.DataFrame:
    """Add the canonical embedding text and preferred image URL columns."""
    out = df.copy()

    tqdm.pandas(desc="Building embed_text")
    out["embed_text"] = out.progress_apply(build_embedding_text, axis=1)

    tqdm.pandas(desc="Resolving image URLs")
    out["embed_image_url"] = out.progress_apply(
        lambda row: image_url(row, prefer=prefer_image_field),
        axis=1,
    )

    out["has_image_url"] = out["embed_image_url"].fillna("").astype(str).str.strip().ne("")
    return out


def embed_metadata_texts(
    texts: Sequence[str],
    *,
    model_name: str,
    batch_size: int,
    device: str,
) -> np.ndarray:
    """Encode metadata strings into a dense semantic space."""
    model = SentenceTransformer(model_name, device=device)
    vectors = model.encode(
        list(texts),
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return np.asarray(vectors, dtype=np.float32)


def load_clip(model_name: str, device: str) -> tuple[CLIPModel, AutoProcessor]:
    """Load CLIP once for both image and text encoding."""
    model = CLIPModel.from_pretrained(model_name)
    processor = AutoProcessor.from_pretrained(model_name)
    model.eval()
    model.to(device)
    return model, processor


def resolve_clip_projection_dim(model_name: str, *, clip_dim: int | None = None) -> int:
    """Resolve the CLIP projection dimension without loading the model when possible."""
    if clip_dim is not None:
        if clip_dim <= 0:
            raise ValueError("--clip-dim must be positive when provided")
        return clip_dim
    known = KNOWN_CLIP_PROJECTION_DIMS.get(model_name)
    if known is not None:
        return known
    raise ValueError(
        "Unknown CLIP projection dimension for model "
        f"{model_name!r}. Pass --clip-dim to use --skip-images without loading CLIP."
    )


from tqdm.auto import tqdm  # add near imports


def embed_clip_images(
    image_urls: Sequence[str | None],
    *,
    model_name: str,
    batch_size: int,
    device: str,
    timeout: float,
) -> tuple[np.ndarray, list[str]]:
    """Encode artwork images with CLIP and record per-row embedding status."""
    model, processor = load_clip(model_name, device)
    dim = int(model.config.projection_dim)
    vectors = np.zeros((len(image_urls), dim), dtype=np.float32)
    statuses = [
        "missing_url" if not url or not str(url).strip() else "pending"
        for url in image_urls
    ]

    urls = list(image_urls)
    num_batches = (len(urls) + batch_size - 1) // batch_size

    embedded_count = 0
    failed_count = 0
    missing_count = int(sum(s == "missing_url" for s in statuses))

    pbar = tqdm(
        batched(urls, batch_size),
        total=num_batches,
        desc="CLIP image batches",
        unit="batch",
    )

    for start, batch_urls in pbar:
        images = []
        target_rows: list[int] = []

        for offset, url in enumerate(batch_urls):
            row_index = start + offset
            if not url:
                continue
            image = load_pil_image(url, timeout=timeout)
            if image is None:
                statuses[row_index] = "download_or_decode_failed"
                failed_count += 1
                continue
            images.append(image)
            target_rows.append(row_index)
            statuses[row_index] = "loaded"

        if images:
            inputs = processor(images=images, return_tensors="pt")
            inputs = {key: value.to(device) for key, value in inputs.items()}
            with torch.inference_mode():
                feats = model.get_image_features(**inputs)

            batch_vectors = feats.detach().cpu().numpy().astype(np.float32)
            vectors[target_rows] = l2_normalize(batch_vectors)

            for row_index in target_rows:
                statuses[row_index] = "embedded"
            embedded_count += len(target_rows)

        pbar.set_postfix(
            embedded=embedded_count,
            failed=failed_count,
            missing=missing_count,
        )

    return vectors, statuses


def embed_clip_texts(
    texts: Sequence[str],
    *,
    model_name: str,
    batch_size: int,
    device: str,
) -> np.ndarray:
    """Encode free-text queries into the CLIP-aligned semantic space."""
    model, processor = load_clip(model_name, device)
    dim = int(model.config.projection_dim)
    vectors = np.zeros((len(texts), dim), dtype=np.float32)

    texts_list = list(texts)
    num_batches = (len(texts_list) + batch_size - 1) // batch_size

    for start, batch_texts in tqdm(
        batched(texts_list, batch_size),
        total=num_batches,
        desc="CLIP text batches",
        unit="batch",
    ):
        inputs = processor(
            text=list(batch_texts),
            return_tensors="pt",
            padding=True,
            truncation=True,
        )
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.inference_mode():
            feats = model.get_text_features(**inputs)
        batch_vectors = feats.detach().cpu().numpy().astype(np.float32)
        vectors[start : start + len(batch_texts)] = l2_normalize(batch_vectors)

    return vectors


def build_joint_embeddings(
    clip_vectors: np.ndarray,
    text_vectors: np.ndarray,
    *,
    clip_weight: float = 1.0,
    text_weight: float = 1.0,
) -> np.ndarray:
    """Combine CLIP and metadata vectors into a single normalized representation."""
    if len(clip_vectors) != len(text_vectors):
        raise ValueError("clip_vectors and text_vectors must have the same row count")
    weighted_clip = l2_normalize(clip_vectors) * np.float32(clip_weight)
    weighted_text = l2_normalize(text_vectors) * np.float32(text_weight)
    joint = np.concatenate([weighted_clip, weighted_text], axis=1)
    return l2_normalize(joint)


def embed_queries(
    queries: Sequence[str],
    *,
    text_model_name: str = DEFAULT_TEXT_MODEL,
    clip_model_name: str | None = DEFAULT_CLIP_MODEL,
    batch_size: int = 32,
    device: str = "auto",
    clip_weight: float = 1.0,
    text_weight: float = 1.0,
) -> np.ndarray:
    """
    Build query embeddings in the same joint space used for artworks.

    The artwork side uses CLIP-image + metadata-text vectors. The query side uses
    CLIP-text + metadata-text vectors so cosine similarity still compares aligned
    CLIP dimensions alongside the richer metadata dimensions.
    """
    resolved_device = resolve_device(device)
    if clip_model_name:
        clip_vectors = embed_clip_texts(
            queries,
            model_name=clip_model_name,
            batch_size=batch_size,
            device=resolved_device,
        )
    else:
        clip_vectors = np.zeros((len(queries), 0), dtype=np.float32)
    text_vectors = embed_metadata_texts(
        queries,
        model_name=text_model_name,
        batch_size=batch_size,
        device=resolved_device,
    )
    return build_joint_embeddings(
        clip_vectors,
        text_vectors,
        clip_weight=clip_weight,
        text_weight=text_weight,
    )


def save_artifacts(
    df: pd.DataFrame,
    *,
    output_dir: Path,
    text_vectors: np.ndarray,
    clip_vectors: np.ndarray,
    joint_vectors: np.ndarray,
    text_model_name: str,
    clip_model_name: str,
    clip_weight: float,
    text_weight: float,
    clip_enabled: bool,
) -> None:
    """Persist embeddings plus lightweight metadata for later retrieval."""
    output_dir.mkdir(parents=True, exist_ok=True)
    clip_status_counts = {
        str(status): int(count)
        for status, count in df["clip_embedding_status"].value_counts().items()
    }

    np.save(output_dir / "text_embeddings.npy", text_vectors)
    np.save(output_dir / "clip_embeddings.npy", clip_vectors)
    np.save(output_dir / "joint_embeddings.npy", joint_vectors)

    metadata_columns = [col for col in DEFAULT_METADATA_COLUMNS if col in df.columns]
    metadata_columns.extend(
        [
            "embed_text",
            "embed_image_url",
            "has_image_url",
            "clip_embedding_status",
            "has_clip_embedding",
        ]
    )
    df.loc[:, metadata_columns].to_csv(output_dir / "metadata.csv", index=False)

    manifest = {
        "rows": int(len(df)),
        "text_model": text_model_name,
        "clip_model": clip_model_name,
        "clip_enabled": clip_enabled,
        "text_weight": text_weight,
        "clip_weight": clip_weight,
        "text_embedding_dim": int(text_vectors.shape[1]),
        "clip_embedding_dim": int(clip_vectors.shape[1]),
        "joint_embedding_dim": int(joint_vectors.shape[1]),
        "clip_embedding_status_counts": clip_status_counts,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Met artwork embedding artifacts")
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path("data/processed/met_on_view.csv"),
        help="CSV exported from the Met API",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("embeddings"),
        help="Directory for .npy and metadata outputs",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only embed the first N rows for smoke testing",
    )
    parser.add_argument(
        "--text-model",
        default=DEFAULT_TEXT_MODEL,
        help="sentence-transformers model for metadata text",
    )
    parser.add_argument(
        "--clip-model",
        default=DEFAULT_CLIP_MODEL,
        help="CLIP model for image embeddings and future query text embeddings",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for both text and CLIP processing",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="Torch device: auto, cpu, cuda, or mps",
    )
    parser.add_argument(
        "--clip-weight",
        type=float,
        default=1.0,
        help="Weight applied to normalized CLIP vectors before concatenation",
    )
    parser.add_argument(
        "--text-weight",
        type=float,
        default=1.0,
        help="Weight applied to normalized metadata vectors before concatenation",
    )
    parser.add_argument(
        "--prefer-image-field",
        default="primaryImageSmall",
        help="Preferred URL column for CLIP image downloads",
    )
    parser.add_argument(
        "--image-timeout",
        type=float,
        default=30.0,
        help="Per-image download timeout in seconds",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip CLIP image encoding and fill that part with zeros",
    )
    parser.add_argument(
        "--disable-clip",
        action="store_true",
        help="Build a text-only embedding space with no CLIP component",
    )
    parser.add_argument(
        "--clip-dim",
        type=int,
        default=None,
        help="Projection dim for --skip-images when you do not want to load CLIP",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    device = resolve_device(args.device)

    print("[1/5] Loading input CSV...")
    df = pd.read_csv(args.input_csv)
    if args.limit is not None:
        df = df.head(args.limit).copy()

    print("[2/5] Building embedding dataframe...")
    df = build_embedding_dataframe(df, prefer_image_field=args.prefer_image_field)

    print("[3/5] Encoding metadata text embeddings...")
    text_vectors = embed_metadata_texts(
        df["embed_text"].fillna("").tolist(),
        model_name=args.text_model,
        batch_size=args.batch_size,
        device=device,
    )

    print("[4/5] Building CLIP embeddings...")
    if args.disable_clip:
        clip_vectors = np.zeros((len(df), 0), dtype=np.float32)
        df["clip_embedding_status"] = np.where(
            df["has_image_url"],
            "clip_disabled",
            "missing_url",
        )
    elif args.skip_images:
        clip_dim = resolve_clip_projection_dim(
            args.clip_model,
            clip_dim=args.clip_dim,
        )
        clip_vectors = np.zeros((len(df), clip_dim), dtype=np.float32)
        df["clip_embedding_status"] = np.where(
            df["has_image_url"],
            "skipped_image_encoding",
            "missing_url",
        )
    else:
        clip_vectors, clip_statuses = embed_clip_images(
            df["embed_image_url"].tolist(),
            model_name=args.clip_model,
            batch_size=args.batch_size,
            device=device,
            timeout=args.image_timeout,
        )
        df["clip_embedding_status"] = clip_statuses

    print("[5/5] Building joint embeddings + saving artifacts...")

    df["has_clip_embedding"] = df["clip_embedding_status"].eq("embedded")

    joint_vectors = build_joint_embeddings(
        clip_vectors,
        text_vectors,
        clip_weight=args.clip_weight,
        text_weight=args.text_weight,
    )

    save_artifacts(
        df,
        output_dir=args.output_dir,
        text_vectors=text_vectors,
        clip_vectors=clip_vectors,
        joint_vectors=joint_vectors,
        text_model_name=args.text_model,
        clip_model_name=args.clip_model,
        clip_weight=args.clip_weight,
        text_weight=args.text_weight,
        clip_enabled=not args.disable_clip,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
