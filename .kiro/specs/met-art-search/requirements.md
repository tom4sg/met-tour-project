# Requirements Document

## Introduction

This feature delivers a full-stack semantic art search application for the Metropolitan Museum of Art collection. A FastAPI backend loads pre-computed CLIP image embeddings, sentence-transformer text embeddings, and joint (image + text) embeddings from disk, then serves cosine-similarity search over ~45,000 artworks. A Next.js frontend provides an elegant, museum-quality interface that lets visitors search by text query, uploaded image, or a combination of both, and browse the top matching artworks with rich metadata.

The backend reads from:
- `data/embeddings/clip_embeddings.npy` — 512-dim CLIP image embeddings (30,724 artworks have image embeddings)
- `data/embeddings/text_embeddings.npy` — 384-dim sentence-transformer text embeddings
- `data/embeddings/joint_embeddings.npy` — 896-dim concatenated joint embeddings
- `data/embeddings/manifest.json` — index metadata (row count, model names, dims)
- `data/embeddings/metadata.csv` — per-artwork metadata (title, artist, date, department, image URLs, MET object URL, etc.)

---

## Glossary

- **Search_API**: The FastAPI backend service that handles embedding inference and similarity search.
- **Search_UI**: The Next.js frontend application presented to the end user.
- **Query_Encoder**: The component within Search_API responsible for encoding a user's text or image input into an embedding vector using the same models used during indexing (sentence-transformers/all-MiniLM-L6-v2 for text, openai/clip-vit-base-patch32 for images).
- **Similarity_Engine**: The component within Search_API that performs cosine similarity between the query embedding and the stored embedding matrix, returning ranked results.
- **Artwork_Card**: A UI component in Search_UI that displays a single artwork result including its image, title, artist, date, department, and a link to the MET website.
- **Search_Mode**: One of three modes — `text`, `image`, or `joint` — that determines which embedding space is used for retrieval. Each mode uses a distinct, non-overlapping embedding index; no silent cross-mode fallback occurs.
- **Top_K**: The number of top-ranked results returned by a search query (default 20, user-selectable from 10, 20, 50, or 100).
- **Joint_Query**: A search that combines a text embedding and an image embedding via weighted combination, normalized to unit length, then matched against the joint embedding index.
- **Text_Weight**: A float in the range [0.0, 1.0] (default 0.5) that controls the relative contribution of the text embedding in a joint query. The image weight is implicitly `1 - text_weight`.
- **Embedding_Index**: The in-memory numpy array of pre-computed embeddings loaded at server startup.
- **Manifest**: The `manifest.json` file describing the embedding dimensions, model names, and row counts.

---

## Requirements

### Requirement 1: Backend Startup and Embedding Index Loading

**User Story:** As a developer, I want the Search_API to load all embedding indices and metadata into memory at startup, so that search queries are served with low latency without re-reading files on every request.

#### Acceptance Criteria

1. WHEN the Search_API process starts, THE Search_API SHALL load `clip_embeddings.npy`, `text_embeddings.npy`, `joint_embeddings.npy`, and `metadata.csv` into memory before accepting any search requests.
2. WHEN the Search_API process starts, THE Search_API SHALL read `manifest.json` and validate that the number of rows in each `.npy` file matches the `rows` field in the Manifest.
3. IF any embedding file is missing or unreadable at startup, THEN THE Search_API SHALL log a descriptive error message and exit with a non-zero status code.
4. IF the row count of any loaded `.npy` file does not match the Manifest `rows` field, THEN THE Search_API SHALL log a descriptive mismatch error and exit with a non-zero status code.
5. WHEN the Embedding_Index is loaded, THE Search_API SHALL normalize all embedding vectors to unit length to enable cosine similarity via dot product.

---

### Requirement 2: Text Search

**User Story:** As a museum visitor, I want to type a natural-language description or keyword and find artworks that match, so that I can discover pieces relevant to my interests without knowing specific titles or artists.

