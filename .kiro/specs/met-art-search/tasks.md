# Implementation Plan: MET Art Search

## Overview

Build a full-stack semantic art search application: a FastAPI backend that loads pre-computed embeddings at startup and serves cosine-similarity search, and a Next.js frontend with MET museum aesthetics and three search modes (text, image, joint).

## Tasks

- [x] 1. Bootstrap project structure and configuration
  - Create `app/backend/` and `app/frontend/` directory skeletons
  - Create `app/backend/config.py` using `pydantic-settings`; read `EMBEDDINGS_DIR` (default `data/embeddings`), `HOST` (default `0.0.0.0`), `PORT` (default `8000`), `ALLOWED_ORIGINS` (default `http://localhost:3000`)
  - Create `app/backend/requirements.txt` with: `fastapi`, `uvicorn[standard]`, `numpy`, `pandas`, `torch`, `transformers`, `sentence-transformers`, `Pillow`, `pydantic-settings`, `hypothesis`, `pytest`, `pytest-asyncio`, `httpx`
  - Scaffold `app/frontend/package.json`, `tailwind.config.ts`, `tsconfig.json`, and `app/frontend/app/globals.css` with MET CSS variables (`--met-red: #E31837`, `--met-cream: #F5F0E8`, `--met-charcoal: #1A1A1A`, `--met-gold: #C9A84C`)
  - Create `app/frontend/types/search.ts` with TypeScript types mirroring `SearchMode`, `ArtworkResult`, `SearchResponse`, `SearchParams`
  - _Requirements: 6.1, 6.2, 10.1, 10.2, 10.3, 10.4_

- [x] 2. Implement backend data models and Pydantic schemas
  - [x] 2.1 Create `app/backend/models.py`
    - Define `SearchMode` enum (`text`, `image`, `joint`)
    - Define `ArtworkResult` with all required fields: `object_id`, `title`, `artist_display_name`, `object_date`, `department`, `medium`, `primary_image_small`, `primary_image`, `object_url`, `score`, `is_highlight`
    - Define `SearchResponse` (`results`, `query_mode`, `total_results`, `text_weight`)
    - Define `HealthResponse` (`status`, `rows`)
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 3. Implement EmbeddingIndex
  - [x] 3.1 Create `app/backend/index.py` with `EmbeddingIndex` class
    - `load(embeddings_dir)`: read `manifest.json`, load all three `.npy` files, validate row counts against manifest, L2-normalize all matrices in-place; exit with non-zero status and descriptive stderr message on missing file or row-count mismatch
    - `search(query_vec, mode, top_k)`: select matrix by mode, compute `scores = matrix @ query_vec`, argsort descending, return top-K `SearchHit` objects with row index and score
    - Build separate row-to-objectID mappings for text, CLIP, and joint indices from the metadata DataFrame
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.2, 3.2, 3.6, 4.3_

  - [ ]* 3.2 Write property test: manifest row count validation (Property 1)
    - **Property 1: Manifest row count validation**
    - **Validates: Requirements 1.2, 1.4**
    - Use `hypothesis` to generate arbitrary `(n_rows, manifest_rows)` pairs; assert validation accepts iff `n_rows == manifest_rows`

  - [ ]* 3.3 Write property test: index normalization invariant (Property 2)
    - **Property 2: Index normalization invariant**
    - **Validates: Requirements 1.5**
    - Generate random float32 matrices; after calling the normalization routine, assert every row has L2 norm within 1e-5 of 1.0

  - [ ]* 3.4 Write property test: search returns true top-K sorted descending (Property 5)
    - **Property 5: Search correctness — true top-K, sorted descending**
    - **Validates: Requirements 2.2, 3.2, 4.3, 5.4**
    - Generate random unit-normalized matrices and query vectors; assert returned scores equal the true top-K dot products, sorted non-increasing

  - [ ]* 3.5 Write property test: top_k result count invariant (Property 6)
    - **Property 6: top_k result count invariant**
    - **Validates: Requirements 2.5, 3.7, 4.8**
    - For any valid `top_k` ∈ {10, 20, 50, 100} and index of size N, assert `len(results) == min(top_k, N)`

