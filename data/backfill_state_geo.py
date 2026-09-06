#!/usr/bin/env python3
"""Backfill venue metadata:
  1. state IS NULL + has coords  -> reverse geocode (Nominatim) -> set state
  2. scrape rows with lat=0      -> forward geocode street/city/state

Polite: 1.1s between Nominatim calls. Idempotent: skips rows already fixed.
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
UA = "TheHopper/1.0 (metadata backfill; contact via karaokespot.us)"

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH",
    "NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT",
    "VT","VA","WA","WV","WI","WY",
}


def clean_addr(a: str) -> str:
    return re.sub(r"\b(unit|ste|suite|#)\b\.?\s*[a-z0-9\-]+", " ", a, flags=re.I)


def fetch_json(url: str):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read())


def reverse_state(lat: float, lng: float) -> str | None:
    url = (f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}"
           f"&format=json&zoom=10")
    try:
        addr = fetch_json(url).get("address", {})
        code = (addr.get("state_code") or addr.get("ISO3166-2-lvl4") or "").split("-")[-1]
        if code.upper() in US_STATES:
            return code.upper()
    except Exception:
        pass
    return None


def forward(latlng_query: str) -> tuple[float, float] | None:
    url = ("https://nominatim.openstreetmap.org/search?q="
           + urllib.parse.quote(latlng_query) + "&format=json&limit=1")
    try:
        results = fetch_json(url)
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        pass
    return None


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # Pass 1: states via reverse geocode
    todo1 = conn.execute(
        "SELECT id, lat, lng FROM venues WHERE state IS NULL AND lat != 0"
    ).fetchall()
    fixed_state = 0
    print(f"pass 1: {len(todo1)} rows need state", flush=True)
    for r in todo1:
        st = reverse_state(r["lat"], r["lng"])
        if st:
            conn.execute("UPDATE venues SET state=? WHERE id=?", (st, r["id"]))
            fixed_state += 1
        time.sleep(1.1)
        if fixed_state % 40 == 0 and fixed_state:
            print(f"  states: {fixed_state}", flush=True)
    conn.commit()
    print(f"pass 1 done: {fixed_state}/{len(todo1)} states filled", flush=True)

    # Pass 2: geocode scrape rows with no coords
    todo2 = conn.execute(
        """SELECT id, name, address, city, state FROM venues
           WHERE lat = 0 AND lng = 0 AND source LIKE 'scrape%'"""
    ).fetchall()
    fixed_geo = 0
    print(f"pass 2: {len(todo2)} scrape rows need geocode", flush=True)
    for r in todo2:
        q = ", ".join(
            p for p in (clean_addr(r["address"]), r["city"], r["state"]) if p
        )
        if not q:
            continue
        geo = forward(q)
        if geo:
            conn.execute(
                "UPDATE venues SET lat=?, lng=? WHERE id=?",
                (geo[0], geo[1], r["id"]),
            )
            fixed_geo += 1
        time.sleep(1.1)
        if fixed_geo % 40 == 0 and fixed_geo:
            print(f"  geocoded: {fixed_geo}", flush=True)
    conn.commit()
    conn.close()
    print(f"DONE: states={fixed_state} geocoded={fixed_geo}", flush=True)


if __name__ == "__main__":
    main()