#### Acceptance Criteria

1. WHEN a text search request is received with a non-empty query string and Search_Mode `text`, THE Query_Encoder SHALL encode the query string using the sentence-transformers/all-MiniLM-L6-v2 model into a 384-dimensional embedding vector.
2. WHEN the query embedding is produced, THE Similarity_Engine SHALL compute cosine similarity between the query embedding and the text Embedding_Index exclusively, returning the Top_K highest-scoring artworks from the full 44,973-artwork text index.
3. THE Search_API SHALL return search results within 2 seconds for any text query against the full index of 44,973 artworks.
4. IF a text search request is received with an empty or whitespace-only query string, THEN THE Search_API SHALL return an HTTP 422 response with a descriptive validation error message.
5. WHERE the client specifies a `top_k` parameter with a value of 10, 20, 50, or 100, THE Search_API SHALL return exactly that many results (or fewer if the index contains fewer artworks); THE Search_API SHALL default to 20 results when no `top_k` parameter is provided.

---

### Requirement 3: Image Search

**User Story:** As a museum visitor, I want to upload a photo or image and find visually similar artworks in the MET collection, so that I can explore art that resembles something I've seen or photographed.

#### Acceptance Criteria

1. WHEN an image search request is received with a valid image file and Search_Mode `image`, THE Query_Encoder SHALL encode the uploaded image using the openai/clip-vit-base-patch32 model into a 512-dimensional embedding vector.
2. WHEN the query embedding is produced, THE Similarity_Engine SHALL compute cosine similarity between the query embedding and the CLIP Embedding_Index exclusively, returning the Top_K highest-scoring artworks from the 30,724 artworks that have CLIP embeddings.
3. THE Search_API SHALL accept image uploads in JPEG, PNG, and WebP formats with a maximum file size of 10 MB.
4. IF an uploaded file is not a valid image or exceeds 10 MB, THEN THE Search_API SHALL return an HTTP 422 response with a descriptive error message.
5. THE Search_API SHALL return image search results within 3 seconds for any image query against the full index.
6. WHEN computing image similarity, THE Similarity_Engine SHALL only score artworks that have a valid CLIP embedding (i.e., artworks with `clip_embedding_status` = `embedded`), returning at most the 30,724 artworks with image embeddings.
7. WHERE the client specifies a `top_k` parameter with a value of 10, 20, 50, or 100, THE Search_API SHALL return exactly that many results (or fewer if the CLIP index contains fewer artworks); THE Search_API SHALL default to 20 results when no `top_k` parameter is provided.

---

### Requirement 4: Joint (Text + Image) Search

**User Story:** As a museum visitor, I want to search using both a text description and an uploaded image simultaneously, so that I can find artworks that match a specific visual style described in words.

#### Acceptance Criteria

1. WHEN a joint search request is received with both a non-empty query string and a valid image file and Search_Mode `joint`, THE Query_Encoder SHALL encode the text into a 384-dimensional vector and the image into a 512-dimensional vector.
2. WHEN both embeddings are produced, THE Query_Encoder SHALL construct the Joint_Query vector as: `normalize(text_weight * text_vec + (1 - text_weight) * image_vec)`, where `text_weight` is the value of the optional `text_weight` request parameter (default 0.5), and then search this normalized vector against the joint Embedding_Index.
3. WHEN the Joint_Query vector is produced, THE Similarity_Engine SHALL compute cosine similarity against the joint Embedding_Index and return the Top_K highest-scoring artworks from the artworks that have joint embeddings.
4. THE Search_API SHALL accept an optional `text_weight` parameter as a float in the range [0.0, 1.0], defaulting to 0.5; the implicit image weight is `1 - text_weight`.
5. IF a joint search request is received with a query string but no image, THEN THE Search_API SHALL return an HTTP 422 response with the message "Joint mode requires both a text query and an image; provide an image or switch to text mode."
6. IF a joint search request is received with an image but no query string, THEN THE Search_API SHALL return an HTTP 422 response with the message "Joint mode requires both a text query and an image; provide a text query or switch to image mode."
7. THE Search_API SHALL return joint search results within 4 seconds for any combined query against the full joint index.
8. WHERE the client specifies a `top_k` parameter with a value of 10, 20, 50, or 100, THE Search_API SHALL return exactly that many results (or fewer if the joint index contains fewer artworks); THE Search_API SHALL default to 20 results when no `top_k` parameter is provided.