- [x] 4. Implement QueryEncoder
  - [x] 4.1 Create `app/backend/encoder.py` with `QueryEncoder` class
    - Load `sentence-transformers/all-MiniLM-L6-v2` and `openai/clip-vit-base-patch32` once at instantiation; log and exit on model load failure
    - `encode_text(query: str) -> np.ndarray`: encode with sentence-transformer, L2-normalize, return float32 (384,)
    - `encode_image(image: PIL.Image.Image) -> np.ndarray`: encode with CLIP processor + model, L2-normalize, return float32 (512,)
    - `encode_joint(text_vec, image_vec, text_weight) -> np.ndarray`: compute `normalize(text_weight * text_vec + (1 - text_weight) * image_vec)`, return float32 (896,)
    - _Requirements: 2.1, 3.1, 4.1, 4.2_

  - [ ]* 4.2 Write property test: text encoder output invariant (Property 3)
    - **Property 3: Text encoder output invariant**
    - **Validates: Requirements 2.1**
    - Generate arbitrary non-empty strings; assert output shape is (384,), dtype float32, L2 norm within 1e-5 of 1.0

  - [ ]* 4.3 Write property test: image encoder output invariant (Property 4)
    - **Property 4: Image encoder output invariant**
    - **Validates: Requirements 3.1**
    - Generate arbitrary RGB PIL images (varied sizes/pixel values); assert output shape is (512,), dtype float32, L2 norm within 1e-5 of 1.0

  - [ ]* 4.4 Write property test: joint vector construction (Property 10)
    - **Property 10: Joint vector construction**
    - **Validates: Requirements 4.2**
    - Generate unit-normalized (384,) and (512,) vectors and `text_weight` ∈ [0.0, 1.0]; assert output equals `normalize(text_weight * t + (1 - text_weight) * v)` with L2 norm within 1e-5 of 1.0

- [x] 5. Implement FastAPI app and routes
  - [x] 5.1 Create `app/backend/main.py`
    - Use `lifespan` context manager to instantiate `EmbeddingIndex` and `QueryEncoder` at startup, store in `app.state`
    - Configure CORS middleware using `ALLOWED_ORIGINS` from config
    - Implement `GET /health` → `HealthResponse` with `status: "ok"` and `rows` from loaded index
    - Implement `POST /search` (multipart/form-data): validate `mode`, `query`, `image`, `top_k`, `text_weight`; dispatch to correct encoder path; call `index.search()`; build and return `SearchResponse`
    - Enforce all validation rules: whitespace query → 422, invalid image format/size → 422, invalid `top_k` → 422, `text_weight` out of range → 422, joint mode missing text or image → 422 with exact error messages from design
    - _Requirements: 1.1, 2.4, 2.5, 3.3, 3.4, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 9.1, 9.2, 9.3, 10.2, 10.4_

  - [ ]* 5.2 Write property test: whitespace query rejection (Property 7)
    - **Property 7: Whitespace query rejection**
    - **Validates: Requirements 2.4**
    - Generate strings composed entirely of whitespace characters; assert POST /search returns HTTP 422

  - [ ]* 5.3 Write property test: image upload validation (Property 8)
    - **Property 8: Image upload validation**
    - **Validates: Requirements 3.3, 3.4**
    - Generate valid JPEG/PNG/WebP images ≤10 MB (accept) and invalid files or oversized images (reject with 422)

  - [ ]* 5.4 Write property test: CLIP-only results for image mode (Property 9)
    - **Property 9: CLIP-only results for image mode**
    - **Validates: Requirements 3.6**
    - For any image search result, assert every returned artwork has `clip_embedding_status == "embedded"` in metadata

  - [ ]* 5.5 Write property test: text_weight range validation (Property 11)
    - **Property 11: text_weight range validation**
    - **Validates: Requirements 4.4**
    - Generate floats in [0.0, 1.0] (accept) and floats outside that range (reject with 422)

  - [ ]* 5.6 Write property test: search response schema invariants (Property 12)
    - **Property 12: Search response schema invariants**
    - **Validates: Requirements 5.1, 5.2, 5.3**
    - For any valid search request across all modes, assert response contains all required fields with correct types; assert `text_weight` present iff `query_mode == "joint"`

  - [ ]* 5.7 Write unit tests for backend example cases
    - Startup exits non-zero when embedding files are missing (Req 1.3)
    - Joint mode returns exact error messages for missing text / missing image (Req 4.5, 4.6)
    - `GET /health` returns `{"status": "ok", "rows": N}` (Req 9.1)
    - CORS preflight OPTIONS returns correct headers (Req 9.3)
    - Default `top_k` is 20 when not specified (Req 2.5, 3.7, 4.8)
    - Default `text_weight` is 0.5 when not specified (Req 4.4)

- [x] 6. Checkpoint — backend complete
  - Ensure all backend tests pass: `pytest app/backend/tests/ --hypothesis-seed=0`
  - Verify `GET /health` responds correctly and `POST /search` handles all three modes
  - Ask the user if questions arise before proceeding to frontend.

- [x] 7. Implement frontend API client and types
  - [x] 7.1 Create `app/frontend/lib/api.ts`
    - Implement `searchArtworks(params: SearchParams): Promise<SearchResponse>`
    - Build `FormData` with `mode`, optional `query`, optional `image` file, `top_k`, optional `text_weight`
    - POST to `NEXT_PUBLIC_API_URL/search`; parse JSON; throw typed `ApiError` on non-2xx responses, parsing `detail` field from 422 responses
    - _Requirements: 9.2, 10.3_

