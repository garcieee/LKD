"""Download the Chicago 311 requests the matcher evaluation uses, as csv, into eval/data/raw/ (git-ignored).

Source: City of Chicago Data Portal, "311 Service Requests" (resource v6vf-nfxy), public open data.
Run from anywhere:  python3 models/tickets/eval/matching/chicago/fetch.py
It is safe to rerun: a finished file is skipped.
"""
import csv
import io
import time
import urllib.parse
import urllib.request
from pathlib import Path

RESOURCE = "https://data.cityofchicago.org/resource/v6vf-nfxy.csv"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
COLUMNS = "sr_number,sr_type,status,origin,created_date,closed_date,duplicate,parent_sr_number,latitude,longitude,street_address,community_area,ward"
PAGE = 40_000

# (file stem, Chicago request type, first day, day after the last), mapped to the app's categories in the evaluation
SLICES = [
    ("pothole_2024_2025", "Pothole in Street Complaint", "2024-01-01", "2026-01-01"),
    ("streetlight_2025", "Street Light Out Complaint", "2025-01-01", "2026-01-01"),
    ("sidewalk_2025", "Sidewalk Inspection Request", "2025-01-01", "2026-01-01"),
    ("waterstreet_2025", "Water On Street Complaint", "2025-01-01", "2026-01-01"),
]


def get(params: dict) -> bytes:
    url = RESOURCE + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "lakad-hackathon-research"})
    for attempt in range(4):
        try:
            return urllib.request.urlopen(request, timeout=180).read()
        except Exception as error:  # a public API: retry a few times with a pause
            if attempt == 3:
                raise
            print(f"  retry after {error}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def fetch(stem: str, sr_type: str, first: str, last: str) -> None:
    out = RAW / f"chicago_311_{stem}.csv"
    if out.exists():
        print(f"{out.name}: already there, skipping")
        return
    where = f"sr_type='{sr_type}' AND created_date >= '{first}T00:00:00' AND created_date < '{last}T00:00:00'"
    rows: list[list[str]] = []
    header: list[str] = []
    offset = 0
    while True:
        text = get({"$select": COLUMNS, "$where": where, "$order": "sr_number", "$limit": PAGE, "$offset": offset}).decode()
        page = list(csv.reader(io.StringIO(text)))
        header, body = page[0], page[1:]
        rows += body
        print(f"  {stem}: {len(rows):,} rows")
        if len(body) < PAGE:
            break
        offset += PAGE
    expected = int(list(csv.DictReader(io.StringIO(get({"$select": "count(*) as n", "$where": where}).decode())))[0]["n"])
    assert len(rows) == expected, f"{stem}: got {len(rows)} rows, the portal says {expected}"
    RAW.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"{out.name}: {len(rows):,} rows, {out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    for slice_ in SLICES:
        fetch(*slice_)
