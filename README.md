# Final project

Machine learning course final project. This repository is set up for a **Streamlit** search application; the app itself is not implemented yet.

## Layout

| Path | Purpose |
|------|---------|
| `app/` | Streamlit entrypoint and UI code (to be added) |
| `src/` | Shared Python modules (search, indexing, utilities) |
| `data/raw/` | Raw datasets (ignored by git; use `.gitkeep` to keep the folder) |
| `data/processed/` | Processed artifacts (ignored by git) |
| `notebooks/` | Jupyter notebooks for exploration |
| `tests/` | Unit tests |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for environment variables; copy to `.env` |

## Setup

1. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -U pip
   pip install -r requirements.txt
   ```

2. Copy environment template and add any API keys or local settings:

   ```bash
   cp .env.example .env
   ```

3. When the Streamlit app exists, run it from the project root (exact filename will depend on what you add under `app/`).

## Git

Only `.env.example` is tracked. Your real `.env` and Streamlit `secrets.toml` stay local (see `.gitignore`).
