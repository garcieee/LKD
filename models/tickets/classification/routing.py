"""Who handles a ticket: the office for its category (resources/offices.json) and the district its spot is in
(resources/districts.json)."""


def office_for(category: str, offices: dict[str, str]) -> str:
    """The office for a category, falling back to the "other" entry and then to "Unassigned"."""
    return offices.get(category) or offices.get("other") or "Unassigned"


def _inside(x: float, y: float, ring: list) -> bool:
    """Ray casting: a ray from the point crosses a closed ring's edges an odd number of times when it is inside."""
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def district_of(lat: float, lng: float, districts) -> int | None:
    """The district of the barangay the point is in, from (district_id, name, (west, south, east, north), rings) per
    barangay. None inside no barangay: outside Makati, or in an EMBO barangay that is Taguig now."""
    for district_id, _name, (west, south, east, north), rings in districts:
        if west <= lng <= east and south <= lat <= north and any(_inside(lng, lat, ring) for ring in rings):
            return district_id
    return None
