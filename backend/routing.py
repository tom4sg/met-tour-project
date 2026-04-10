"""Approximate walking order for a Met Fifth Avenue tour on Floors 1, 1M, and 2.

Room comments below are rough wayfinding notes based on the shared floor maps,
not an official gallery database. For departments spanning multiple floors, the
order defers to the lower floor or the floor that appears to hold the larger
visitor-facing footprint.
"""

DEPARTMENT_ORDER = {
    # Floor 1, entering from the Great Hall.
    # Egyptian Art sits just east of the Great Hall in the 1xx rooms.
    "Egyptian Art": 1,
    # Greek and Roman Art anchors the west side of Floor 1 around rooms 15x-16x.
    "Greek and Roman Art": 2,
    # Ancient Near Eastern Art is represented by the Floor 2 southwest rooms
    # around the 203/204 area, so we place it early but after the Great Hall pair.
    "Ancient Near Eastern Art": 3,

    # Floor 1 central spine north of the Great Hall.
    # Arms and Armor occupies the east-central 37x/38x side.
    "Arms and Armor": 4,
    # Medieval Art is the middle connector around the 30x/50x run.
    "Medieval Art": 5,
    # European Sculpture and Decorative Arts spreads across the west-central
    # galleries near rooms 350, 351, 362, and the 54x corridor.
    "European Sculpture and Decorative Arts": 6,

    # Floor 1M / upper east side.
    # The American Wing is concentrated around rooms 707 and 774 on 1M, with
    # related Floor 1 presence around 700/724, so it stays in this east-side slot.
    "The American Wing": 7,
    "American Wing": 7,
    "American Decorative Arts": 7,
    # Modern and Contemporary Art has a compact but clear west-side presence on
    # 1M and a larger Floor 2 block around 917-919; we anchor it here to the
    # lower mezzanine stop instead of duplicating it upstairs.
    "Modern Art": 8,
    "Modern and Contemporary Art": 8,

    # Floor 2 west-to-center sequence.
    # European Paintings runs through the broad central 600-series galleries,
    # especially around rooms 628, 631, 633, and 644.
    "European Paintings": 9,
    # The Robert Lehman Collection sits in the prominent north projection seen
    # on Floor 1 around rooms 954, 957, 961, and 962.
    "The Robert Lehman Collection": 10,
    "Robert Lehman Collection": 10,
    # Drawings and Prints is not labeled on the screenshots, so it is treated as
    # a nearby Floor 2 works-on-paper stop following Lehman / European Paintings.
    "Drawings and Prints": 11,
    # Photographs is likewise placed in the later Floor 2 works-on-paper zone.
    "Photographs": 12,

    # Floor 2 global collections, moving toward the east / south edge.
    # Islamic Art corresponds to the southwest cluster labeled "Art of the Arab
    # Lands, Turkey, Iran, Central Asia, and Later South Asia."
    "Islamic Art": 13,
    # Asian Art is clearly marked on the southeast side around rooms 209, 215,
    # 216, 237, and 239, so we anchor it here instead of any higher-floor presence.
    "Asian Art": 14,
    # Arts of Africa, Oceania, and the Americas is not labeled on these floors,
    # so it is treated as a later global-collections catch-all stop.
    "Arts of Africa, Oceania, and the Americas": 15,

    # Specialty destinations on the upper route.
    # Musical Instruments is marked on Floor 2 around rooms 681-684 and the
    # nearby 227-229 connector.
    "Musical Instruments": 16,
    # Costume Institute is not shown in the screenshots, so it remains a late
    # specialty stop with a conservative placement near the end.
    "The Costume Institute": 17,
    "Costume Institute": 17,

    # Separate site: keep at the end for Fifth Avenue walking tours.
    "The Cloisters": 99,
    "Medieval Art (The Met Cloisters / Medieval Sculpture Hall)": 99,
}


def sort_stops(departments: list[str]) -> list[str]:
    """Sort departments by approximate Fifth Avenue walking order.

    Unknown departments are placed at the end. The sort is stable, so any ties
    keep their original input order.
    """
    return sorted(departments, key=lambda dept: DEPARTMENT_ORDER.get(dept, 99))


if __name__ == "__main__":
    sample_departments = [
        "The Robert Lehman Collection",
        "The Cloisters",
        "Photographs",
        "Egyptian Art",
        "American Decorative Arts",
        "Arms and Armor",
        "Asian Art",
    ]
    print(sort_stops(sample_departments))
