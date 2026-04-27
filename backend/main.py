import io
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from config import settings
from encoder import QueryEncoder
from index import EmbeddingIndex
from models import ArtworkResult, HealthResponse, SearchMode, SearchResponse
from tour import router as tour_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    index = EmbeddingIndex()
    index.load(Path(settings.EMBEDDINGS_DIR), Path(settings.METADATA_PATH))
    encoder = QueryEncoder()
    app.state.index = index
    app.state.encoder = encoder
    app.state.gallery_cache = {}
    yield


app = FastAPI(title="MET Art Search API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(tour_router)



@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    index: EmbeddingIndex = app.state.index
    return HealthResponse(status="ok", rows=index.joint_matrix.shape[0])


@app.post("/search", response_model=SearchResponse)
async def search(
    mode: str = Form(...),
    query: str | None = Form(None),
    image: UploadFile | None = File(None),
    top_k: int = Form(20),
    text_weight: float = Form(0.5),
    clip_weight: float = Form(1.0),
    st_weight: float = Form(1.0),
    top_clusters: int = Form(2),
) -> SearchResponse:
    # Validate mode
    if mode not in {"text", "image", "joint"}:
        raise HTTPException(422, "mode must be one of: text, image, joint")

    # Validate top_k
    if top_k < 1 or top_k > 100:
        raise HTTPException(422, "top_k must be between 1 and 100")

    # Validate text_weight
    if text_weight < 0.0 or text_weight > 1.0:
        raise HTTPException(422, "text_weight must be between 0.0 and 1.0")

    # Mode-specific input validation
    if mode == "text":
        if query is None or query.strip() == "":
            raise HTTPException(422, "Query string must not be empty")

    elif mode == "image":
        if image is None:
            raise HTTPException(422, "Please upload an image")

    elif mode == "joint":
        missing_text = query is None or query.strip() == ""
        missing_image = image is None
        if missing_text and missing_image:
            raise HTTPException(
                422,
                "Joint mode requires both a text query and an image; provide an image or switch to text mode.",
            )
        if missing_text:
            raise HTTPException(
                422,
                "Joint mode requires both a text query and an image; provide a text query or switch to image mode.",
            )
        if missing_image:
            raise HTTPException(
                422,
                "Joint mode requires both a text query and an image; provide an image or switch to text mode.",
            )

    # Image validation (for image and joint modes)
    pil_image: Image.Image | None = None
    if image is not None:
        image_bytes = await image.read()

        # Check file size
        if len(image_bytes) > 10 * 1024 * 1024:
            raise HTTPException(422, "Image file size must not exceed 10 MB")

        # Check content type
        if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(422, "Image must be JPEG, PNG, or WebP")

        # Validate it's a real image
        try:
            pil_image = Image.open(io.BytesIO(image_bytes))
            pil_image.verify()
            # Re-open after verify (verify closes the image)
            pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception:
            raise HTTPException(422, "Image must be JPEG, PNG, or WebP")

    # Encode and search
    index: EmbeddingIndex = app.state.index
    encoder: QueryEncoder = app.state.encoder
    search_mode = SearchMode(mode)

    if mode == "text":
        query_vec = encoder.encode_text(query, clip_weight=clip_weight, st_weight=st_weight)
    elif mode == "image":
        query_vec = encoder.encode_image(pil_image, clip_weight=clip_weight)
    else:  # joint
        query_vec = encoder.encode_joint(
            query, pil_image, text_weight,
            clip_weight=clip_weight, st_weight=st_weight,
        )

    hits = index.search(query_vec, search_mode, top_k, top_clusters=top_clusters)

    results = []
    for hit in hits:
        metadata = index.get_artwork(hit.row_index, search_mode)
        results.append(ArtworkResult(score=hit.score, **metadata))

    return SearchResponse(
        results=results,
        query_mode=search_mode,
        total_results=len(results),
        text_weight=text_weight if mode == "joint" else None,
    )


if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
