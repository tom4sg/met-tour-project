# Requirements Document

## Introduction

The Tour Guide Routing feature extends the MET Museum art search app to help visitors plan a physical museum visit. After performing a semantic search, users can generate a tour route from the results. The system uses a hardcoded spatial coordinate map of Met galleries to compute physically meaningful walking distances, fetches gallery numbers from the Met Collection API where available, and falls back to department-level centroid coordinates for artworks without a specific gallery number. The route is optimized using a nearest-neighbor greedy algorithm per floor followed by 2-opt local search, starting from the Great Hall. Only artworks with neither a gallery number nor a known department are excluded from the tour.

## Glossary

- **Tour_Generator**: The backend service responsible for fetching gallery numbers, computing coordinates, and producing an optimized walking route.
- **Gallery_Fetcher**: The backend component that calls the Met Collection API to retrieve `GalleryNumber` for a given object ID, with caching and rate-limit compliance.
- **Gallery_Cache**: An in-process, request-scoped or server-scoped store that maps object IDs to their fetched gallery numbers to avoid redundant API calls.
- **Tour_Route**: An ordered list of gallery stops, each containing a stop label, floor, and the artworks located there.
- **Gallery_Stop**: A single entry in a Tour_Route representing one physical stop (a specific gallery room or a department area), its floor, and the artworks within it.
- **Tour_Panel**: The frontend UI component that displays the Tour_Route as an ordered list of Gallery_Stops and provides a link to the Met interactive map.
- **Route_Visualizer**: The frontend component that renders the tour as a visual floor-by-floor stop list with a deep-link to the Met interactive map.
- **Met_Collection_API**: The public REST API at `https://collectionapi.metmuseum.org/public/collection/v1/objects/[objectID]` that returns artwork metadata including `GalleryNumber`.
- **Met_Interactive_Map**: The web-based map at `https://maps.metmuseum.org` used for gallery navigation.
- **On_View**: An artwork is considered on view when the Met Collection API returns a non-empty `GalleryNumber` for its object ID.
- **Object_ID**: The numeric identifier extracted from the `objectURL` field in local metadata (e.g., `460813` from `.../search/460813`).
- **ROOM_COORDS**: A hardcoded dictionary mapping ~400+ Met gallery numbers to `(x, y, floor)` spatial coordinates derived from the actual Met floor maps.
- **DEPARTMENT_COORDS**: A hardcoded dictionary mapping Met department names to approximate `(x, y, floor)` centroid coordinates, used as a fallback when a specific gallery number is unavailable.
- **Floor_Penalty**: A constant (8.0) applied to the z-axis so that Euclidean distance calculations naturally penalize floor changes, strongly preferring routes that complete one floor before moving to the next.
- **Great_Hall**: The fixed starting point for every tour, located at coordinates (5.2, 0.5) on Floor 1, representing the main entrance of the Met's Fifth Avenue building.
- **Routable**: An artwork is routable when it has either a `GalleryNumber` present in ROOM_COORDS or a `department` present in DEPARTMENT_COORDS.

---

## Requirements

### Requirement 1: Gallery Number Retrieval

**User Story:** As a visitor, I want the app to look up which gallery each artwork is in, so that I know which artworks are physically on view and where to find them.

#### Acceptance Criteria

1. WHEN a tour is requested for a set of object IDs, THE Gallery_Fetcher SHALL call the Met Collection API for each object ID to retrieve its `GalleryNumber`.
2. WHILE fetching gallery numbers, THE Gallery_Fetcher SHALL respect the Met Collection API rate limit by issuing no more than 80 concurrent requests per second.
3. THE Gallery_Cache SHALL store the `GalleryNumber` result for each object ID so that repeated requests for the same object ID within the same server session do not trigger additional API calls.
4. IF the Met Collection API returns an empty, null, or missing `GalleryNumber` for an object ID, THEN THE Gallery_Fetcher SHALL mark that artwork as not having a specific gallery room, and THE Tour_Generator SHALL attempt to route it using its department centroid from DEPARTMENT_COORDS.
5. IF the Met Collection API returns an HTTP error for an object ID, THEN THE Gallery_Fetcher SHALL mark that artwork as not having a specific gallery room, and THE Tour_Generator SHALL attempt to route it using its department centroid from DEPARTMENT_COORDS.
6. WHEN gallery number retrieval is complete, THE Tour_Generator SHALL include only Routable artworks in the Tour_Route, excluding artworks from The Cloisters (a separate building) and artworks with neither a known gallery number nor a known department.

