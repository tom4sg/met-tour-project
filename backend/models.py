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
    gallery_number: str | None = None



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


class TourArtworkInput(BaseModel):
    object_id: int
    title: str
    artist_display_name: str | None = None
    primary_image_small: str | None = None
    object_url: str
    department: str | None = None
    gallery_number: str | None = None


class TourArtwork(BaseModel):
    object_id: int
    title: str
    artist_display_name: str | None
    primary_image_small: str | None
    object_url: str
    gallery_number: str | None = None


class GalleryStop(BaseModel):
    stop_label: str
    floor: int
    x: float = 0.0  # routing coordinate x (0–10 scale)
    y: float = 0.0  # routing coordinate y (0–10 scale)
    artworks: list[TourArtwork]


class TourRequest(BaseModel):
    artworks: list[TourArtworkInput] = Field(min_length=1, max_length=100)


class TourResponse(BaseModel):
    stops: list[GalleryStop]
    total_input: int
    routable_count: int
    excluded_count: int
