#!/usr/bin/env python3
"""Import the national KaraokeLocations scrape into thehopper.db.

Deduplicates against existing venues three ways:
  1. normalized-name containment + same city
  2. name containment + within 0.1 mi (when the incoming row geocodes)
  3. Nominatim geocode (1 req/s, unit-stripped addresses)

Rows that match an existing venue only update it when the existing row has no
karaoke schedule and the incoming one might contribute one (it can't — KL has
no schedules — so updates are limited to missing phone/website/state).
New rows are inserted with source='scrape:karaokelocations',
confidence='unverified'.

Usage:
  python3 data/import_karaokelocations_national.py            # full run
  python3 data/import_karaokelocations_national.py --dry-run  # no writes
"""

import json
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "backend" / "thehopper.db"
IN = BASE / "data" / "karaokelocations_national.json"

UA = "TheHopper/1.0 (directory import; contact via karaokespot.us)"

# --- Normalization (mirrors backend/main.py) --------------------------------

SUFFIXES = [" the ", " bar ", " grill ", " pub ", " lounge ", " restaurant ",
            " bar and grill", " and grill", " sports bar", " tavern",
            " taproom"]


def norm_name(name: str) -> str:
    n = name.lower().strip()
    n = n.replace("&", " and ")
    for s in SUFFIXES:
        n = n.replace(s, " ")
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    if n.startswith("the "):
        n = n[4:]
    return n


def clean_addr(a: str) -> str:
    """Strip unit/suite designators for Nominatim (learned from kava pipeline)."""
    return re.sub(r"\b(unit|ste|suite|#)\b\.?\s*[a-z0-9\-]+", " ", a, flags=re.I)


# Full state names -> USPS codes (the scrape returns "Idaho", not "ID")
US_STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN",
    "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT",
    "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def usps(state: str) -> str:
    s = state.strip()
    if s.upper() in {"AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI",
                     "ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN",
                     "MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH",
                     "OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA",
                     "WV","WI","WY"}:
        return s.upper()
    return US_STATE_NAMES.get(s.lower(), s)


# --- Geocoding ---------------------------------------------------------------

_geo_cache: dict[str, tuple[float, float] | None] = {}


def geocode(addr: str, city: str, state: str) -> tuple[float, float] | None:
    key = f"{addr}|{city}|{state}"
    if key in _geo_cache:
        return _geo_cache[key]
    q = ", ".join(p for p in (clean_addr(addr), city, state) if p)
    url = ("https://nominatim.openstreetmap.org/search?q="
           + urllib.parse.quote(q) + "&format=json&limit=1")
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.loads(resp.read())
        val = (float(results[0]["lat"]), float(results[0]["lon"])) if results else None
    except Exception:
        val = None
    _geo_cache[key] = val
    time.sleep(1.1)  # Nominatim policy
    return val


# --- Main --------------------------------------------------------------------

def main() -> None:
    dry = "--dry-run" in sys.argv
    records = json.loads(IN.read_text())
    print(f"{len(records)} scraped records")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    existing = conn.execute(
        "SELECT id, name, city, address, lat, lng, phone, website, state, "
        "karaoke_nights FROM venues"
    ).fetchall()
    print(f"{len(existing)} existing venues in db")

    ex_by_key: dict[tuple[str, str], sqlite3.Row] = {}
    for v in existing:
        ex_by_key[(norm_name(v["name"]), (v["city"] or "").lower())] = v

    inserted = updated = matched = skipped = 0
    unmatched_geo: list[dict] = []

    for i, rec in enumerate(records, 1):
        name = (rec.get("name") or "").strip()
        city = (rec.get("city") or "").strip()
        state = usps(rec.get("state") or "")
        street = (rec.get("street") or "").strip()
        if not name or not city:
            skipped += 1
            continue
        nn = norm_name(name)

        # 1) exact normalized name + city
        hit = ex_by_key.get((nn, city.lower()))
        # 2) name containment + same city
        if hit is None:
            for (en, ec), v in ex_by_key.items():
                if ec == city.lower() and (nn in en or en in nn):
                    hit = v
                    break
        # 3) geocode + proximity
        lat = lng = None
        if hit is None and street and state:
            geo = geocode(street, city, state)
            if geo:
                lat, lng = geo
                for v in existing:
                    if v["lat"] and v["lng"]:
                        dlat = abs(v["lat"] - lat)
                        dlng = abs(v["lng"] - lng)
                        if dlat < 0.002 and dlng < 0.002:  # ~150m box
                            hit = v
                            break

        if hit is not None:
            matched += 1
            # Enrich: fill gaps only; never overwrite curated data.
            sets, vals = [], []
            if not hit["phone"] and rec.get("phone"):
                sets.append("phone=?")
                vals.append(rec["phone"])
            if not hit["website"] and rec.get("website"):
                sets.append("website=?")
                vals.append(rec["website"])
            if not hit["state"] and state:
                sets.append("state=?")
                vals.append(state)
            if sets:
                vals.append(hit["id"])
                if not dry:
                    conn.execute(f"UPDATE venues SET {', '.join(sets)} WHERE id=?", vals)
        else:
            if not state or not lat:
                unmatched_geo.append(rec)
            if not dry:
                conn.execute(
                    """INSERT INTO venues
                       (name, address, city, state, lat, lng, phone, website,
                        karaoke_nights, start_time, end_time, source, confidence)
                       VALUES (?,?,?,?,?,?,?,?,'','','', 'scrape:karaokelocations','unverified')""",
                    (
                        name, street or "", city,
                        state if len(state) == 2 else state,
                        lat if lat else 0.0,
                        lng if lng else 0.0,
                        rec.get("phone"), rec.get("website"),
                    ),
                )
            inserted += 1

        if i % 250 == 0:
            print(f"  {i}/{len(records)}: matched={matched} inserted={inserted} "
                  f"skipped={skipped} no-geo={len(unmatched_geo)}", flush=True)

    if not dry:
        conn.commit()
    conn.close()

    (BASE / "data" / "karaokelocations_import_report.json").write_text(
        json.dumps(
            {
                "total": len(records),
                "matched_existing": matched,
                "inserted": inserted,
                "skipped_missing_name_or_city": skipped,
                "inserted_without_geocode": len(unmatched_geo),
            },
            indent=1,
        )
    )
    print(f"DONE: matched={matched} inserted={inserted} skipped={skipped} "
          f"no-geo={len(unmatched_geo)} dry_run={dry}")


if __name__ == "__main__":
    main()
