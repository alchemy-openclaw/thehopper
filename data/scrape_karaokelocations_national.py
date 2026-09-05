#!/usr/bin/env python3
"""Scrape all venue pages from karaokelocations.com using its sitemap.

Every venue URL carries schema.org LocalBusiness JSON-LD with name, address,
phone, rating, and website. Output: data/karaokelocations_national.json
(+ per-run progress log). Polite: 0.5s delay, real UA, resumable via cache.
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "karaokelocations_national.json"
CACHE = BASE / "data" / ".karaokelocations_cache"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 KaraokeSpotResearch/1.0"
DELAY = 0.5

CACHE.mkdir(exist_ok=True)


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def get_sitemap_urls() -> list[str]:
    xml = fetch("https://karaokelocations.com/sitemap.xml")
    return re.findall(r"<loc>([^<]*?/venue/[^<]*?)</loc>", xml)


def parse_page(html: str) -> dict | None:
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    )
    for raw in blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            t = item.get("@type", "")
            if isinstance(t, str) and (
                "LocalBusiness" in t or "BarOrPub" in t or "FoodEstablishment" in t
            ):
                return item
    return None


def scrape(only_state: str | None = None, limit: int | None = None) -> list[dict]:
    urls = get_sitemap_urls()
    if only_state:
        urls = [u for u in urls if f"/state/{only_state}/" in u]
    if limit:
        urls = urls[:limit]
    print(f"{len(urls)} venue URLs to scrape", flush=True)

    results: list[dict] = []
    for i, url in enumerate(urls, 1):
        slug = url.rstrip("/").split("/")[-1]
        cache_file = CACHE / f"{slug}.json"
        if cache_file.exists():
            try:
                results.append(json.loads(cache_file.read_text()))
                continue
            except json.JSONDecodeError:
                pass
        try:
            html = fetch(url)
            item = parse_page(html)
            if item:
                addr = item.get("address", {}) or {}
                rec = {
                    "name": item.get("name"),
                    "street": addr.get("streetAddress"),
                    "city": addr.get("addressLocality"),
                    "state": addr.get("addressRegion"),
                    "zip": addr.get("postalCode"),
                    "phone": item.get("telephone"),
                    "website": item.get("url"),
                    "description": item.get("description"),
                    "rating": item.get("aggregateRating", {}).get("ratingValue")
                    if isinstance(item.get("aggregateRating"), dict)
                    else None,
                    "source_url": url,
                }
                cache_file.write_text(json.dumps(rec))
                results.append(rec)
        except Exception as e:
            print(f"  [{i}] ERR {url}: {e}", flush=True)
        if i % 100 == 0:
            print(f"  {i}/{len(urls)} (ok={len(results)})", flush=True)
        time.sleep(DELAY)

    return results


def main() -> None:
    only_state = None
    limit = None
    for arg in sys.argv[1:]:
        if arg.startswith("--state="):
            only_state = arg.split("=", 1)[1]
        elif arg.startswith("--limit="):
            limit = int(arg.split("=", 1)[1])
    results = scrape(only_state, limit)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1))
    states = {}
    for r in results:
        s = r.get("state") or "?"
        states[s] = states.get(s, 0) + 1
    print(f"saved {len(results)} venues -> {OUT}")
    print("top states:", sorted(states.items(), key=lambda kv: -kv[1])[:10])


if __name__ == "__main__":
    main()
