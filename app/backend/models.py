from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field


class SearchMode(str, Enum):
    text = "text"
    image = "image"
    joint = "joint"


class ArtworkResult(BaseModel):
    object_id: int
    title: str
    artist_display_name: str | None
    object_date: str | None
    department: str | None
    medium: str | None
    primary_image_small: str | None
    primary_image: str | None
    object_url: str
    score: float = Field(ge=0.0, le=1.0)
    is_highlight: bool


class SearchResponse(BaseModel):
    results: list[ArtworkResult]
    query_mode: SearchMode
    total_results: int
    text_weight: float | None = None


class HealthResponse(BaseModel):
    status: str
    rows: int


@dataclass
class SearchHit:
    row_index: int
    score: float
