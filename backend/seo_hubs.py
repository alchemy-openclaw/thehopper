#!/usr/bin/env python3
"""Server-rendered SEO hub pages for the national directory.

/karaoke/            — all states
/karaoke/{state}     — cities in a state ("karaoke in florida")
/karaoke/{state}/{city} — venues in a city ("karaoke in tampa fl")

Static HTML, no JS, schema.org structured data (ItemList > Event with
eventSchedule for venues that have nights). Served by FastAPI before the SPA
catch-all, so crawlers get real content.
"""

import html
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "thehopper.db"

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
NAME_TO_STATE = {v: k for k, v in STATE_NAMES.items()}

# Valid day names for schedule data + their schema.org DayOfWeek tokens.
DAY_SCHEMA = {
    "monday": "Monday", "tuesday": "Tuesday", "wednesday": "Wednesday",
    "thursday": "Thursday", "friday": "Friday", "saturday": "Saturday",
    "sunday": "Sunday",
}
DAY_KEYS = set(DAY_SCHEMA)

BASE_URL = "https://karaokespot.us"

_CSS = """
:root { --ink: #1a1a1a; --dim: #555; --line: #ddd; --bg: #fdfdfb; --card: #fff; }
* { box-sizing: border-box; }
body {
  font-family: Georgia, 'Times New Roman', serif;
  color: var(--ink); background: var(--bg);
  max-width: 46rem; margin: 0 auto; padding: 2rem 1.25rem 4rem;
  line-height: 1.5;
}
header a { color: var(--ink); text-decoration: none; font-size: 0.9rem; }
h1 { font-size: 1.9rem; font-weight: 700; margin: 1rem 0 0.25rem; letter-spacing: -0.02em; }
h1 a { color: inherit; text-decoration: none; }
.count { color: var(--dim); margin: 0 0 2rem; font-size: 0.95rem; }
h2 { font-size: 1.05rem; text-transform: lowercase; letter-spacing: 0.04em; color: var(--dim); margin: 2rem 0 0.75rem; font-weight: 600; }
ul.grid { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr)); gap: 0.4rem 1.5rem; }
ul.grid a { color: var(--ink); text-decoration: none; }
ul.grid a:hover { text-decoration: underline; }
.venue { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 1rem 1.25rem; margin-bottom: 0.8rem; }
.venue h3 { margin: 0 0 0.15rem; font-size: 1.15rem; }
.venue h3 a { color: inherit; text-decoration: none; }
.addr { color: var(--dim); font-size: 0.92rem; margin: 0; }
.nights { margin: 0.5rem 0 0; font-size: 0.95rem; }
.nights span { display: inline-block; background: #eef4ee; border: 1px solid #d8e6d8; border-radius: 999px; padding: 0.1rem 0.6rem; margin: 0.15rem 0.2rem 0 0; font-size: 0.85rem; }
footer { margin-top: 3rem; color: var(--dim); font-size: 0.85rem; border-top: 1px solid var(--line); padding-top: 1rem; }
footer a { color: var(--dim); }
.add { background: #f2f6f2; border: 1px dashed #b9ceb9; border-radius: 10px; padding: 1rem 1.25rem; margin: 2rem 0; font-size: 0.95rem; }
.add a { color: var(--ink); }
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _page(title: str, desc: str, canonical: str, body: str, jsonld: dict | None = None) -> str:
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{html.escape(canonical)}">
<style>{_CSS}</style>
{ld}
</head><body>
<header><a href="{BASE_URL}/karaoke/">&larr; karaoke near you</a></header>
{body}
<footer>
karaoke shows, hosts, and venues across the us · data community-maintained ·
<a href="{BASE_URL}">karaokespot.us</a> ·
<a href="{BASE_URL}/privacy">privacy</a>
</footer>
</body></html>"""


def _fmt_nights(v: sqlite3.Row) -> str:
    nights = [n.strip() for n in (v["karaoke_nights"] or "").split(",") if n.strip()]
    if not nights:
        return ""
    start = v["start_time"] or ""
    end = v["end_time"] or ""
    timebit = f" · {start}" + (f"–{end}" if end and end != start else "") if start else ""
    kj_name = v["kj_name"] or ""
    kj = f" · host: {html.escape(kj_name)}" if kj_name else ""
    spans = "".join(f"<span>{html.escape(n)}</span>" for n in nights)
    return f'<p class="nights">{spans}{timebit}{kj}</p>'


# --- pages -------------------------------------------------------------------

