#!/usr/bin/env python3
"""Generate sitemap.xml + robots.txt covering the SEO hub pages.

Written to frontend/public/ so the SPA build ships them as static files
(served at /sitemap.xml and /robots.txt). Hub URLs only — the SPA's own
routes are already covered by whatever robots config exists.

Regenerate whenever the directory grows materially (monthly is plenty).
"""

import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "frontend" / "public"
DB = BASE / "backend" / "thehopper.db"
BASE_URL = "https://karaokespot.us"

STATE_NAMES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "DC": "district of columbia", "FL": "florida", "GA": "georgia", "HI": "hawaii",
    "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york",
    "NC": "north carolina", "ND": "north dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island",
    "SC": "south carolina", "SD": "south dakota", "TN": "tennessee", "TX": "texas",
    "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington",
    "WV": "west virginia", "WI": "wisconsin", "WY": "wyoming",
}


def city_slug(city: str) -> str:
    return city.strip().lower().replace(" ", "-")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    urls = [f"{BASE_URL}/karaoke/"]
    seen_states: set[str] = set()
    rows = conn.execute(
        """SELECT state, city, COUNT(*) n FROM venues
           WHERE state IS NOT NULL AND state != '' AND city != ''
           GROUP BY state, city"""
    ).fetchall()
    for r in rows:
        st = r["state"].upper()
        if st not in STATE_NAMES:
            continue
        if st not in seen_states:
            seen_states.add(st)
            urls.append(f"{BASE_URL}/karaoke/{st.lower()}")
        urls.append(f"{BASE_URL}/karaoke/{st.lower()}/{city_slug(r['city'])}")
    conn.close()

    # Sitemaps cap at 50k URLs / 50MB — we're far under.
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        body.append(f"  <url><loc>{u}</loc></url>")
    body.append("</urlset>")
    (OUT / "sitemap.xml").write_text("\n".join(body) + "\n")

    (OUT / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        f"Sitemap: {BASE_URL}/sitemap.xml\n"
    )
    print(f"wrote sitemap.xml ({len(urls)} urls) and robots.txt -> {OUT}")


if __name__ == "__main__":
    main()
