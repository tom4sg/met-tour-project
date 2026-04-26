# Feature: tour-guide-routing, Property 1: Floor penalty encoding

from hypothesis import given, settings
from hypothesis import strategies as st

from tour import DEPARTMENT_COORDS, FLOOR_PENALTY, ROOM_COORDS, get_coords

# Build a strategy that samples only gallery keys whose floor is 1 or 2
_known_floor_galleries = [
    gallery for gallery, (_, _, floor) in ROOM_COORDS.items() if floor in (1, 2)
]


@given(gallery=st.sampled_from(_known_floor_galleries))
@settings(max_examples=50)
def test_floor_penalty_encoding(gallery: str) -> None:
    """Property 1: Floor penalty encoding.

    For any artwork with a known floor number N (1 or 2), get_coords SHALL
    return a z-coordinate equal to N × FLOOR_PENALTY (8.0), so that Euclidean
    distance calculations naturally penalize floor changes.

    Validates: Requirements 2.5, 3.3
    """
    _, _, floor = ROOM_COORDS[gallery]
    artwork = {"GalleryNumber": gallery}
    _, _, z = get_coords(artwork)
    assert (
        z == floor * FLOOR_PENALTY
    ), f"Gallery {gallery!r} (floor {floor}): expected z={floor * FLOOR_PENALTY}, got z={z}"


# Feature: tour-guide-routing, Property 2: Coordinate resolution priority

_known_room_galleries = list(ROOM_COORDS.keys())
_known_departments = list(DEPARTMENT_COORDS.keys())


@given(gallery=st.sampled_from(_known_room_galleries))
@settings(max_examples=50)
def test_resolution_priority_room_coords(gallery: str) -> None:
    """Property 2a: When GalleryNumber is in ROOM_COORDS, get_coords returns ROOM_COORDS value.

    Validates: Requirements 2.2, 3.5
    """
    x_expected, y_expected, floor = ROOM_COORDS[gallery]
    artwork = {"GalleryNumber": gallery}
    result = get_coords(artwork)
    assert result == (
        x_expected,
        y_expected,
        floor * FLOOR_PENALTY,
    ), f"Gallery {gallery!r}: expected {(x_expected, y_expected, floor * FLOOR_PENALTY)}, got {result}"


@given(dept=st.sampled_from(_known_departments))
@settings(max_examples=50)
def test_resolution_priority_department_coords(dept: str) -> None:
    """Property 2b: When GalleryNumber is absent/unknown but department is in DEPARTMENT_COORDS,
    get_coords returns DEPARTMENT_COORDS value.

    Validates: Requirements 2.2, 3.5
    """
    x_expected, y_expected, floor = DEPARTMENT_COORDS[dept]
    # Use a gallery number that is definitely not in ROOM_COORDS
    artwork = {"GalleryNumber": "UNKNOWN_GALLERY_XYZ", "department": dept}
    result = get_coords(artwork)
    assert result == (
        x_expected,
        y_expected,
        floor * FLOOR_PENALTY,
    ), f"Department {dept!r}: expected {(x_expected, y_expected, floor * FLOOR_PENALTY)}, got {result}"


@given(
    gallery=st.text(min_size=0, max_size=20).filter(
        lambda g: g.strip() not in ROOM_COORDS
    ),
    dept=st.text(min_size=0, max_size=40).filter(
        lambda d: d.strip() not in DEPARTMENT_COORDS
    ),
)
@settings(max_examples=50)
def test_resolution_priority_sentinel(gallery: str, dept: str) -> None:
    """Property 2c: When neither GalleryNumber nor department is known,
    get_coords returns the sentinel (99.0, 99.0, 99.0).

    Validates: Requirements 2.2, 3.5
    """
    artwork = {"GalleryNumber": gallery, "department": dept}
    result = get_coords(artwork)
    assert result == (
        99.0,
        99.0,
        99.0,
    ), f"Unknown gallery/dept: expected sentinel (99.0, 99.0, 99.0), got {result}"


# Feature: tour-guide-routing, Property 4: 2-opt never worsens a route

from tour import total_distance, two_opt

_routable_galleries = list(ROOM_COORDS.keys())


@given(
    artworks=st.lists(
        st.sampled_from(_routable_galleries).map(lambda g: {"GalleryNumber": g}),
        min_size=2,
        max_size=20,
    )
)
@settings(max_examples=50)
def test_two_opt_never_worsens(artworks: list) -> None:
    """Property 4: 2-opt never worsens a route.

    For any list of artworks on a single floor, the total Euclidean path
    distance of the 2-opt result SHALL be less than or equal to the total
    distance of the input route.

    Validates: Requirements 2.4
    """
    result = two_opt(artworks)
    assert total_distance(result) <= total_distance(artworks), (
        f"2-opt worsened the route: "
        f"before={total_distance(artworks):.4f}, after={total_distance(result):.4f}"
    )
