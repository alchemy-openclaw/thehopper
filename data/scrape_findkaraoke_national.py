#!/usr/bin/env python3
"""Scrape FindKaraoke.net nationally for karaoke show schedules.

Two phases, both resumable via cache dirs:
  A. fetch every city page from the sitemap, collect venue links
  B. fetch each venue detail page, parse name/address/phone/schedule

The FL-only scraper (scrape_findkaraoke.py) proved the parsing approach;
this version generalizes state handling beyond ", FL".

Output: data/findkaraoke_national.json
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "findkaraoke_national.json"
CITY_CACHE = BASE / "data" / ".fk_cities_cache"
VENUE_CACHE = BASE / "data" / ".fk_venues_cache"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 KaraokeSpotResearch/1.0"
DELAY = 0.4

CITY_CACHE.mkdir(exist_ok=True)
VENUE_CACHE.mkdir(exist_ok=True)

DAYS_MAP = {
    "mon": "Monday", "monday": "Monday",
    "tue": "Tuesday", "tues": "Tuesday", "tuesday": "Tuesday",
    "wed": "Wednesday", "wednesday": "Wednesday",
    "thu": "Thursday", "thur": "Thursday", "thurs": "Thursday", "thursday": "Thursday",
    "fri": "Friday", "friday": "Friday",
    "sat": "Saturday", "saturday": "Saturday",
    "sun": "Sunday", "sunday": "Sunday",
}
DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# --- schedule parsing (from the proven FL scraper, state-agnostic) ----------

def normalize_time(t: str) -> str:
    if not t:
        return ""
    t = t.strip()
    if re.search(r"[AP]M", t, re.I):
        t = re.sub(r"(\d)([AP])", r"\1 \2", t, flags=re.I)
        m = re.match(r"(\d{1,2}):?(\d{0,2})\s*([AP]M)", t, re.I)
        if m:
            hour = int(m.group(1))
            minute = m.group(2) if m.group(2) else "00"
            return f"{hour:02d}:{minute} {m.group(3).upper()}"
        return t.upper()
    if ":" in t:
        hour = int(t.split(":")[0])
        return f"{hour:02d}:{t.split(':')[1].split()[0]} PM"
    if t.isdigit():
        hour = int(t)
        return f"{hour:02d}:00 PM"
    return t


def parse_schedule(text: str) -> list[dict]:
    time_re = r"\d{1,2}[:\.]?\d{0,2}\s*[APap][Mm]"
    schedule: list[dict] = []
    patterns = [
        rf"((?:Mon|Tues?|Wed(?:nes)?|Thurs?|Fri|Sat(?:ur)?|Sun)(?:day)?s?)\s*[\u2013\u2014-]\s*((?:Mon|Tues?|Wed(?:nes)?|Thurs?|Fri|Sat(?:ur)?|Sun)(?:day)?s?)\s+at\s+({time_re})",
        rf"Every\s*day\s+at\s+({time_re})",
        rf"((?:(?:Mon|Tues?|Wed(?:nes)?|Thurs?|Fri|Sat(?:ur)?|Sun)(?:day)?s?\s*,?\s*(?:and\s+)?)+)\s+at\s+({time_re})",
        rf"((?:Mon|Tues?|Wed(?:nes)?|Thurs?|Fri|Sat(?:ur)?|Sun)(?:day)?s?)\s+at\s+({time_re})",
    ]
    for i, pat in enumerate(patterns):
        m = re.search(pat, text, re.I)
        if not m:
            continue
        if i == 0:
            si = next((idx for idx, d in enumerate(DAY_ORDER) if d.startswith(m.group(1).lower()[:3])), None)
            ei = next((idx for idx, d in enumerate(DAY_ORDER) if d.startswith(m.group(2).lower()[:3])), None)
            if si is not None and ei is not None:
                days = DAY_ORDER[si:ei + 1] if si <= ei else DAY_ORDER[si:] + DAY_ORDER[:ei + 1]
                for d in days:
                    schedule.append({"day": DAYS_MAP[d], "start_time": normalize_time(m.group(3)), "end_time": ""})
        elif i == 1:
            for day in DAY_FULL:
                schedule.append({"day": day, "start_time": normalize_time(m.group(1)), "end_time": ""})
        elif i == 2:
            for dp in re.split(r",|\sand\s", m.group(1)):
                d = dp.strip().lower()[:3]
                if d in DAYS_MAP:
                    schedule.append({"day": DAYS_MAP[d], "start_time": normalize_time(m.group(2)), "end_time": ""})
        elif i == 3:
            d = m.group(1).lower()[:3]
            if d in DAYS_MAP:
                schedule.append({"day": DAYS_MAP[d], "start_time": normalize_time(m.group(2)), "end_time": ""})
        break
    seen: set[str] = set()
    return [s for s in schedule if not (s["day"] in seen or seen.add(s["day"]))]


# --- venue detail parsing (regex on text; no bs4 dependency) ----------------

def extract_venue_name(html: str, city_slug: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if not m:
        return ""
    text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    name = re.sub(r"^Karaoke\s+at\s*", "", text, flags=re.I)
    # strip trailing ", City, ST" or ", ST" — city title-cased from slug
    city_title = city_slug.replace("-", " ").title()
    name = re.sub(rf",\s*{re.escape(city_title)},?\s*[A-Z]{{2}}\s*$", "", name)
    name = re.sub(rf",\s*{re.escape(city_title)}\s*$", "", name)
    name = re.sub(r",\s*[A-Z]{2}\s*$", "", name)
    return name.strip()


def extract_address(html: str) -> str:
    # Google maps links first
    for m in re.finditer(r'href="([^"]*(?:maps\.google|maps\.app)[^"]*)"', html):
        href = urllib.parse.unquote(m.group(1))
        q = re.search(r"[?&]q=([^&]+)", href)
        if q and re.match(r"^\s*\d+\s", q.group(1)):
            return q.group(1).strip()
    text = re.sub(r"<[^>]+>", "\n", html)
    m = re.search(r"Address\s*\n+\s*(\d+\s+[^\n,]+(?:,[^\n]+)?)", text)
    if m:
        return m.group(1).strip()
    return ""


def extract_phone(html: str) -> str:
    text = re.sub(r"<[^>]+>", "\n", html)
    m = re.search(r"(\(\d{3}\)\s*\d{3}[-.]?\d{4})", text)
    return m.group(1) if m else ""


def extract_schedule_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    updated = re.search(r"Updated\s+\w+\s+\d+,\s+\d{4}", text)
    going = re.search(r"I'm Going", text)
    if updated and going:
        return text[updated.end():going.start()].strip()
    # fallback: after "at <City>, <ST>" header
    m = re.search(r",\s*[A-Z]{2}\s{2,}|,\s*[A-Z]{2}\s", text)
    if m and going:
        return text[m.end():going.start()].strip()
    return ""


# --- phases ------------------------------------------------------------------

def phase_a_cities() -> list[str]:
    """Fetch all city pages, return venue hrefs with city slugs."""
    xml = fetch("https://findkaraoke.net/sitemap.xml")
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    from urllib.parse import urlparse
    skip = ("blog/", "submissions/", "venue/")
    reserved = {"", "blog", "tonight", "stats", "cities", "private-karaoke-rooms",
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
    cities = []
    for u in locs:
        p = urlparse(u).path.strip("/")
        if p and not p.startswith(skip) and p not in reserved and "/venues/" not in p:
            cities.append(p)
    print(f"phase A: {len(cities)} city pages", flush=True)

    venue_links: dict[str, dict] = {}
    for i, city in enumerate(cities, 1):
        cf = CITY_CACHE / f"{city}.json"
        if cf.exists():
            links = json.loads(cf.read_text())
        else:
            links = []
            try:
                html = fetch(f"https://findkaraoke.net/{city}")
                for m in re.finditer(rf'href="/{re.escape(city)}/venues/([^"]+)"[^>]*>(.*?)</a>', html, re.S):
                    slug, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
                    key = f"{city}/venues/{slug}"
                    if label and key not in venue_links:
                        links.append({"key": key, "label": label, "city": city})
                        venue_links[key] = True
                cf.write_text(json.dumps(links))
            except Exception as e:
                cf.write_text(json.dumps([]))
                print(f"  [{i}] city ERR {city}: {e}", flush=True)
        for l in links:
            venue_links.setdefault(l["key"], True)
            if l["key"] not in [x for x in []]:
                pass
        if i % 500 == 0:
            print(f"  {i}/{len(cities)} cities, {len(venue_links)} venues so far", flush=True)
        time.sleep(DELAY)

    # reload all cached links (resumable runs)
    all_links: list[dict] = []
    seen: set[str] = set()
    for cf in sorted(CITY_CACHE.glob("*.json")):
        try:
            for l in json.loads(cf.read_text()):
                if l["key"] not in seen:
                    seen.add(l["key"])
                    all_links.append(l)
        except Exception:
            pass
    print(f"phase A done: {len(all_links)} unique venue links", flush=True)
    return all_links


def phase_b_venues(all_links: list[dict]) -> list[dict]:
    results: list[dict] = []
    for i, link in enumerate(all_links, 1):
        vf = VENUE_CACHE / (link["key"].replace("/", "_") + ".json")
        if vf.exists():
            try:
                results.append(json.loads(vf.read_text()))
                continue
            except Exception:
                pass
        rec = {**link, "name": "", "address": "", "phone": "", "schedule": [], "about": "", "source": "findkaraoke.net"}
        try:
            html = fetch(f"https://findkaraoke.net/{link['key']}")
            rec["name"] = extract_venue_name(html, link["city"]) or link["label"]
            rec["address"] = extract_address(html)
            rec["phone"] = extract_phone(html)
            rec["schedule"] = parse_schedule(extract_schedule_text(html))
            vf.write_text(json.dumps(rec))
        except Exception as e:
            vf.write_text(json.dumps(rec))
            print(f"  [{i}] venue ERR {link['key']}: {e}", flush=True)
        if i % 250 == 0:
            print(f"  {i}/{len(all_links)} venues (done={len(results)})", flush=True)
        time.sleep(DELAY)
        results.append(rec)
    return results


def main() -> None:
    only_phase_a = "--cities" in sys.argv
    all_links = phase_a_cities()
    if only_phase_a:
        return
    results = phase_b_venues(all_links)
    with_sched = [r for r in results if r["schedule"]]
    OUT.write_text(json.dumps(results, indent=1))
    print(f"saved {len(results)} venues ({len(with_sched)} with schedules) -> {OUT}")


if __name__ == "__main__":
    main()