---

### Requirement 5: Search Result Schema

**User Story:** As a frontend developer, I want the Search_API to return a consistent, well-structured JSON response for all search modes, so that the Search_UI can render results without mode-specific parsing logic.

#### Acceptance Criteria

1. THE Search_API SHALL return search results as a JSON object containing a `results` array, a `query_mode` string, a `total_results` integer, and an optional `text_weight` float (present only when `query_mode` is `joint`).
2. WHEN returning search results, THE Search_API SHALL include the following fields for each result: `object_id` (integer), `title` (string), `artist_display_name` (string or null), `object_date` (string or null), `department` (string or null), `medium` (string or null), `primary_image_small` (string URL or null), `primary_image` (string URL or null), `object_url` (string URL), `score` (float between 0 and 1), and `is_highlight` (boolean).
3. WHEN an artwork has no primary image URL in the metadata, THE Search_API SHALL set `primary_image_small` and `primary_image` to null in the result.
4. THE Search_API SHALL sort results in descending order by `score`.

---

### Requirement 6: Search_UI Layout and MET Aesthetic

**User Story:** As a museum visitor, I want the search interface to feel like an extension of the Metropolitan Museum of Art's visual identity, so that the experience feels authoritative, elegant, and culturally appropriate.

#### Acceptance Criteria

1. THE Search_UI SHALL use a color palette consistent with the MET museum brand: deep red (`#E31837` or equivalent MET red), off-white/cream (`#F5F0E8` or equivalent), charcoal (`#1A1A1A`), and gold accent (`#C9A84C` or equivalent).
2. THE Search_UI SHALL use a serif typeface (such as Georgia or a web-safe serif) for headings and display text, and a clean sans-serif for body and UI controls.
3. THE Search_UI SHALL display a header containing the MET logo text "The Metropolitan Museum of Art" and a subtitle "Collection Search" in the MET typographic style.
4. THE Search_UI SHALL follow a mobile-first responsive design strategy, starting layout and styling at 320px viewport width and progressively enhancing for larger viewports up to 2560px; all touch targets SHALL be at least 44×44px.
5. THE Search_UI SHALL display a loading state with a tasteful animation while a search request is in progress.
6. WHEN no search has been performed, THE Search_UI SHALL display a hero section optimized for mobile viewports first, scaling to full-width on larger viewports, with a featured artwork image and an introductory tagline.

---

### Requirement 7: Search Input Controls

**User Story:** As a museum visitor, I want clear, intuitive controls to enter my search query in text, image, or joint mode, so that I can switch between search types without confusion.

#### Acceptance Criteria