- [x] 8. Implement frontend components
  - [x] 8.1 Create `app/frontend/components/ArtworkCard.tsx`
    - Display artwork image (with `onError` fallback to MET placeholder), title, artist display name (or placeholder if null), object date, department
    - Entire card links to `object_url` opening in a new tab
    - Minimum touch target 44×44px; apply MET color palette
    - _Requirements: 8.2, 8.3, 8.4_

  - [ ]* 8.2 Write property test: ArtworkCard renders required fields (Property 13)
    - **Property 13: ArtworkCard renders required fields**
    - **Validates: Requirements 8.2**
    - Use Jest + RTL; for any `ArtworkResult` object, assert rendered output contains title, artist name (or placeholder), object date, and department

  - [x] 8.3 Create `app/frontend/components/ResultsGrid.tsx`
    - Responsive CSS grid: 1 col <375px, 2 col ≥375px, 3 col ≥768px, 4 col ≥1280px
    - Display result count string "Showing {n} of {total} artworks"
    - Render "No artworks found. Try a different search." when results array is empty
    - _Requirements: 8.1, 8.5, 8.6_

  - [x] 8.4 Create `app/frontend/components/SearchForm.tsx`
    - Manage state: `mode`, `query`, `imageFile`, `textWeight`, `topK`
    - Mode selector with three options: "Text", "Image", "Text + Image" (default "Text")
    - Text input disabled and visually inactive when mode is "Image"; image upload disabled when mode is "Text"
    - Weight slider (0.0–1.0, default 0.5) labeled "Text ← Weight → Image", visible only in "Text + Image" mode
    - Top-K selector: 10 / 20 / 50 / 100, default 20
    - Image upload shows thumbnail preview before submission
    - Client-side validation before API call: empty text in Text mode → "Please enter a search query"; no image in Image mode → "Please upload an image"; incomplete joint → "Text + Image mode requires both a query and an image"
    - All interactive controls minimum 44×44px touch targets
    - Call `searchArtworks()` on valid submit; lift results to parent via `onResults` callback
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12_

  - [x] 8.5 Create `app/frontend/components/LoadingState.tsx`
    - Animated loading indicator displayed while search is in progress
    - _Requirements: 6.5_

  - [x] 8.6 Create `app/frontend/components/HeroSection.tsx`
    - Pre-search hero with featured artwork image and introductory tagline
    - Mobile-first layout, scales to full-width on larger viewports
    - _Requirements: 6.6_

  - [ ]* 8.7 Write component tests for SearchForm (Jest + RTL)
    - Image upload disabled when mode is "Text" (Req 7.4)
    - Text input disabled when mode is "Image" (Req 7.5)
    - Both controls enabled when mode is "Text + Image" (Req 7.6)
    - Inline validation message for empty text in Text mode (Req 7.9)
    - Inline validation message for missing image in Image mode (Req 7.10)
    - Inline validation message for incomplete joint mode (Req 7.11)

  - [ ]* 8.8 Write component tests for ResultsGrid (Jest + RTL)
    - Shows "No artworks found." when results array is empty (Req 8.6)
    - Displays correct count string (Req 8.5)

  - [ ]* 8.9 Write snapshot tests
    - Snapshot tests for `ArtworkCard`, `HeroSection`, `LoadingState` for visual regression

- [x] 9. Implement Next.js root layout and home page
  - [x] 9.1 Create `app/frontend/app/layout.tsx`
    - Root layout with serif heading font and sans-serif body font
    - Header with "The Metropolitan Museum of Art" and "Collection Search" subtitle in MET typographic style
    - Apply MET color palette via CSS variables from `globals.css`
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 9.2 Create `app/frontend/app/page.tsx`
    - Render `HeroSection` when no search has been performed
    - Render `SearchForm` with `onResults` callback
    - Render `LoadingState` while request is in progress
    - Render `ResultsGrid` with results once returned
    - Display API error banner for 422 detail messages; display generic "Something went wrong. Please try again." for network errors / 500s
    - _Requirements: 6.4, 6.5, 6.6, 8.1_

- [x] 10. Final checkpoint — full stack wired together
  - Ensure all frontend tests pass: `jest app/frontend/ --testPathPattern="\.test\.(ts|tsx)$" --passWithNoTests`
  - Ensure all backend tests pass: `pytest app/backend/tests/ --hypothesis-seed=0`
  - Verify the frontend `SearchForm` correctly calls `api.ts`, results render in `ResultsGrid`, and all three search modes work end-to-end
  - Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation before moving to the next layer
- Property tests use `@settings(max_examples=100)` with `--hypothesis-seed=0` for reproducible CI runs
- Backend tests live in `app/backend/tests/`; frontend tests co-located with components as `*.test.tsx`
