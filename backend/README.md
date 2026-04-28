# Backend

FastAPI service that powers semantic artwork search and museum tour routing for the Met collection.

## Stack

- **FastAPI** + **Uvicorn**
- **sentence-transformers** (`all-MiniLM-L6-v2`) for text embeddings
- **CLIP** (`openai/clip-vit-base-patch32`) for image embeddings
- **NumPy** for cosine-similarity search over pre-built embedding matrices
- **httpx** for async Met API calls (gallery number lookup)
- **pydantic-settings** for config

## File Tree

```
backend/
├── main.py          # FastAPI app — lifespan startup, CORS, GET /health, POST /search
├── tour.py          # POST /tour — gallery-number fetch, nearest-neighbour routing, 2-opt, stop grouping
├── index.py         # EmbeddingIndex — loads .npy matrices + metadata.csv, runs cosine search
├── encoder.py       # QueryEncoder — encodes text (MiniLM) and images (CLIP) to unit vectors
├── models.py        # Pydantic models and dataclasses shared across modules
├── config.py        # Settings (EMBEDDINGS_DIR, HOST, PORT, ALLOWED_ORIGINS) via .env
└── tests/
    └── test_tour_routing.py
```

## How It Works

### Startup (`main.py` lifespan)

On boot the app loads three pre-built embedding matrices from `data/embeddings/`:

| File                   | Shape    | Used for                |
| ---------------------- | -------- | ----------------------- |
| `text_embeddings.npy`  | (N, 384) | text-mode search        |
| `clip_embeddings.npy`  | (M, 512) | image-mode search       |
| `joint_embeddings.npy` | (M, 896) | joint text+image search |

`metadata.csv` is loaded alongside and enriched with gallery numbers from `data/processed/met_on_view.csv` when available.

### `POST /search`

1. Validates `mode` (`text` / `image` / `joint`), `top_k`, `text_weight`, and input presence.
2. `QueryEncoder` encodes the query:
   - **text** → MiniLM → 384-d unit vector
   - **image** → CLIP → 512-d unit vector
   - **joint** → weighted concat of both → 896-d unit vector
3. `EmbeddingIndex.search()` computes dot-product similarity (matrices are pre-normalised) and returns the top-k row indices.
4. Metadata is looked up per hit and returned as `ArtworkResult` objects.

### `POST /tour` (`tour.py`)

1. Receives a list of `TourArtworkInput` objects (from search results).
2. Fetches live gallery numbers from the Met Collection API in parallel (up to 80 concurrent requests), using an in-process cache.
3. Filters out Cloisters artworks and any with no resolvable coordinates.
4. Runs **nearest-neighbour greedy routing** floor-by-floor (Floor 1 → Floor 2), starting from the Great Hall entrance.
5. Applies **2-opt** local search within each floor to remove path crossings.
6. Groups consecutive artworks by gallery/department into `GalleryStop` objects.
7. Returns `TourResponse` with stops, counts, and per-stop `(x, y, floor)` coordinates for the frontend map.

### Coordinate system

`ROOM_COORDS` in `tour.py` maps ~400 Met gallery numbers to `(x, y, floor)` on a 0–10 scale. Floor changes are penalised by multiplying the floor number by `FLOOR_PENALTY = 8.0` so the Euclidean distance naturally discourages unnecessary floor switches. `DEPARTMENT_COORDS` provides centroid fallbacks when a gallery number is absent.

### Environment

Copy `.env.example` to `.env`:

```
EMBEDDINGS_DIR=../../data/embeddings
ALLOWED_ORIGINS=http://localhost:3000
HOST=0.0.0.0
PORT=8000
```

## Running

```bash
uv sync
uv run uvicorn main:app --reload   # http://localhost:8000
```

## Tests

```bash
uv run pytest
```
