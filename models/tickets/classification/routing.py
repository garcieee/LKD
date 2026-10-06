"""Which office handles which category. The table lives in resources/offices.json."""


def office_for(category: str, offices: dict[str, str]) -> str:
    """The office for a category, falling back to the "other" entry and then to "Unassigned"."""
    return offices.get(category) or offices.get("other") or "Unassigned"
