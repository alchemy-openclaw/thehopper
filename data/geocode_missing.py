#!/usr/bin/env python3
"""Geocode venues that still have no coordinates (lat=0, lng=0).

Retry ladder per row (all Nominatim, 1.1s between calls):
  1. cleaned address + city + state
  2. address with trailing junk tokens stripped ("Rd a", "3rd floor", "#1A")
  3. address with only the leading street number + first two words
  4. city + state centroid (marked confidence='city_centroid' so the UI can
     treat it as approximate)

Idempotent; safe to re-run.
"""

import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "backend" / "thehopper.db"
UA = "TheHopper/1.0 (geocode backfill; contact via karaokespot.us)"

JUNK = re.compile(
    r"\b(floor|flr|ste|suite|unit|bldg|building|room|rm|rear|upstairs|downstairs)\b\.?"
    r"(\s*#?\s*[a-z0-9\-]+)?$|,\s*[a-z]{1,3}$|\s[a-z]$",
    re.I,
)


def clean_addr(a: str) -> str:
    a = re.sub(r"\b(unit|ste|suite|#)\b\.?\s*[a-z0-9\-]+", " ", a, flags=re.I)
    return re.sub(r"\s+", " ", a).strip().strip(",")


def strip_junk(a: str) -> str:
    a = a.strip()
    while True:
        new = JUNK.sub("", a).strip().strip(",").strip()
        if new == a or not new:
            break
        a = new
    return re.sub(r"\s+", " ", a)


def shorten(a: str) -> str:
    parts = a.split()
    if len(parts) <= 3:
        return a
    return " ".join(parts[:3])


def fetch_json(url: str):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read())


def try_q(q: str):
    if not q:
        return None
    url = ("https://nominatim.openstreetmap.org/search?q="
           + urllib.parse.quote(q) + "&format=json&limit=1")
    try:
        r = fetch_json(url)
    except Exception:
        r = []
    time.sleep(1.1)
    if r:
        return float(r[0]["lat"]), float(r[0]["lon"])
    return None


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, address, city, state FROM venues WHERE lat = 0 AND lng = 0"
    ).fetchall()
    print(f"{len(rows)} rows to geocode", flush=True)

    fixed = centroid = 0
    for i, r in enumerate(rows, 1):
        addr = r["address"] or ""
        city, state = r["city"] or "", r["state"] or ""
        got = None
        confidence = None

        a1 = clean_addr(addr)
        if a1:
            got = try_q(", ".join(p for p in (a1, city, state) if p))
            if not got:
                a2 = strip_junk(a1)
                if a2 and a2 != a1:
                    got = try_q(", ".join(p for p in (a2, city, state) if p))
                if not got:
                    a3 = shorten(a1)
                    if a3 and a3 not in (a1, a2):
                        got = try_q(", ".join(p for p in (a3, city, state) if p))
            if got:
                confidence = "geocoded"
        if not got and city:
            # City centroid — approximate but keeps the row on maps/lists.
            got = try_q(", ".join(p for p in (city, state) if p))
            if got:
                confidence = "city_centroid"
                centroid += 1

        if got:
            conn.execute(
                "UPDATE venues SET lat=?, lng=?, confidence=COALESCE(confidence, ?) WHERE id=?",
                (got[0], got[1], confidence, r["id"]),
            )
            fixed += 1
        if i % 40 == 0:
            print(f"  {i}/{len(rows)}: fixed={fixed} (centroid={centroid})", flush=True)
            conn.commit()

    conn.commit()
    conn.close()
    print(f"DONE: fixed={fixed}/{len(rows)} (city centroids: {centroid})", flush=True)


if __name__ == "__main__":
    main()