1. THE Search_UI SHALL provide a text input field with placeholder text "Search the collection…" that accepts free-form text queries.
2. THE Search_UI SHALL provide an image upload control that accepts JPEG, PNG, and WebP files and displays a thumbnail preview of the selected image before submission.
3. THE Search_UI SHALL provide a Search_Mode selector with three options: "Text", "Image", and "Text + Image", defaulting to "Text".
4. WHEN the Search_Mode is set to "Text", THE Search_UI SHALL disable the image upload control and visually indicate it is inactive.
5. WHEN the Search_Mode is set to "Image", THE Search_UI SHALL disable the text input field and visually indicate it is inactive.
6. WHEN the Search_Mode is set to "Text + Image", THE Search_UI SHALL enable both the text input field and the image upload control.
7. WHEN the Search_Mode is set to "Text + Image", THE Search_UI SHALL display a weight slider labeled "Text ← Weight → Image" ranging from 0% text / 100% image to 100% text / 0% image, defaulting to 50% / 50%, and SHALL transmit the selected value as the `text_weight` parameter (0.0–1.0) in the search request.
8. THE Search_UI SHALL provide a Top_K selector control with options 10, 20, 50, and 100, defaulting to 20, and SHALL transmit the selected value as the `top_k` parameter in every search request.
12. THE Search_UI SHALL render all interactive controls (sliders, mode selectors, and the image upload button) with a minimum tap target size of 44×44px to ensure touch-friendliness on mobile devices.
9. WHEN the user submits a search with Search_Mode "Text" and an empty text field, THE Search_UI SHALL display an inline validation message "Please enter a search query" and SHALL NOT submit the request to the Search_API.
10. WHEN the user submits a search with Search_Mode "Image" and no image selected, THE Search_UI SHALL display an inline validation message "Please upload an image" and SHALL NOT submit the request to the Search_API.
11. WHEN the user submits a search with Search_Mode "Text + Image" and either the text field is empty or no image is selected, THE Search_UI SHALL display an inline validation message "Text + Image mode requires both a query and an image" and SHALL NOT submit the request to the Search_API.

---

### Requirement 8: Search Results Display

**User Story:** As a museum visitor, I want to browse search results as a visually rich grid of artwork cards, so that I can quickly scan and identify pieces of interest.

#### Acceptance Criteria

1. WHEN search results are returned, THE Search_UI SHALL display Artwork_Cards in a mobile-first responsive grid layout: 1 column on viewports narrower than 375px, 2 columns on viewports 375px and wider, 3 columns on viewports 768px and wider, and 4 columns on viewports 1280px and wider.
2. WHEN displaying an Artwork_Card, THE Search_UI SHALL show the artwork's primary image (or a placeholder if no image is available), title, artist display name, object date, and department.
3. WHEN an Artwork_Card is clicked, THE Search_UI SHALL open the MET museum object page (`object_url`) in a new browser tab.
4. WHEN an artwork has no primary image, THE Search_UI SHALL display a styled placeholder with the MET logo mark or a museum-appropriate icon.
5. THE Search_UI SHALL display the total number of results returned and the active Top_K setting (e.g., "Showing 20 of 44,973 artworks").
6. WHEN a search returns zero results, THE Search_UI SHALL display a message "No artworks found. Try a different search." in place of the results grid.

---

### Requirement 9: API Health and CORS

**User Story:** As a developer, I want the Search_API to expose a health check endpoint and handle CORS correctly, so that the Next.js frontend can communicate with it during development and production.

#### Acceptance Criteria

1. THE Search_API SHALL expose a `GET /health` endpoint that returns HTTP 200 with a JSON body `{"status": "ok", "rows": <integer>}` where `<integer>` is the number of artworks in the loaded index.
2. THE Search_API SHALL configure CORS to allow requests from the Search_UI origin (configurable via environment variable `ALLOWED_ORIGINS`), defaulting to `http://localhost:3000` in development.
3. WHEN a preflight `OPTIONS` request is received, THE Search_API SHALL respond with the appropriate CORS headers and HTTP 200.

---

### Requirement 10: Environment Configuration

**User Story:** As a developer, I want both the backend and frontend to be configurable via environment variables, so that the application can be deployed to different environments without code changes.

#### Acceptance Criteria

1. THE Search_API SHALL read the embeddings directory path from the environment variable `EMBEDDINGS_DIR`, defaulting to `data/embeddings` relative to the project root.
2. THE Search_API SHALL read the server host and port from environment variables `HOST` (default `0.0.0.0`) and `PORT` (default `8000`).
3. THE Search_UI SHALL read the Search_API base URL from the environment variable `NEXT_PUBLIC_API_URL`, defaulting to `http://localhost:8000`.
4. THE Search_API SHALL read `ALLOWED_ORIGINS` as a comma-separated list of allowed CORS origins.
