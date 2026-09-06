#!/usr/bin/env python3
"""Geocode Florida liquor license venues via Nominatim.

Two-pass approach:
1. Try precise address geocoding (street + city + state + zip)
2. If that fails, fall back to city + state + zip (less precise but better than nothing)
3. If that fails, fall back to zip code only

Rate limit: 1 req/sec (Nominatim usage policy)

Usage:
    cd ~/projects/thehopper
    python3 data/geocode_liquor.py [--bars-only] [--limit N]
"""

import sqlite3
import sys
import time
import urllib.request
import urllib.parse
import json
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "thehopper.db"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "karaokespot-us/1.0 (contact@alchemycreativelounge.com)"


def geocode_nominatim(query: str):
    """Geocode a query string via Nominatim. Returns (lat, lng) or (None, None)."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and len(data) > 0:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None, None


def geocode_venue(address: str, city: str, state: str, zip_code: str):
    """Multi-pass geocoding. Returns (lat, lng, precision) or (None, None, None)."""
    state = state or "FL"

    # Pass 1: full street address
    if address and city:
        q = f"{address}, {city}, {state} {zip_code}".strip()
        lat, lng = geocode_nominatim(q)
        if lat:
            return lat, lng, "address"
        time.sleep(1.0)

    # Pass 2: city + zip (no street — sometimes the street format is wrong)
    if city and zip_code:
        q = f"{city}, {state} {zip_code}"
        lat, lng = geocode_nominatim(q)
        if lat:
            return lat, lng, "city"
        time.sleep(1.0)

    # Pass 3: zip code only (centroid — approximate but better than nothing)
    if zip_code and len(zip_code) >= 5:
        zip5 = zip_code[:5]
        q = f"{zip5}, {state}"
        lat, lng = geocode_nominatim(q)
        if lat:
            return lat, lng, "zip"
        time.sleep(1.0)

    return None, None, None


def main():
    bars_only = "--bars-only" in sys.argv
    limit_arg = None
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit_arg = int(sys.argv[i + 1])
            break

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if bars_only:
        query = """
            SELECT id, dba_name, business_address, business_city,
                   business_state, business_zip
            FROM fl_liquor_licenses
            WHERE is_on_premises = 1 AND is_bar_like = 1 AND is_chain = 0
              AND geocoded = 0
            ORDER BY id
        """
        label = "bar-like venues (non-chain)"
    else:
        query = """
            SELECT id, dba_name, business_address, business_city,
                   business_state, business_zip
            FROM fl_liquor_licenses
            WHERE is_on_premises = 1 AND geocoded = 0
            ORDER BY id
        """
        label = "on-premises venues"

    if limit_arg:
        query += f" LIMIT {limit_arg}"

    rows = conn.execute(query).fetchall()
    total = len(rows)
    print(f"Geocoding {total} {label}...")
    print(f"(Rate limited to 1 req/sec — this will take ~{total * 3 // 60} min)")

    success_addr = 0
    success_city = 0
    success_zip = 0
    fail = 0

    for i, row in enumerate(rows):
        lat, lng, precision = geocode_venue(
            str(row["business_address"] or ""),
            str(row["business_city"] or ""),
            str(row["business_state"] or "FL"),
            str(row["business_zip"] or ""),
        )

        if lat is not None:
            conn.execute(
                "UPDATE fl_liquor_licenses SET lat = ?, lng = ?, geocoded = 1 WHERE id = ?",
                (lat, lng, row["id"]),
            )
            if precision == "address":
                success_addr += 1
            elif precision == "city":
                success_city += 1
            else:
                success_zip += 1
        else:
            conn.execute(
                "UPDATE fl_liquor_licenses SET geocoded = 1 WHERE id = ?",
                (row["id"],),
            )
            fail += 1

        if (i + 1) % 50 == 0:
            conn.commit()
            print(f"  {i + 1}/{total} — addr:{success_addr} city:{success_city} zip:{success_zip} fail:{fail}")

        # Rate limit
        time.sleep(1.0)

    conn.commit()
    print(f"\nDone:")
    print(f"  Address-level:  {success_addr}")
    print(f"  City-level:     {success_city}")
    print(f"  ZIP-level:      {success_zip}")
    print(f"  Failed:         {fail}")
    print(f"  Total success:  {success_addr + success_city + success_zip}/{total}")

    # Summary
    stats = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN lat IS NOT NULL THEN 1 ELSE 0 END) as with_coords
        FROM fl_liquor_licenses
        WHERE is_on_premises = 1 AND is_bar_like = 1 AND is_chain = 0
    """).fetchone()
    print(f"\nBar-like non-chain venues: {stats['total']}")
    print(f"  With coordinates: {stats['with_coords']}")

    conn.close()


if __name__ == "__main__":
    main()
