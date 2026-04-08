"""Small dummy-data tests for backend.routing.

Run directly with:
    python3 backend/test_routing_dummy.py

This file is intentionally simple so we can quickly sanity-check routing
behavior while tweaking the department order.
"""

from routing import sort_stops


def run_case(name: str, departments: list[str], expected: list[str]) -> None:
    """Sort one dummy department list and verify the result."""
    result = sort_stops(departments)
    print(f"{name}:")
    print(f"  input:    {departments}")
    print(f"  expected: {expected}")
    print(f"  result:   {result}")
    assert result == expected, f"{name} failed"


if __name__ == "__main__":
    # Basic mixed-floor case: should move from Great Hall departments outward.
    run_case(
        "basic_mixed_route",
        [
            "Asian Art",
            "Egyptian Art",
            "European Paintings",
            "Arms and Armor",
            "The American Wing",
        ],
        [
            "Egyptian Art",
            "Arms and Armor",
            "The American Wing",
            "European Paintings",
            "Asian Art",
        ],
    )

    # Alias handling: API-ish and app-ish names should land in the same slot.
    run_case(
        "alias_names",
        [
            "American Decorative Arts",
            "Modern Art",
            "Robert Lehman Collection",
            "The American Wing",
        ],
        [
            "American Decorative Arts",
            "The American Wing",
            "Modern Art",
            "Robert Lehman Collection",
        ],
    )

    # Unknown departments should fall to the end; the sort remains stable for ties.
    run_case(
        "unknown_at_end",
        [
            "Photographs",
            "Imaginary Department",
            "Asian Art",
            "Another Unknown",
        ],
        [
            "Photographs",
            "Asian Art",
            "Imaginary Department",
            "Another Unknown",
        ],
    )

    # Cloisters should always be relegated to the end of a Fifth Avenue tour.
    run_case(
        "cloisters_last",
        [
            "The Cloisters",
            "Greek and Roman Art",
            "Egyptian Art",
        ],
        [
            "Egyptian Art",
            "Greek and Roman Art",
            "The Cloisters",
        ],
    )

    print("\nAll dummy routing tests passed.")
