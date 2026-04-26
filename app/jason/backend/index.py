import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from models import SearchHit, SearchMode


class EmbeddingIndex:
    text_matrix: np.ndarray  # shape (44973, 384), float32, unit-normalized
    clip_matrix: (
        np.ndarray
    )  # shape (30724, 512), float32, unit-normalized (embedded rows only)
    joint_matrix: (
        np.ndarray
    )  # shape (30724, 896), float32, unit-normalized (embedded rows only)
    metadata: pd.DataFrame  # full metadata, indexed by row position
    manifest: dict

    # Row-to-position mappings (position = integer row index in metadata df)
    text_row_to_pos: np.ndarray  # identity: [0, 1, 2, ...] for all 44973 rows
    clip_row_to_pos: np.ndarray  # positions of embedded rows in the full df
    joint_row_to_pos: np.ndarray  # same as clip_row_to_pos

    def load(self, embeddings_dir: Path) -> None:
        """Load and normalize all embedding matrices and metadata from disk."""
        manifest_path = embeddings_dir / "manifest.json"
        if not manifest_path.exists():
            print(f"Missing embedding file: {manifest_path}", file=sys.stderr)
            sys.exit(1)

        with open(manifest_path) as f:
            self.manifest = json.load(f)

        expected_rows = self.manifest["rows"]  # 44973 for all three files

        # Load and validate all three matrices — all have shape (44973, dim)
        matrices = {}
        for filename, key in [
            ("text_embeddings.npy", "text"),
            ("clip_embeddings.npy", "clip"),
            ("joint_embeddings.npy", "joint"),
        ]:
            path = embeddings_dir / filename
            if not path.exists():
                print(f"Missing embedding file: {path}", file=sys.stderr)
                sys.exit(1)
            m = np.load(path)
            if m.shape[0] != expected_rows:
                print(
                    f"Row count mismatch for {filename}: expected {expected_rows}, got {m.shape[0]}",
                    file=sys.stderr,
                )
                sys.exit(1)
            matrices[key] = m

        # Load metadata
        metadata_path = embeddings_dir / "metadata.csv"
        if not metadata_path.exists():
            print(f"Missing embedding file: {metadata_path}", file=sys.stderr)
            sys.exit(1)

        df = pd.read_csv(metadata_path)

        # Extract objectID from objectURL (e.g. https://…/search/460813 → 460813)
        df["objectID"] = df["objectURL"].str.extract(r"/(\d+)$")[0].astype("Int64")

        # Enrich with GalleryNumber from met_on_view.csv if available
        on_view_path = metadata_path.parent.parent / "processed" / "met_on_view.csv"
        if on_view_path.exists():
            on_view = pd.read_csv(
                on_view_path,
                usecols=["objectID", "GalleryNumber"],
                dtype={"objectID": "Int64", "GalleryNumber": str},
            )
            on_view["GalleryNumber"] = on_view["GalleryNumber"].str.strip()
            on_view = on_view[
                on_view["GalleryNumber"].notna() & (on_view["GalleryNumber"] != "")
            ]
            df = df.merge(on_view, on="objectID", how="left")
        else:
            df["GalleryNumber"] = None

        # Build the CLIP-embedded mask
        clip_mask = (df["clip_embedding_status"] == "embedded").to_numpy()
        clip_positions = np.where(clip_mask)[0]  # integer positions in df

        # Extract sub-matrices for image/joint search (only embedded rows)
        clip_sub = matrices["clip"].astype(np.float32)[clip_mask]
        joint_sub = matrices["joint"].astype(np.float32)[clip_mask]

        # L2-normalize all matrices
        def _normalize(m: np.ndarray) -> np.ndarray:
            norms = np.linalg.norm(m, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1.0, norms)
            return m / norms

        self.text_matrix = _normalize(matrices["text"].astype(np.float32))
        self.clip_matrix = _normalize(clip_sub)
        self.joint_matrix = _normalize(joint_sub)

        # Row-to-position mappings (used in get_artwork to iloc into df)
        self.text_row_to_pos = np.arange(len(df), dtype=np.int64)
        self.clip_row_to_pos = clip_positions
        self.joint_row_to_pos = clip_positions.copy()

        # Store full dataframe (positional access via iloc)
        self.metadata = df.reset_index(drop=True)

    def search(
        self, query_vec: np.ndarray, mode: SearchMode, top_k: int
    ) -> list[SearchHit]:
        """Return top_k results by cosine similarity."""
        if mode == SearchMode.text:
            matrix = self.text_matrix
        elif mode == SearchMode.image:
            matrix = self.clip_matrix
        else:
            matrix = self.joint_matrix

        scores = matrix @ query_vec
        sorted_indices = np.argsort(scores)[::-1]
        top_indices = sorted_indices[:top_k]

        return [
            SearchHit(row_index=int(idx), score=float(scores[idx]))
            for idx in top_indices
        ]

    def get_artwork(self, row_index: int, mode: SearchMode) -> dict:
        """Look up artwork metadata by search-result row index."""
        if mode == SearchMode.text:
            pos = int(self.text_row_to_pos[row_index])
        elif mode == SearchMode.image:
            pos = int(self.clip_row_to_pos[row_index])
        else:
            pos = int(self.joint_row_to_pos[row_index])

        row = self.metadata.iloc[pos]

        def _str_or_none(col: str) -> str | None:
            val = row.get(col)
            if (
                val is None
                or (isinstance(val, float) and pd.isna(val))
                or str(val).strip() == ""
            ):
                return None
            return str(val)

        def _bool_val(col: str) -> bool:
            val = row.get(col)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return False
            if isinstance(val, bool):
                return val
            return str(val).strip().lower() in ("true", "1", "yes", "public domain")

        # Derive object_id from objectURL
        object_url = str(row.get("objectURL", ""))
        import re

        m = re.search(r"/(\d+)$", object_url)
        object_id = int(m.group(1)) if m else pos

        return {
            "object_id": object_id,
            "title": _str_or_none("title") or "",
            "artist_display_name": _str_or_none("artistDisplayName"),
            "object_date": _str_or_none("objectBeginDate"),
            "department": _str_or_none("department"),
            "medium": _str_or_none("medium"),
            "primary_image_small": _str_or_none("primaryImageSmall"),
            "primary_image": _str_or_none("primaryImage"),
            "object_url": object_url,
            "is_highlight": _bool_val("isHighlight_converted"),
            "gallery_number": _str_or_none("GalleryNumber"),
        }
