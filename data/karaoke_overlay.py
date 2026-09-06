#!/usr/bin/env python3
"""Match KaraokeLocations.com data against liquor license DB.

Tight matching: require exact normalized name match OR 
significant word overlap + same city. No false positives.

Unmatched venues are saved as a separate JSON for manual review —
these are confirmed karaoke venues that don't have a liquor license
(karaoke-only bars, KJ services, private rooms, etc.).

Usage:
    cd ~/projects/thehopper
    python3 data/karaoke_overlay.py
"""

import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "thehopper.db"
KARAOKE_JSON = Path(__file__).resolve().parent / "karaokelocations_fl.json"
UNMATCHED_JSON = Path(__file__).resolve().parent / "karaokelocations_unmatched.json"


def normalize(name: str) -> str:
    n = name.lower().strip()
    for suffix in [" inc", " llc", " corp", " co", " the", " ltd", " company"]:
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    n = re.sub(r"[^a-z0-9\s]", "", n)
    return re.sub(r"\s+", " ", n).strip()


def extract_city(addr) -> str:
    if isinstance(addr, dict):
        return addr.get("addressLocality", "").lower().strip()
    return ""


def extract_street(addr) -> str:
    if isinstance(addr, dict):
        return addr.get("streetAddress", "")
    return addr if isinstance(addr, str) else ""


def name_match(a: str, b: str) -> bool:
    na = normalize(a)
    nb = normalize(b)
    if not na or not nb:
        return False
    # Exact
    if na == nb:
        return True
    # One contains the other (but must be at least 4 chars to avoid "bar" matching "barbershop")
    if len(na) >= 4 and len(nb) >= 4:
        if na in nb or nb in na:
            return True
    return False


def word_overlap_match(a: str, b: str, min_ratio=0.7) -> bool:
    na = normalize(a)
    nb = normalize(b)
    words_a = set(na.split())
    words_b = set(nb.split())
    if len(words_a) < 2 or len(words_b) < 2:
        return False
    overlap = words_a & words_b
    ratio = len(overlap) / min(len(words_a), len(words_b))
    return ratio >= min_ratio


def main():
    if not KARAOKE_JSON.exists():
        print(f"ERROR: {KARAOKE_JSON} not found. Run the scraper first.")
        return

    venues = json.loads(KARAOKE_JSON.read_text())
    print(f"Loaded {len(venues)} karaoke venues from KaraokeLocations.com")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Get all on-premises licenses
    licenses = conn.execute("""
        SELECT id, dba_name, business_address, business_city, business_zip
        FROM fl_liquor_licenses WHERE is_on_premises = 1
    """).fetchall()
    print(f"Matching against {len(licenses)} on-premises licenses")

    matched = 0
    unmatched = []

    for kv in venues:
        kv_name = kv.get("name", "").strip()
        if not kv_name:
            continue

        kv_city = extract_city(kv.get("address", ""))
        kv_street = extract_street(kv.get("address", ""))
        kv_phone = (kv.get("phone") or "").strip()

        found = False
        best_match = None

        for lic in licenses:
            lic_name = lic["dba_name"] or ""
            if not lic_name:
                continue

            # Pass 1: exact normalized name match
            if name_match(kv_name, lic_name):
                best_match = lic
                break

            # Pass 2: word overlap + city match
            if word_overlap_match(kv_name, lic_name, min_ratio=0.7):
                lic_city = (lic["business_city"] or "").lower().strip()
                if kv_city and lic_city:
                    if kv_city == lic_city or kv_city in lic_city or lic_city in kv_city:
                        best_match = lic
                        break

        if best_match:
            conn.execute("""
                UPDATE fl_liquor_licenses
                SET has_karaoke = 1, karaoke_confidence = 'confirmed',
                    kj_phone = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (kv_phone, best_match["id"]))
            matched += 1
            print(f"  MATCH: {kv_name} -> {best_match['dba_name']} ({best_match['business_city']})")
        else:
            unmatched.append({
                "name": kv_name,
                "address": kv_street,
                "city": kv_city,
                "phone": kv_phone,
                "url": kv.get("url", ""),
                "description": kv.get("description", ""),
                "rating": kv.get("rating", ""),
                "review_count": kv.get("review_count", ""),
            })

    conn.commit()

    # Save unmatched for manual review
    if unmatched:
        UNMATCHED_JSON.write_text(json.dumps(unmatched, indent=2))

    print(f"\n=== Overlay Summary ===")
    print(f"Karaoke venues from KaraokeLocations.com: {len(venues)}")
    print(f"Matched to liquor licenses:                {matched}")
    print(f"Unmatched (saved for review):              {len(unmatched)}")

    if unmatched:
        print(f"\n=== Unmatched venues (confirmed karaoke, no liquor license match) ===")
        for v in unmatched:
            print(f"  {v['name']} — {v['address']}, {v['city']} — {v['phone']}")

    # DB stats
    count = conn.execute(
        "SELECT COUNT(*) as c FROM fl_liquor_licenses WHERE has_karaoke = 1"
    ).fetchone()
    print(f"\nTotal has_karaoke=1 in DB: {count['c']}")

    # Show geocoding progress
    geo = conn.execute("""
        SELECT
            SUM(CASE WHEN geocoded = 1 AND lat IS NOT NULL THEN 1 ELSE 0 END) as geocoded,
            SUM(CASE WHEN geocoded = 1 AND lat IS NULL THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN geocoded = 0 THEN 1 ELSE 0 END) as remaining
        FROM fl_liquor_licenses
        WHERE is_on_premises = 1 AND is_bar_like = 1 AND is_chain = 0
    """).fetchone()
    print(f"\nGeocoding progress (bar-like non-chain):")
    print(f"  Geocoded:  {geo['geocoded']}")
    print(f"  Failed:    {geo['failed']}")
    print(f"  Remaining:  {geo['remaining']}")

    conn.close()


if __name__ == "__main__":
    main()
