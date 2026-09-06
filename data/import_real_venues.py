#!/usr/bin/env python3
"""Replace placeholder venues with real data from the liquor license staging table.

1. Delete the 15 placeholder venues (555 phone numbers, example.com URLs)
2. Import Brevard County bar-like venues from fl_liquor_licenses
3. Import the 22 unmatched KaraokeLocations.com venues as new venues
4. Approve the 2 real Kennedy's Lamp Post submissions from venue_submissions

Usage:
    cd ~/projects/thehopper
    python3 data/import_real_venues.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "thehopper.db"


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # ── Step 1: Delete placeholder venues ──────────────────────────────
    placeholders = conn.execute("""
        SELECT id, name FROM venues
        WHERE phone LIKE '%555%' OR website LIKE '%example.com%'
    """).fetchall()
    print(f"Step 1: Deleting {len(placeholders)} placeholder venues")
    for v in placeholders:
        print(f"  Deleting: {v['name']}")
    conn.execute("DELETE FROM venues WHERE phone LIKE '%555%' OR website LIKE '%example.com%'")
    conn.commit()

    # ── Step 2: Import Brevard bar-like venues from liquor licenses ──
    print("\nStep 2: Importing Brevard County bar-like venues")
    brevard = conn.execute("""
        SELECT dba_name, business_address, business_city, business_state,
               business_zip, lat, lng, series, has_karaoke, kj_phone
        FROM fl_liquor_licenses
        WHERE county_code = '15'
          AND is_on_premises = 1
          AND is_bar_like = 1
          AND is_chain = 0
          AND lat IS NOT NULL
        ORDER BY business_city, dba_name
    """).fetchall()
    print(f"  Found {len(brevard)} Brevard bar-like venues with coordinates")

    imported = 0
    skipped = 0
    for r in brevard:
        # Build full address
        addr = r["business_address"]
        if r["business_zip"] and len(r["business_zip"]) >= 5:
            zip5 = r["business_zip"][:5]
            full_addr = f"{addr}, {r['business_city']}, {r['business_state']} {zip5}"
        else:
            full_addr = f"{addr}, {r['business_city']}, {r['business_state']}"

        # Check if this venue already exists by name + address
        existing = conn.execute(
            "SELECT id FROM venues WHERE name = ? AND address = ?",
            (r["dba_name"], full_addr),
        ).fetchone()

        if existing:
            skipped += 1
            continue

        # Determine karaoke fields
        if r["has_karaoke"]:
            karaoke_nights = "TBD"
            start_time = "20:00"
            end_time = "00:00"
        else:
            karaoke_nights = ""
            start_time = ""
            end_time = ""

        conn.execute("""
            INSERT INTO venues (
                name, address, city, lat, lng,
                karaoke_nights, start_time, end_time,
                phone, website, vibe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["dba_name"],
            full_addr,
            r["business_city"],
            r["lat"],
            r["lng"],
            karaoke_nights,
            start_time,
            end_time,
            r["kj_phone"] or "",
            "",
            "",
        ))
        imported += 1

    conn.commit()
    print(f"  Imported: {imported}, Skipped (already exist): {skipped}")

    # ── Step 3: Import unmatched KaraokeLocations.com venues ──────────
    print("\nStep 3: Importing unmatched KaraokeLocations.com venues")
    import json
    unmatched_path = Path(__file__).resolve().parent / "karaokelocations_unmatched.json"
    if unmatched_path.exists():
        unmatched = json.loads(unmatched_path.read_text())
        print(f"  Found {len(unmatched)} unmatched karaoke venues")

        # These are confirmed karaoke venues — mark karaoke_nights as TBD
        imported_k = 0
        for v in unmatched:
            name = v.get("name", "").strip()
            if not name:
                continue
            address = v.get("address", "")
            city = v.get("city", "").title() if v.get("city") else "Unknown"
            phone = v.get("phone", "")

            # Check if already exists
            existing = conn.execute(
                "SELECT id FROM venues WHERE name = ? AND city = ?",
                (name, city),
            ).fetchone()
            if existing:
                continue

            # These don't have coordinates yet — use 0,0 as placeholder
            # (they'll get geocoded later)
            conn.execute("""
                INSERT INTO venues (
                    name, address, city, lat, lng,
                    karaoke_nights, start_time, end_time,
                    phone, website
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                address,
                city,
                0.0,  # Will geocode later
                0.0,
                "TBD",
                "20:00",
                "00:00",
                phone,
                "",
            ))
            imported_k += 1
        conn.commit()
        print(f"  Imported: {imported_k}")
    else:
        print("  No unmatched file found — skipping")

    # ── Step 4: Approve real pending submissions ───────────────────────
    print("\nStep 4: Approving real pending venue submissions")
    pending = conn.execute("""
        SELECT id, name, address, city, lat, lng, karaoke_nights,
               start_time, end_time, kj_name, phone, vibe
        FROM venue_submissions
        WHERE status = 'pending'
          AND name NOT LIKE '%Alchemy%'
          AND name NOT LIKE '%Test%'
          AND submitter_phone IS NOT NULL
    """).fetchall()

    approved = 0
    for s in pending:
        print(f"  Approving: {s['name']} — {s['address']}, {s['city']}")

        # Check if venue already exists by name
        existing = conn.execute(
            "SELECT id FROM venues WHERE name = ?", (s["name"],)
        ).fetchone()

        if existing:
            # Update existing venue
            venue_id = existing["id"]
            if s["lat"] and s["lng"]:
                conn.execute(
                    "UPDATE venues SET lat = ?, lng = ? WHERE id = ?",
                    (s["lat"], s["lng"], venue_id),
                )
            if s["kj_name"]:
                conn.execute(
                    "UPDATE venues SET kj_name = ? WHERE id = ?",
                    (s["kj_name"], venue_id),
                )
        else:
            # Insert new venue
            conn.execute("""
                INSERT INTO venues (
                    name, address, city, lat, lng,
                    karaoke_nights, start_time, end_time,
                    kj_name, phone, vibe
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                s["name"],
                s["address"],
                s["city"],
                s["lat"] or 0.0,
                s["lng"] or 0.0,
                s["karaoke_nights"] or "TBD",
                s["start_time"] or "20:00",
                s["end_time"] or "00:00",
                s["kj_name"] or "",
                s["phone"] or "",
                s["vibe"] or "",
            ))
            venue_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Mark submission as approved
        conn.execute("""
            UPDATE venue_submissions
            SET status = 'approved', reviewed_at = datetime('now'), venue_id = ?
            WHERE id = ?
        """, (venue_id, s["id"]))
        approved += 1

    conn.commit()
    print(f"  Approved: {approved}")

    # ── Summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("=== FINAL VENUES TABLE SUMMARY ===")
    total = conn.execute("SELECT COUNT(*) as c FROM venues").fetchone()
    print(f"Total venues: {total['c']}")

    # By city
    print("\nVenues by city (top 15):")
    cities = conn.execute("""
        SELECT city, COUNT(*) as cnt FROM venues
        GROUP BY city ORDER BY cnt DESC LIMIT 15
    """).fetchall()
    for c in cities:
        print(f"  {c['city']}: {c['cnt']}")

    # By has-karaoke
    karaoke = conn.execute("""
        SELECT COUNT(*) as c FROM venues WHERE karaoke_nights != '' AND karaoke_nights IS NOT NULL
    """).fetchone()
    print(f"\nVenues with karaoke nights set: {karaoke['c']}")

    # Brevard specifically
    bre_count = conn.execute("""
        SELECT COUNT(*) as c FROM venues WHERE city IN (
            'Cocoa Beach', 'Melbourne', 'Palm Bay', 'Rockledge',
            'Titusville', 'Cape Canaveral', 'Viera', 'Satellite Beach',
            'Indian Harbour Beach', 'Merritt Island', 'West Melbourne',
            'Cocoa', 'Melbourne Beach'
        )
    """).fetchone()
    print(f"Brevard County venues: {bre_count['c']}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
