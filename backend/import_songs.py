#!/usr/bin/env python3
"""Import KaraFun CSV catalog into the thehopper database.

Usage:
    cd backend
    source venv/bin/activate
    python import_songs.py

Replaces the existing seed_data songs (101 hand-curated) with the
KaraFun catalog (84,000+ songs). Keeps the songs table schema the same
but adds genre and year from KaraFun data.
"""
import csv
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "thehopper.db"
CSV_PATH = Path(__file__).parent.parent / "data" / "karafun_catalog.csv"


def parse_genre(styles: str) -> str:
    """KaraFun uses comma-separated styles. We store the first as genre."""
    if not styles:
        return "Pop"
    genres = [g.strip() for g in styles.split(",") if g.strip()]
    return genres[0] if genres else "Pop"


def parse_range_fit(genre: str) -> list[str]:
    """Approximate vocal range fit from genre. This is a rough heuristic
    for cold start -- the collaborative filtering engine will replace this
    once enough singing data is collected."""
    # Default: all ranges
    return ["bass", "baritone", "tenor", "alto", "mezzo", "soprano"]


def approximate_difficulty(year: int | None, genre: str) -> int:
    """Rough difficulty heuristic for cold start. 1=easy, 5=hard.
    This will be replaced by collaborative filtering."""
    return 3  # Default to moderate


def main():
    if not CSV_PATH.exists():
        print(f"CSV not found: {CSV_PATH}")
        sys.exit(1)

    # Parse the CSV (semicolon-delimited)
    songs = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        # Skip header
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            title = (row.get("Title") or "").strip()
            artist = (row.get("Artist") or "").strip()
            if not title or not artist:
                continue
            year_str = row.get("Year", "")
            try:
                year = int(year_str) if year_str else None
            except ValueError:
                year = None
            genre = parse_genre(row.get("Styles", ""))
            songs.append({
                "title": title,
                "artist": artist,
                "genre": genre,
                "year": year,
                "difficulty": approximate_difficulty(year, genre),
                "range_fit": ",".join(parse_range_fit(genre)),
                "notes": None,
            })

    print(f"Parsed {len(songs)} songs from KaraFun CSV")

    # Insert into database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Check current song count
    current = conn.execute("SELECT COUNT(*) as c FROM songs").fetchone()["c"]
    print(f"Current songs in DB: {current}")

    # Clear existing songs and insert new ones
    conn.execute("DELETE FROM songs")
    print("Cleared existing songs")

    # Batch insert
    batch_size = 500
    for i in range(0, len(songs), batch_size):
        batch = songs[i:i + batch_size]
        placeholders = ",".join(["(?,?,?,?,?,?,?)" for _ in batch])
        values = []
        for s in batch:
            values.extend([s["title"], s["artist"], s["genre"], s["year"],
                          s["difficulty"], s["range_fit"]])
        conn.executemany(
            "INSERT INTO songs (title, artist, genre, year, difficulty, range_fit, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            [(s["title"], s["artist"], s["genre"], s["year"],
              s["difficulty"], s["range_fit"], s["notes"]) for s in batch],
        )
        if (i // batch_size) % 10 == 0:
            print(f"  Inserted {i + len(batch)}/{len(songs)}...")

    conn.commit()
    final = conn.execute("SELECT COUNT(*) as c FROM songs").fetchone()["c"]
    print(f"Final song count: {final}")

    # Show some samples
    samples = conn.execute("SELECT title, artist, genre, year FROM songs ORDER BY RANDOM() LIMIT 5").fetchall()
    print("\nSamples:")
    for s in samples:
        print(f"  {s['title']} - {s['artist']} ({s['genre']}, {s['year']})")

    conn.close()


if __name__ == "__main__":
    main()
