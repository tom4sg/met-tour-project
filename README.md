# Final project

Machine learning course final project: repo layout and dependencies are in place for a future Streamlit search app, which is not built yet. So far, exploration lives in notebooks (e.g. Hugging Face dense text embeddings and CLIP smoke tests in `notebooks/` and `embed.ipynb`).

## Met collection fetch (`src/fetch_met_collection.py`)

From the repo root, activate the venv, then run with **`--group`** (required):

```bash
cd final-project   # your clone path
source .venv/bin/activate
python src/fetch_met_collection.py \
  --group 3 \
  --direction reverse \
  --limit 10000 \
  --chunk 100 \
  --rps 40 \
  --out data/processed/met_collection_api.csv
```

- **`--group` `1`–`5`:** Object IDs come from **`data/processed/met_object_id_groups.csv`** (columns `objectID`, `group`). That file is produced by `python src/split_met_object_ids.py` and maps every API object ID to one of five shards so teammates can split work. Change `3` to `1`, `2`, `4`, or `5` for another shard.
- **`--group` `ALL`:** Loads the full ID list from the Met API (`/objects`); no groups CSV used.

**Flags (same for a numeric group or `ALL`):**

| Flag | Role |
|------|------|
| `--direction` | `forward` = walk IDs from the start of the current scope; `reverse` = from the end (with `--limit`, that scope is only the last *N* IDs). |
| `--limit` | Optional cap: first *N* IDs (`forward`) or last *N* (`reverse`) within that scope. Omit to fetch the whole scope. |
| `--chunk` | Append to the output CSV every *N* successful rows so progress isn’t lost if the run stops. |
| `--rps` | Max requests per second to the API (Met suggests ≤80). |
| `--out` | Output CSV path. Re-runs **resume**: IDs already in this file are skipped. |

Optional: **`--groups-csv`** — path to the mapping file (default `data/processed/met_object_id_groups.csv`) when `--group` is `1`–`5`.

**`ALL` example** (full API list, same flag meanings):

```bash
python src/fetch_met_collection.py --group ALL --direction forward --limit 10000 \
  --chunk 100 --rps 40 --out data/processed/met_collection_api.csv
```

