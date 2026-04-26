# MET Art Search — Backend

FastAPI backend serving cosine-similarity search over pre-computed MET collection embeddings.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — install via `pip install uv` or `brew install uv`

## Setup

```bash
cd app/backend

# Create virtual environment and install all dependencies
uv sync

# Install with dev dependencies (tests)
uv sync --extra dev
```

## Running

```bash
# Copy and edit environment config
cp .env.example .env

# Start the server
uv run python main.py

# Or with uvicorn directly
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at http://localhost:8000.

## Testing

```bash
uv run pytest --hypothesis-seed=0
```

## Endpoints

- `GET /health` — health check with row count
- `POST /search` — multipart/form-data search (fields: `mode`, `query`, `image`, `top_k`, `text_weight`)

## Environment Variables

| Variable          | Default                 | Description                          |
| ----------------- | ----------------------- | ------------------------------------ |
| `EMBEDDINGS_DIR`  | `data/embeddings`       | Path to the embeddings directory     |
| `HOST`            | `0.0.0.0`               | Server bind host                     |
| `PORT`            | `8000`                  | Server port                          |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS allowed origins |
