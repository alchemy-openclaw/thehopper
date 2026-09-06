#!/usr/bin/env python3
"""Import Florida ABT liquor license CSV into a staging table in thehopper.db.

Creates fl_liquor_licenses table if it doesn't exist, then upserts all
on-premises retail licenses from the ABT CSV download.

Usage:
    cd ~/projects/thehopper/backend
    python3 ../data/import_liquor_licenses.py
"""

import csv
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "backend" / "thehopper.db"
CSV_PATH = Path(__file__).resolve().parent / "bd4006lic.csv"

# On-premises consumption license series (bars + restaurants that serve alcohol)
# 2COP = beer/wine on-premises, 4COP = spirits/full bar on-premises,
# 1COP = special, 5COP = hotel, 6COP = restaurant, 7COP = restaurant/special,
# 8COP = restaurant/special
ON_PREMISES_SERIES = {"2COP", "4COP", "1COP", "5COP", "6COP", "7COP", "8COP"}

# Keywords that suggest a bar/tavern/pub (vs a restaurant)
BAR_KEYWORDS = [
    "bar", "pub", "tavern", "saloon", "lounge", "nightclub", "night club",
    "taproom", "brewhaus", "brewhouse", "brewery", "ale house", "alehouse",
    "cantina", "dive", "spirits", "cocktail", "wine bar",
]

# Franchise/chain keywords — unlikely to host karaoke
CHAIN_KEYWORDS = [
    "applebee", "chili", "cracker barrel", "outback", "olive garden",
    "red lobster", "tgi", "friday", "ruby tuesday", "longhorn",
    "texas roadhouse", "perkins", "denny", "ihop", "waffle house",
    "mcdonald", "wendy", "burger king", "subway", "taco bell",
    "kfc", "pizza hut", "domino", "papa john", "chipotle",
    "panera", "starbucks", "dunkin", "sonny", "sonny's real pit",
    "smokey bones", "beef o brady", "beef o'brady", "flanigan",
    "miller's ale house", "bjs restaurant",
]


def is_bar_like(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in BAR_KEYWORDS)


def is_chain(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in CHAIN_KEYWORDS)


def create_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fl_liquor_licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_number TEXT UNIQUE,
            dba_name TEXT,
            owner_name TEXT,
            series TEXT,
            series_description TEXT,
            business_address TEXT,
            business_city TEXT,
            business_state TEXT,
            business_zip TEXT,
            county_code TEXT,
            license_status TEXT,
            original_issue_date TEXT,
            effective_date TEXT,
            expiration_date TEXT,
            is_on_premises INTEGER DEFAULT 0,
            is_bar_like INTEGER DEFAULT 0,
            is_chain INTEGER DEFAULT 0,
            lat REAL,
            lng REAL,
            geocoded INTEGER DEFAULT 0,
            has_karaoke INTEGER DEFAULT 0,
            karaoke_confidence TEXT,
            karaoke_nights TEXT,
            karaoke_start_time TEXT,
            karaoke_end_time TEXT,
            kj_name TEXT,
            kj_phone TEXT,
            kj_id INTEGER,
            imported_to_venues INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lic_county
        ON fl_liquor_licenses(county_code)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lic_bar_like
        ON fl_liquor_licenses(is_bar_like)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_lic_has_karaoke
        ON fl_liquor_licenses(has_karaoke)
    """)
    conn.commit()


SERIES_DESCRIPTIONS = {
    "2COP": "Beer/Wine (on-premises)",
    "4COP": "Spirits/Full Bar (on-premises)",
    "1COP": "Special (on-premises)",
    "5COP": "Hotel (on-premises)",
    "6COP": "Restaurant (on-premises)",
    "7COP": "Restaurant/Special (on-premises)",
    "8COP": "Restaurant/Special (on-premises)",
    "2APS": "Beer/Wine (package store)",
    "4APS": "Spirits (package store)",
    "1APS": "Special (package store)",
    "11C": "Community/Club",
    "11CG": "Community/Golf Club",
    "11PA": "Public/Civic",
    "11AL": "American Legion",
    "13CT": "Catering",
    "3PS": "Package Store",
    "3CPS": "Convenience Package",
}


def build_business_address(row: dict) -> str:
    parts = [
        row.get("Location Address 1", "").strip(),
        row.get("Location Address 2", "").strip(),
        row.get("Location Address 3", "").strip(),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else ""


def import_csv(conn, csv_path: Path):
    with open(csv_path, "r", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    active = 0
    on_premises = 0
    inserted = 0
    updated = 0

    for row in rows:
        # Only active licenses
        if row.get("Primary Status") != "20":
            continue
        if row.get("Secondary Status") != "20":
            continue
        active += 1

        series = row.get("Series", "").strip()
        is_on_prem = series in ON_PREMISES_SERIES
        if is_on_prem:
            on_premises += 1

        dba = row.get("DBA", "").strip()
        if not dba:
            dba = row.get("Owner Name", "").strip()

        bar_like = is_bar_like(dba)
        chain = is_chain(dba)

        addr = build_business_address(row)
        city = row.get("Location City", "").strip()
        state = row.get("Location State", "").strip()
        zip_code = row.get("Location ZIP", "").strip()
        county = row.get("Location County", "").strip()
        license_num = row.get("License Number", "").strip()
        series_desc = SERIES_DESCRIPTIONS.get(series, series)

        existing = conn.execute(
            "SELECT id FROM fl_liquor_licenses WHERE license_number = ?",
            (license_num,),
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE fl_liquor_licenses SET
                    dba_name = ?, owner_name = ?, series = ?,
                    series_description = ?, business_address = ?,
                    business_city = ?, business_state = ?, business_zip = ?,
                    county_code = ?, license_status = ?,
                    original_issue_date = ?, effective_date = ?,
                    expiration_date = ?, is_on_premises = ?,
                    is_bar_like = ?, is_chain = ?, updated_at = datetime('now')
                WHERE license_number = ?
            """, (dba, row.get("Owner Name", "").strip(), series, series_desc,
                  addr, city, state, zip_code, county, "active",
                  row.get("Original Licensure Date", "").strip(),
                  row.get("Effective Date", "").strip(),
                  row.get("Expiration Date", "").strip(),
                  1 if is_on_prem else 0,
                  1 if bar_like else 0,
                  1 if chain else 0,
                  license_num))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO fl_liquor_licenses (
                    license_number, dba_name, owner_name, series,
                    series_description, business_address, business_city,
                    business_state, business_zip, county_code,
                    license_status, original_issue_date, effective_date,
                    expiration_date, is_on_premises, is_bar_like, is_chain
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (license_num, dba, row.get("Owner Name", "").strip(), series,
                  series_desc, addr, city, state, zip_code, county, "active",
                  row.get("Original Licensure Date", "").strip(),
                  row.get("Effective Date", "").strip(),
                  row.get("Expiration Date", "").strip(),
                  1 if is_on_prem else 0,
                  1 if bar_like else 0,
                  1 if chain else 0))
            inserted += 1

    conn.commit()
    return total, active, on_premises, inserted, updated


