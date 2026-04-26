# Implementation Plan: Tour Guide Routing

## Overview

Port the routing algorithm from `met_tour_routing.py` into the FastAPI backend, expose a `POST /tour` endpoint, and render the tour in a new `TourPanel` component below the existing search results. The implementation is purely additive — no existing search behavior is modified.

## Tasks

- [x] 1. Add tour models to `app/backend/models.py`
  - Add `TourArtworkInput`, `TourArtwork`, `GalleryStop`, `TourRequest`, and `TourResponse` Pydantic models
  - `TourRequest.artworks` uses `Field(min_length=1, max_length=100)`
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 8.1, 8.3_

- [x] 2. Create `app/backend/tour.py` — routing engine
  - [x] 2.1 Port coordinate data and helpers from `met_tour_routing.py`
    - Copy `ROOM_COORDS`, `DEPARTMENT_COORDS`, `FLOOR_PENALTY`, `GREAT_HALL` constants verbatim
    - Port `get_coords`, `coords_array`, `total_distance` — remove pandas dependency, accept plain dicts
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 2.2 Write property test for `get_coords` — Property 1: Floor penalty encoding
    - File: `app/backend/tests/test_tour_routing.py`
    - **Property 1: Floor penalty encoding**
    - **Validates: Requirements 2.5, 3.3**

  - [x] 2.3 Write property test for `get_coords` — Property 2: Coordinate resolution priority
    - File: `app/backend/tests/test_tour_routing.py`
    - **Property 2: Coordinate resolution priority**
    - **Validates: Requirements 2.2, 3.5**

  - [x] 2.4 Port `two_opt` and `nearest_neighbor_route` from `met_tour_routing.py`
    - Copy functions verbatim; remove the pandas `df` global and `__main__` block
    - _Requirements: 2.3, 2.4, 2.5_

  - [x] 2.5 Write property test for `two_opt` — Property 4: 2-opt never worsens a route
    - File: `app/backend/tests/test_tour_routing.py`
    - **Property 4: 2-opt never worsens a route**
    - **Validates: Requirements 2.4**

  - [x] 2.6 Implement `group_by_stop` returning `list[GalleryStop]`
    - Adapt `group_by_stop` from `met_tour_routing.py` to return an ordered `list[GalleryStop]` instead of a dict
    - Derive `floor` from the first artwork in each group's z-coordinate divided by `FLOOR_PENALTY`
    - Apply stop label priority: `"Gallery {number}"` → department name → `"Unknown Location"`
    - Filter out Cloisters artworks and sentinel-coordinate artworks before grouping
    - _Requirements: 1.6, 2.6, 2.7, 2.9, 3.4_

  - [ ]* 2.7 Write property test for `group_by_stop` — Property 3: Cloisters and unroutable excluded
    - File: `app/backend/tests/test_tour_routing.py`
    - **Property 3: Cloisters and unroutable artworks excluded from tour**
    - **Validates: Requirements 1.6, 3.4**

  - [ ]* 2.8 Write property test for `group_by_stop` — Property 5: Non-empty routable input produces non-empty tour
    - File: `app/backend/tests/test_tour_routing.py`
    - **Property 5: Non-empty routable input produces non-empty tour**
    - **Validates: Requirements 2.6**

  - [ ]* 2.9 Write property test for `group_by_stop` — Property 9: Stop label assignment follows priority
    - File: `app/backend/tests/test_tour_routing.py`
    - **Property 9: Stop label assignment follows priority**
    - **Validates: Requirements 2.9**

  - [ ]* 2.10 Write property test — Property 8: Department-only artworks are routable, not excluded
    - File: `app/backend/tests/test_tour_routing.py`
    - **Property 8: Department-only artworks are routable, not excluded**
    - **Validates: Requirements 7.4**

