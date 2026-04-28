# Met Museum Semantic Search

Semantic search and museum tour routing over the Metropolitan Museum of Art's on-view collection (~44k artworks).

Queries are encoded into a 896-dimensional joint embedding space (CLIP + Sentence-BERT) and matched against pre-built artwork embeddings using GMM-filtered cosine similarity search.

---

## How It Works

**Embedding space** — each artwork is embedded as a concatenation of its CLIP image vector (512-d) and Sentence-BERT text vector (384-d), L2-normalized to 896-d.

**Retrieval** — at query time the query vector is assigned a log-posterior probability against each GMM cluster. The top-N clusters are selected and cosine similarity is computed only within that candidate pool, avoiding a brute-force scan over all 44k artworks.

**Tour routing** — selected artworks are routed through Met gallery coordinates using nearest-neighbour + 2-opt local search, floor by floor.

---

## Setup

### Prerequisites

- [Node.js](https://nodejs.org/en) (if not already installed)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) or [pip](https://pypi.org/project/pip/) for Python dependency management

### 1. Add the joint embeddings file

> [!IMPORTANT]  
> Most artifacts in `embeddings/metart/` are tracked in the repo, but `joint_embeddings.npy` is too large for GitHub. Download it from Google Drive and place it manually in `embeddings/metart/`
> 
> [Download joint_embeddings.npy](https://drive.google.com/drive/folders/1UqgmWO18c2PIWrXasvQcSkwSpj7BCA4B?usp=sharing)

After placing the file, your `embeddings/metart/` directory should look like this:

```
embeddings/metart/
├── joint_embeddings.npy   ← download this from Google Drive
├── gmm_joint_48_100.npz
├── gmm_joint_48_100_indices.json
├── gmm_joint_320_100.npz
├── gmm_joint_320_100_indices.json
├── gmm_manifest.json
├── metadata.csv
└── metadata_post_embedding.csv
```

### 2. Install root-level Python dependencies

Required for notebooks, the Streamlit app, and the embedding pipeline in `src/`:

**Option A — uv**

```bash
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

**Option B — pip**

First, create and activate a virtual environment from the project root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

Then install:

```bash
pip install -r requirements.txt
```

### 3. Install backend dependencies

**Option A — uv**

```bash
cd backend
uv sync
cd ..
```

**Option B — pip**

```bash
cd backend
pip install -e .
cd ..
```

### 4. Install frontend dependencies

```bash
cd frontend
npm i
cd ..
```

---

### Starting the app

### Terminal 1

**If using `uv`**
```bash
# Terminal 1 — backend
cd backend
uv run uvicorn main:app --reload --port 8000
```

**If using `pip`**
```bash
# Terminal 1 — backend
cd backend
source ../.venv/bin/activate  # Windows: ..\.venv\Scripts\activate
uvicorn main:app --reload --port 8000
```
### Terminal 2

```bash
# Terminal 2 — frontend
cd frontend
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000).

---

## Project Structure

```
backend/           FastAPI search + tour routing API
frontend/          Next.js web app
src/
  embedding/       Embedding pipeline (CLIP + Sentence-BERT)
  search/          GMM clustering, retrieval logic
  tuning/          BIC sweep for GMM hyperparameter selection
embeddings/metart/ Pre-built artifacts (npz + json tracked; npy downloaded separately)
notebooks/         EDA and GMM analysis notebooks
```
