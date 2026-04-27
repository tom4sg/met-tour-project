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

Before anything, make sure you have downloaded the necessary files folder containing embeddings, metadata and GMM artifacts, which can be found in the Google Drive here: [Download](https://drive.google.com/drive/folders/1UqgmWO18c2PIWrXasvQcSkwSpj7BCA4B?usp=sharing)

Also, if you don't have Node.js already, download it here: [nodejs.org](https://nodejs.org/en)

Now, assuming you're in the project directory and have replaced the embeddings directory with the files from Google Drive, proceed below!

```bash
# In project root
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
# Terminal 1 — backend (from project root)
cd backend
uvicorn main:app --reload --port 8000
```

```bash
# Terminal 2 — frontend (from frontend/)
cd frontend
npm install
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Project Structure

```
backend/          FastAPI search + tour routing API
frontend/         Next.js web app
src/
  embedding/      Embedding pipeline (CLIP + Sentence-BERT)
  search/         GMM clustering, retrieval logic
  tuning/         BIC sweep for GMM hyperparameter selection
embeddings/metart/ Pre-built artifacts (downloaded from Google Drive)
notebooks/        EDA and GMM analysis notebooks
```