- [x] 3. Create `app/backend/tour.py` — gallery fetcher and endpoint
  - [x] 3.1 Implement `fetch_gallery_number` and `fetch_all_gallery_numbers`
    - Use `httpx.AsyncClient` with `asyncio.Semaphore(80)`
    - Cache results in `app.state.gallery_cache` (dict passed in as argument)
    - On any exception (HTTP error, timeout, invalid JSON), return `None` — never raise
    - Add `httpx` to `[project] dependencies` in `app/backend/pyproject.toml`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 3.2 Implement `POST /tour` endpoint in `tour.py`
    - Accept `TourRequest`, fetch gallery numbers, build artwork dicts, call `group_by_stop`, return `TourResponse`
    - Compute `routable_count`, `excluded_count`, `total_input` from results
    - _Requirements: 4.1, 4.2, 4.5, 4.6_

  - [ ]* 3.3 Write property test — Property 6: Response counts are consistent
    - File: `app/backend/tests/test_tour_routing.py`
    - **Property 6: Response counts are consistent**
    - **Validates: Requirements 4.6**

  - [ ]* 3.4 Write property test — Property 7: TourResponse serialization round-trip
    - File: `app/backend/tests/test_tour_routing.py`
    - **Property 7: TourResponse serialization round-trip**
    - **Validates: Requirements 8.1, 8.2, 8.3**

- [x] 4. Register the tour endpoint in `app/backend/main.py`
  - Initialize `app.state.gallery_cache = {}` inside the `lifespan` function before `yield`
  - Import and register the tour router / endpoint from `tour.py`
  - _Requirements: 4.1_

- [ ]* 5. Checkpoint — ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Create frontend types and API client
  - [x] 6.1 Create `app/frontend/types/tour.ts`
    - Define `TourArtwork`, `GalleryStop`, `TourResponse`, `TourRequest` TypeScript interfaces mirroring backend models
    - _Requirements: 4.2, 5.3_

  - [x] 6.2 Create `app/frontend/lib/tourApi.ts`
    - Implement `generateTour(artworks: ArtworkResult[]): Promise<TourResponse>`
    - Map `ArtworkResult[]` to `TourRequest` body (object_id, title, artist_display_name, primary_image_small, object_url, department)
    - Throw typed errors for 422 and 5xx responses
    - _Requirements: 4.1, 5.2, 5.5_

- [ ] 7. Create `app/frontend/components/GalleryStopCard.tsx`
  - Props: `stop: GalleryStop`, `stopNumber: number`
  - Render stop number badge (met-red), stop label, floor indicator
  - Render horizontal scroll row of artwork thumbnails with title and artist name
  - Use placeholder when `primary_image_small` is null
  - _Requirements: 5.3, 5.6, 5.7_

- [x] 8. Create `app/frontend/components/TourPanel.tsx`
  - [x] 8.1 Implement state machine and "Generate Tour" button
    - State: `idle | loading | success | error`
    - Show button only when `artworks.length > 0`; call `generateTour` on click
    - Show loading spinner with "Planning your tour…" while in-flight
    - _Requirements: 5.1, 5.2_

  - [x] 8.2 Implement success rendering
    - Render ordered list of `GalleryStopCard` components
    - Show stop count summary and excluded count note when `excluded_count > 0`
    - Show "None of your search results could be located in the museum" when `stops` is empty
    - _Requirements: 5.3, 5.4, 7.1, 7.2_

  - [x] 8.3 Implement map link and gallery summary (Route_Visualizer)
    - Render link to `https://maps.metmuseum.org` with `target="_blank"` and `rel="noopener noreferrer"`
    - Display readable gallery number summary: `"Galleries: 825 → 826 → 800 → …"`
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 8.4 Implement error state with retry
    - Show error message and "Try Again" button that resets state to `idle`
    - _Requirements: 5.5_

- [x] 9. Integrate `TourPanel` into `app/frontend/app/page.tsx`
  - Import `TourPanel` and render it below `ResultsGrid` inside the existing `!isLoading && searchResponse` block
  - Pass `searchResponse.results` as the `artworks` prop
  - _Requirements: 5.1, 7.3_

- [ ]* 10. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The routing functions in `met_tour_routing.py` are ported as-is — no algorithmic changes needed
- `httpx` must be added to `[project] dependencies` in `pyproject.toml` (it is already in `dev` dependencies, but needs to be a runtime dependency)
- Property tests use [Hypothesis](https://hypothesis.readthedocs.io/) which is already in `dev` dependencies
- The `TourRequest` uses `artworks: list[TourArtworkInput]` (not bare `object_ids`) so the frontend sends full metadata, avoiding a second index lookup
