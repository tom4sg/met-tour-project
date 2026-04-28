"""
Query encoder matching the joint embedding space built by embed_pipeline.py:
  joint = l2_norm(concat([l2_norm(clip_vec) * clip_w, l2_norm(st_vec) * st_w]))
  where CLIP features occupy dims 0–511 and ST features occupy dims 512–895.
"""

import sys

import numpy as np
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import AutoProcessor, CLIPModel

TEXT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"


def _resolve_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _l2_normalize(vec: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    vec = np.asarray(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)
    return vec / max(norm, eps)


class QueryEncoder:
    def __init__(self) -> None:
        device = _resolve_device()
        self._device = device

        try:
            self._clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME).eval().to(device)
            self._clip_processor = AutoProcessor.from_pretrained(CLIP_MODEL_NAME)
        except Exception as exc:
            print(f"Failed to load CLIP model {CLIP_MODEL_NAME}: {exc}", file=sys.stderr)
            sys.exit(1)

        try:
            self._text_model = SentenceTransformer(TEXT_MODEL_NAME, device=device)
        except Exception as exc:
            print(f"Failed to load text model {TEXT_MODEL_NAME}: {exc}", file=sys.stderr)
            sys.exit(1)

    # ── Private feature extractors ─────────────────────────────────────────

    def _clip_text_features(self, text: str) -> np.ndarray:
        """L2-normalized 512-dim CLIP text features."""
        inputs = self._clip_processor(
            text=[text], return_tensors="pt", padding=True, truncation=True
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.inference_mode():
            feat = self._clip_model.get_text_features(**inputs)
        return _l2_normalize(feat.cpu().numpy().squeeze(0))

    def _clip_image_features(self, image: Image.Image) -> np.ndarray:
        """L2-normalized 512-dim CLIP image features."""
        inputs = self._clip_processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.inference_mode():
            feat = self._clip_model.get_image_features(**inputs)
        return _l2_normalize(feat.cpu().numpy().squeeze(0))

    def _st_text_features(self, text: str) -> np.ndarray:
        """L2-normalized 384-dim sentence-transformer features."""
        vec = self._text_model.encode(
            [text], convert_to_numpy=True, normalize_embeddings=True
        )[0].astype(np.float32)
        return _l2_normalize(vec)

    # ── Public encoding methods ────────────────────────────────────────────

    def encode_text(
        self, query: str, clip_weight: float = 1.0, st_weight: float = 1.0
    ) -> np.ndarray:
        """896-dim joint vector from text query (CLIP text + ST text)."""
        clip_vec = self._clip_text_features(query) * np.float32(clip_weight)
        st_vec = self._st_text_features(query) * np.float32(st_weight)
        return _l2_normalize(np.concatenate([clip_vec, st_vec]))

    def encode_image(
        self, image: Image.Image, clip_weight: float = 1.0
    ) -> np.ndarray:
        """896-dim joint vector from image (CLIP image + zero ST component)."""
        clip_vec = self._clip_image_features(image) * np.float32(clip_weight)
        st_vec = np.zeros(384, dtype=np.float32)
        return _l2_normalize(np.concatenate([clip_vec, st_vec]))

    def encode_joint(
        self,
        text: str,
        image: Image.Image,
        text_weight: float,
        clip_weight: float = 1.0,
        st_weight: float = 1.0,
    ) -> np.ndarray:
        """
        896-dim joint vector blending image and text.

        text_weight=1.0 → pure text, text_weight=0.0 → pure image.
        clip_weight / st_weight scale the CLIP and ST components independently.
        """
        img_weight = 1.0 - text_weight
        clip_vec = (
            self._clip_image_features(image) * np.float32(img_weight * clip_weight)
            + self._clip_text_features(text) * np.float32(text_weight * clip_weight)
        )
        st_vec = self._st_text_features(text) * np.float32(text_weight * st_weight)
        return _l2_normalize(np.concatenate([clip_vec, st_vec]))