---

### Requirement 2: Tour Route Generation

**User Story:** As a visitor, I want the app to generate a logical walking route through the galleries, so that I can visit all routable artworks from my search results with minimal backtracking.

#### Acceptance Criteria

1. WHEN coordinates have been resolved for all artworks, THE Tour_Generator SHALL partition artworks into floor groups (floor 1, floor 2, and other/unknown) using each artwork's resolved z-coordinate divided by the Floor_Penalty.
2. THE Tour_Generator SHALL resolve each artwork's spatial coordinate by first looking up its `GalleryNumber` in ROOM_COORDS, then falling back to its `department` in DEPARTMENT_COORDS, and assigning sentinel coordinates (99, 99, 99) to artworks with neither a matching gallery number nor a matching department.
3. WHEN building the route for each floor group, THE Tour_Generator SHALL apply a greedy nearest-neighbor algorithm starting from the Great_Hall on floor 1, then continuing from the last artwork of each floor group as the starting point for the next floor group, processing floor groups in the order: floor 1 → floor 2 → other.
4. WHEN the greedy nearest-neighbor route for a floor group has been computed, THE Tour_Generator SHALL apply 2-opt local search to that floor group's route to eliminate path crossings, accepting any reversal of a sub-segment that reduces the total Euclidean path length.
5. THE Tour_Generator SHALL encode floor transitions in the distance metric by setting each artwork's z-coordinate to `floor_number × 8.0` (Floor_Penalty), so that Euclidean distance naturally penalizes floor changes without requiring explicit floor-change logic.
6. THE Tour_Generator SHALL produce a Tour_Route containing at least one Gallery_Stop when at least one Routable artwork is present in the input.
7. IF no artworks in the search results are Routable, THEN THE Tour_Generator SHALL return an empty Tour_Route and include a message indicating no routable artworks were found.
8. THE Tour_Generator SHALL include each artwork's `object_id`, `title`, `artist_display_name`, `primary_image_small`, and `object_url` within its parent Gallery_Stop.
9. WHEN grouping routed artworks into Gallery_Stops, THE Tour_Generator SHALL label each stop as "Gallery {number}" when the artwork's `GalleryNumber` is present in ROOM_COORDS, as the department name when only a department centroid was used, and as "Unknown Location" otherwise.

---

### Requirement 3: Routing Coordinate System

**User Story:** As a developer, I want the routing system to use physically meaningful gallery coordinates, so that the computed walking distances reflect the actual layout of the Met's Fifth Avenue building.

#### Acceptance Criteria

1. THE Tour_Generator SHALL maintain a hardcoded ROOM_COORDS map covering approximately 400 Met gallery numbers, where each entry maps a gallery number string to an `(x, y, floor)` coordinate derived from the actual Met floor maps, with x ranging from 0 (west wall) to 10 (east wall), y ranging from 0 (south wall) to 10 (north wall), and floor being 1 or 2 (floor 3 galleries stored at floor 2 for routing purposes).
2. THE Tour_Generator SHALL maintain a hardcoded DEPARTMENT_COORDS map covering all major Met departments, where each entry maps a department name string to an approximate `(x, y, floor)` centroid coordinate for that department's gallery area.
3. WHEN computing Euclidean distances between artworks, THE Tour_Generator SHALL encode each artwork's floor as `floor_number × 8.0` on the z-axis, so that a single floor change adds a distance equivalent to walking 8 lateral units.
4. THE Tour_Generator SHALL exclude artworks belonging to The Cloisters department from all routing calculations, as The Cloisters is a separate building not covered by the Fifth Avenue coordinate map.
5. WHEN an artwork's `GalleryNumber` is not present in ROOM_COORDS and its `department` is not present in DEPARTMENT_COORDS, THE Tour_Generator SHALL assign that artwork sentinel coordinates (99, 99, 99) so that it sorts to the end of the route.

---

### Requirement 4: Tour Generation API Endpoint

**User Story:** As a developer, I want a dedicated API endpoint for tour generation, so that the frontend can request a tour route independently of the search operation.

#### Acceptance Criteria

