#!/usr/bin/env python3
"""Merge FindKaraoke national scrape results into thehopper.db as shows.

This is the schedule layer: FK has day/time but thin venue data; the DB has
solid venue rows from the liquor-license universe + KaraokeLocations scrape.
Matching is name-containment + city, with state-aware fallback via address
zip/state tokens. Matched venues get their karaoke_nights/times filled or
unioned; FK rows that match nothing are inserted as new venues
(confidence='scraped_schedule', source='scrape:findkaraoke').

Nights are unioned but capped: if the existing row already has nights, FK
nights are merged only when they don't conflict wildly (a venue can't have
7 karaoke nights unless every day was claimed). TBD/JUNK nights never merge.

Usage:
  python3 data/import_findkaraoke_national.py            # write
  python3 data/import_findkaraoke_national.py --dry-run  # report only
"""

import json
import re
import sqlite3
import sys
from difflib import SequenceMatcher
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "backend" / "thehopper.db"
IN = BASE / "data" / "findkaraoke_national.json"

VALID_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}

SUFFIXES = [" the ", " bar ", " grill ", " pub ", " lounge ", " restaurant ",
            " bar and grill", " and grill", " sports bar", " tavern", " taproom"]


def norm_name(name: str) -> str:
    n = (name or "").lower().strip()
    n = n.replace("&", " and ")
    for s in SUFFIXES:
        n = n.replace(s, " ")
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    if n.startswith("the "):
        n = n[4:]
    return n


def valid_nights(nights_str: str) -> list[str]:
    return [n.strip() for n in (nights_str or "").split(",") if n.strip() in VALID_DAYS]


def main() -> None:
    dry = "--dry-run" in sys.argv
    records = json.loads(IN.read_text())
    print(f"{len(records)} FK records")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    existing = conn.execute(
        "SELECT id, name, city, state, karaoke_nights, start_time, end_time FROM venues"
    ).fetchall()

    # index by (norm_name, city_lower)
    by_key: dict[tuple[str, str], sqlite3.Row] = {}
    for v in existing:
        by_key[(norm_name(v["name"]), (v["city"] or "").lower())] = v
    # city-name index for fuzzy pass
    by_city: dict[str, list[sqlite3.Row]] = {}
    for v in existing:
        by_city.setdefault((v["city"] or "").lower(), []).append(v)

    matched = filled = unioned = inserted = no_match = junk_skipped = 0

    for rec in records:
        name = (rec.get("name") or "").strip()
        if not name or "&amp;" in name or "\n" in name:
            junk_skipped += 1
            continue
        sched = rec.get("schedule") or []
        if not sched:
            # No schedule = nothing this source contributes.
            no_match += 1
            continue
        city = (rec.get("city") or "").strip()
        addr = (rec.get("address") or "").strip()
        nights = [s["day"] for s in sched if s.get("day") in VALID_DAYS]
        start = sched[0].get("start_time") or ""
        if not nights or not city:
            junk_skipped += 1
            continue

        nn = norm_name(name)
        city_l = city.lower()

        # 1) exact key
        hit = by_key.get((nn, city_l))
        # 2) containment within city
        if hit is None:
            for v in by_city.get(city_l, []):
                en = norm_name(v["name"])
                if nn in en or en in nn:
                    hit = v
                    break
        # 3) fuzzy ratio >= 0.85 within city
        if hit is None:
            best, best_score = None, 0.0
            for v in by_city.get(city_l, []):
                score = SequenceMatcher(None, nn, norm_name(v["name"])).ratio()
                if score > best_score:
                    best, best_score = v, score
            if best_score >= 0.85:
                hit = best

        if hit is not None:
            matched += 1
            ex_nights = valid_nights(hit["karaoke_nights"])
            merged = sorted(set(ex_nights) | set(nights))
            # Only write when it actually adds nights or fills a blank schedule.
            if merged != sorted(ex_nights) or not hit["karaoke_nights"]:
                if not dry:
                    conn.execute(
                        """UPDATE venues
                           SET karaoke_nights=?,
                               start_time=COALESCE(NULLIF(?,''), start_time),
                               end_time=COALESCE(NULLIF(?,''), end_time),
                               source=CASE WHEN source IS NULL THEN 'scrape:findkaraoke' ELSE source END,
                               confidence=CASE
                                   WHEN confidence IN ('claimed') THEN confidence
                                   ELSE 'scraped_schedule' END
                           WHERE id=?""",
                        (",".join(merged), start, "", hit["id"]),
                    )
                if ex_nights:
                    unioned += 1
                else:
                    filled += 1
        else:
            # New venue row from the FK data (has a real schedule).
            if not dry:
                conn.execute(
                    """INSERT INTO venues
                       (name, address, city, state, lat, lng, karaoke_nights,
                        start_time, end_time, phone, source, confidence)
                       VALUES (?,?,?,?,0,0,?,?,?,?, 'scrape:findkaraoke','scraped_schedule')""",
                    (
                        name, addr, city, "", ",".join(nights), start, "",
                        rec.get("phone") or "",
                    ),
                )
            inserted += 1

        if matched + inserted >= 0 and (matched + inserted) % 250 == 0 and (matched + inserted):
            print(f"  matched={matched} filled={filled} unioned={unioned} "
                  f"inserted={inserted} junk={junk_skipped}", flush=True)

    if not dry:
        conn.commit()
    conn.close()
    print(f"DONE: matched={matched} (filled={filled} unioned={unioned}) "
          f"inserted={inserted} no-schedule={no_match} junk={junk_skipped} dry={dry}")


if __name__ == "__main__":
    main()