def print_summary(conn):
    stats = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(is_on_premises) as on_prem,
            SUM(is_bar_like) as bar_like,
            SUM(is_chain) as chains,
            SUM(CASE WHEN is_on_premises AND is_bar_like AND NOT is_chain THEN 1 ELSE 0 END) as real_bars,
            SUM(geocoded) as geocoded,
            SUM(has_karaoke) as has_karaoke
        FROM fl_liquor_licenses
    """).fetchone()

    print(f"\n=== Import Summary ===")
    print(f"Total licenses imported:        {stats['total']}")
    print(f"On-premises licenses:           {stats['on_prem']}")
    print(f"Bar-like (by name):              {stats['bar_like']}")
    print(f"Chains (excluded):               {stats['chains']}")
    print(f"Real bars (on-prem + bar-like):  {stats['real_bars']}")
    print(f"Geocoded:                        {stats['geocoded']}")
    print(f"Has karaoke flag:                {stats['has_karaoke']}")

    # Top counties
    print(f"\n=== Top 10 counties (on-premises, bar-like, non-chain) ===")
    counties = conn.execute("""
        SELECT county_code, COUNT(*) as cnt
        FROM fl_liquor_licenses
        WHERE is_on_premises = 1 AND is_bar_like = 1 AND is_chain = 0
        GROUP BY county_code
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    for c in counties:
        print(f"  County {c['county_code']}: {c['cnt']} bars")

    # Brevard specifically
    print(f"\n=== Brevard County (code 15) ===")
    brevard = conn.execute("""
        SELECT COUNT(*) as total,
               SUM(is_bar_like) as bars,
               SUM(is_chain) as chains
        FROM fl_liquor_licenses
        WHERE county_code = '15' AND is_on_premises = 1
    """).fetchone()
    print(f"  On-premises: {brevard['total']}, bar-like: {brevard['bars']}, chains: {brevard['chains']}")


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: CSV file not found at {CSV_PATH}")
        print("Download it first:")
        print(f"  curl -sL -o {CSV_PATH} 'https://www2.myfloridalicense.com/sto/file_download/extracts/bd4006lic.csv'")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    print(f"CSV: {CSV_PATH}")
    print(f"DB:  {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("\nCreating table if needed...")
    create_table(conn)

    print("Importing CSV...")
    total, active, on_prem, inserted, updated = import_csv(conn, CSV_PATH)
    print(f"\nCSV rows:         {total}")
    print(f"Active licenses:  {active}")
    print(f"On-premises:      {on_prem}")
    print(f"Inserted:         {inserted}")
    print(f"Updated:          {updated}")

    print_summary(conn)
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