1. THE Tour_Generator SHALL expose a `POST /tour` endpoint that accepts a JSON body containing a list of `object_id` values.
2. WHEN the `POST /tour` endpoint receives a valid request, THE Tour_Generator SHALL return a response containing the ordered Tour_Route and a count of routable artworks included.
3. IF the `POST /tour` request body contains an empty list of object IDs, THEN THE Tour_Generator SHALL return a 422 error with a descriptive message.
4. IF the `POST /tour` request body contains more than 100 object IDs, THEN THE Tour_Generator SHALL return a 422 error indicating the maximum allowed count.
5. THE Tour_Generator SHALL complete the `POST /tour` response within 10 seconds for a request containing up to 100 object IDs.
6. THE Tour_Generator SHALL return the total count of input object IDs, the count of Routable artworks, and the count of Gallery_Stops in the response.

---

### Requirement 5: Tour Panel UI

**User Story:** As a visitor, I want to see the tour route displayed after my search results, so that I can understand which galleries to visit and in what order.

#### Acceptance Criteria

1. WHEN search results are displayed and at least one result is Routable, THE Tour_Panel SHALL render a "Generate Tour" button below the search results grid.
2. WHEN the user activates the "Generate Tour" button, THE Tour_Panel SHALL call the `POST /tour` endpoint with the object IDs from the current search results and display a loading indicator while the request is in progress.
3. WHEN the Tour_Route is received and contains at least one Gallery_Stop, THE Tour_Panel SHALL render the Gallery_Stops as an ordered list, each showing the stop label, floor, and the artworks within that stop.
4. WHEN the Tour_Route is received and is empty, THE Tour_Panel SHALL display a message stating that none of the search results could be routed to a location in the museum.
5. IF the `POST /tour` request fails, THEN THE Tour_Panel SHALL display an error message and provide a retry option.
6. THE Tour_Panel SHALL display each artwork within a Gallery_Stop with its thumbnail image (using `primary_image_small`), title, and artist name.
7. THE Tour_Panel SHALL use the existing MET brand color palette (met-red, met-cream, met-gold, met-charcoal) and be consistent with the existing component design language.

---

### Requirement 6: Met Interactive Map Integration

**User Story:** As a visitor, I want a link to the Met's interactive map pre-focused on my tour, so that I can navigate the museum using the official map.

#### Acceptance Criteria

1. WHEN a Tour_Route with at least one Gallery_Stop is displayed, THE Route_Visualizer SHALL render a prominent link to the Met Interactive Map (`https://maps.metmuseum.org`).
2. THE Route_Visualizer SHALL display the gallery numbers for all Gallery_Stops in the tour as a readable summary adjacent to the map link, so the visitor can manually navigate to each gallery on the Met Interactive Map.
3. THE Route_Visualizer SHALL open the Met Interactive Map link in a new browser tab.
4. WHERE the Met Interactive Map supports URL parameters for gallery navigation, THE Route_Visualizer SHALL construct the link with the first Gallery_Stop's gallery number as the initial target.

---

### Requirement 7: Graceful Handling of Non-Routable Artworks

**User Story:** As a visitor, I want to know which artworks from my search cannot be located in the museum, so that I can set accurate expectations before visiting.

#### Acceptance Criteria

1. WHEN a Tour_Route is displayed, THE Tour_Panel SHALL show a count of artworks excluded from the tour because they could not be routed to any location in the Fifth Avenue building.
2. WHEN the excluded count is greater than zero, THE Tour_Panel SHALL display a note explaining that those artworks have no known gallery or department location in the current coordinate map.
3. THE Tour_Panel SHALL NOT remove non-Routable artworks from the search results grid; they SHALL remain visible in the results with no tour-related annotation.
4. WHEN an artwork lacks a `GalleryNumber` from the Met Collection API but has a known `department` in DEPARTMENT_COORDS, THE Tour_Panel SHALL include that artwork in the tour at its department centroid location and SHALL NOT count it as excluded.

---

### Requirement 8: Tour Data Serialization Round-Trip

**User Story:** As a developer, I want the tour route data to serialize and deserialize correctly, so that API responses are reliable and consistent.

#### Acceptance Criteria

1. THE Tour_Generator SHALL serialize Tour_Route responses as valid JSON conforming to the defined response schema.
2. FOR ALL valid Tour_Route objects, serializing to JSON and then deserializing SHALL produce an equivalent Tour_Route object (round-trip property).
3. THE Tour_Generator SHALL validate that all required fields (`stop_label`, `floor`, `artworks`) are present in each Gallery_Stop before returning a response.