def states_index() -> str:
    conn = _conn()
    rows = conn.execute(
        """SELECT state, COUNT(*) AS n, COUNT(DISTINCT city) AS cities
           FROM venues WHERE state IS NOT NULL AND state != ''
           GROUP BY state ORDER BY n DESC"""
    ).fetchall()
    conn.close()

    links = []
    for r in rows:
        st = r["state"]
        name = STATE_NAMES.get(st, st.lower())
        links.append(
            f'<li><a href="{BASE_URL}/karaoke/{st.lower()}">{html.escape(name)}</a> '
            f'({r["n"]})</li>'
        )
    body = f"""<h1>karaoke near you</h1>
<p class="count">{sum(r['n'] for r in rows)} venues across {len(rows)} states. find a night, grab the mic.</p>
<h2>states</h2>
<ul class="grid">{''.join(links)}</ul>"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": f"karaoke in {STATE_NAMES.get(r['state'], r['state'].lower())}",
                "url": f"{BASE_URL}/karaoke/{r['state'].lower()}",
            }
            for i, r in enumerate(rows)
        ],
    }
    return _page(
        "karaoke near you — venues and weekly shows by state",
        "find karaoke nights by state and city. weekly show schedules, hosts, and venue info across the us.",
        f"{BASE_URL}/karaoke/",
        body,
        jsonld,
    )


def state_page(state: str) -> str | None:
    st = state.upper()
    if st not in STATE_NAMES:
        return None
    name = STATE_NAMES[st]
    conn = _conn()
    cities = conn.execute(
        """SELECT city, COUNT(*) AS n,
                  SUM(CASE WHEN karaoke_nights != '' THEN 1 ELSE 0 END) AS with_nights
           FROM venues WHERE state = ? AND city != ''
           GROUP BY city ORDER BY city""",
        (st,),
    ).fetchall()
    conn.close()
    if not cities:
        return None

    links = []
    for c in cities:
        city_slug = c["city"].lower().replace(" ", "-")
        suffix = f" ({c['with_nights']} with schedule)" if c["with_nights"] else ""
        links.append(
            f'<li><a href="{BASE_URL}/karaoke/{st.lower()}/{city_slug}">'
            f'{html.escape(c["city"])}</a> ({c["n"]}{suffix})</li>'
        )
    total = sum(c["n"] for c in cities)
    body = f"""<h1>karaoke in {html.escape(name)}</h1>
<p class="count">{total} venues in {len(cities)} cities.</p>
<h2>cities</h2>
<ul class="grid">{''.join(links)}</ul>"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": f"karaoke in {c['city']}, {st}",
                "url": f"{BASE_URL}/karaoke/{st.lower()}/{c['city'].lower().replace(' ', '-')}",
            }
            for i, c in enumerate(cities)
        ],
    }
    return _page(
        f"karaoke in {name} — {total} venues by city",
        f"find karaoke nights in {name}. {total} venues across {len(cities)} cities with weekly show schedules.",
        f"{BASE_URL}/karaoke/{st.lower()}",
        body,
        jsonld,
    )


def city_page(state: str, city_slug: str) -> str | None:
    st = state.upper()
    if st not in STATE_NAMES:
        return None
    city = city_slug.replace("-", " ").title()
    # handle multi-word title quirks: "st. petersburg" etc. — match loosely
    conn = _conn()
    venues = conn.execute(
        """SELECT * FROM venues
           WHERE state = ? AND LOWER(REPLACE(city, '-', ' ')) = ?
           ORDER BY CASE WHEN karaoke_nights != '' THEN 0 ELSE 1 END, name""",
        (st, city.lower()),
    ).fetchall()
    conn.close()
    if not venues:
        return None
    real_city = venues[0]["city"]

    cards = []
    events = []
    for i, v in enumerate(venues):
        addr_bits = [b for b in (v["address"], v["city"], st) if b]
        addr = html.escape(", ".join(addr_bits))
        phone = (
            f' · <a href="tel:{html.escape(v["phone"])}">{html.escape(v["phone"])}</a>'
            if v["phone"]
            else ""
        )
        nights_html = _fmt_nights(v)
        cards.append(
            f"""<div class="venue">
<h3>{html.escape(v["name"])}</h3>
<p class="addr">{addr}{phone}</p>
{nights_html}
</div>"""
        )
        if v["karaoke_nights"]:
            days = [
                n.strip().lower()
                for n in v["karaoke_nights"].split(",")
                if n.strip().lower() in DAY_KEYS
            ]
            if days:
                by_day = [
                    {
                        "@type": "Schedule",
                        "byDay": [DAY_SCHEMA[d] for d in days],
                        "repeatFrequency": "P1W",
                    }
                ]
                events.append(
                    {
                        "@type": "ListItem",
                        "position": len(events) + 1,
                        "item": {
                            "@type": "Event",
                            "name": f"Karaoke at {v['name']}",
                            "location": {
                                "@type": "Place",
                                "name": v["name"],
                                "address": ", ".join(
                                    b for b in (v["address"], v["city"], st) if b
                                ),
                            },
                            "eventSchedule": by_day,
                            "organizer": {"@type": "Organization", "name": v["name"]},
                        },
                    }
                )

    with_nights = sum(1 for v in venues if v["karaoke_nights"])
    body = f"""<h1>karaoke in {html.escape(real_city)}, {st.lower()}</h1>
<p class="count">{len(venues)} venues · {with_nights} with weekly karaoke nights listed.</p>
{''.join(cards)}
<div class="add">
run a karaoke night here that's missing or wrong? the directory is community-maintained —
open <a href="{BASE_URL}">karaokespot</a>, hit <strong>add a show</strong>, and claim it.
</div>"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "numberOfItems": len(events),
        "itemListElement": events,
    }
    return _page(
        f"karaoke in {real_city}, {st} — weekly nights and venues",
        f"every karaoke night in {real_city}, {st}. weekly schedules, venues, and hosts.",
        f"{BASE_URL}/karaoke/{st.lower()}/{city_slug}",
        body,
        jsonld,
    )
