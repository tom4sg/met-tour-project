import logging
import sys

import numpy as np
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import CLIPModel, CLIPProcessor

logger = logging.getLogger(__name__)

TEXT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CLIP_MODEL_NAME = "openai/clip-vit-base-patch32"


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    """L2-normalize a 1D vector to unit length."""
    norm = np.linalg.norm(vec)
    if norm == 0.0:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


class QueryEncoder:
    def __init__(self) -> None:
        # Load sentence-transformer for text encoding
        try:
            self._text_model = SentenceTransformer(TEXT_MODEL_NAME)
        except Exception as exc:
            print(
                f"Failed to load model {TEXT_MODEL_NAME}: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Load CLIP processor + model for image encoding
        try:
            self._clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
            self._clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
            self._clip_model.eval()
        except Exception as exc:
            print(
                f"Failed to load model {CLIP_MODEL_NAME}: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

    def encode_text(self, query: str) -> np.ndarray:
        """Encode a text query into a unit-normalized (384,) float32 vector."""
        with torch.no_grad():
            embedding = self._text_model.encode(
                [query],
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        vec = np.array(embedding[0], dtype=np.float32)
        return _l2_normalize(vec)

    def encode_image(self, image: Image.Image) -> np.ndarray:
        """Encode a PIL image into a unit-normalized (512,) float32 vector."""
        inputs = self._clip_processor(images=image, return_tensors="pt")
        with torch.no_grad():
            features = self._clip_model.get_image_features(**inputs)
        vec = features[0].cpu().numpy().astype(np.float32)
        return _l2_normalize(vec)

    def encode_joint(
        self,
        text_vec: np.ndarray,
        image_vec: np.ndarray,
        text_weight: float,
    ) -> np.ndarray:
        """
        Combine a text vector (384,) and image vector (512,) into a
        unit-normalized joint vector (896,) matching the joint index.

        joint = normalize(concat([text_weight * text_vec, (1 - text_weight) * image_vec]))
        """
        weighted = np.concatenate(
            [text_weight * text_vec, (1.0 - text_weight) * image_vec]
        ).astype(np.float32)
        return _l2_normalize(weighted)
