"""TheHopper — Karaoke companion app backend.

FastAPI app providing:
  - Venues (Brevard County, FL) sorted by geolocation
  - Songs catalog (50+ karaoke songs with range/difficulty metadata)
  - Song suggestions matching user vocal range + favorite artists/genres
  - KJ messaging (singers can leave a message for the karaoke host)
  - Stripe Checkout for reserving a "premium slot" (preferred singing time
    set by the KJ — a community-focused support mechanism, not a queue jump)
  - Per-venue chat room with WebSocket real-time push

Run with: uvicorn main:app --reload
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import secrets
import smtplib
import sqlite3
import string
import time
from contextlib import contextmanager
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request as UrllibRequest, urlopen

import stripe
from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from seed_data import SONGS, VENUES
from stripe_connect import ConnectManager, ConnectAccount
from kj_site_light import _kj_site_html_light

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "thehopper.db"
# Frontend build output is served by FastAPI in production; in dev the Vite
# dev server (port 5173) proxies /api to this server.
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

# Stripe test keys. The publishable key is safe to expose; the secret key
# MUST come from the environment. A placeholder default lets the app boot
# in a "no-payments" mode so devs can try everything without a Stripe account.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "sk_test_PLACEHOLDER_SET_ME")
STRIPE_PUBLISHABLE_KEY = os.environ.get(
    "STRIPE_PUBLISHABLE_KEY", "pk_test_PLACEHOLDER_SET_ME"
)
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# Stripe requires absolute success/cancel URLs on Checkout Sessions — a relative
# path is rejected with an InvalidRequestError, so this must be set correctly
# before live keys are used.
PUBLIC_APP_URL = os.environ.get(
    "PUBLIC_APP_URL", "https://thehopper.alchemycreativelounge.com"
).rstrip("/")

stripe.api_key = STRIPE_SECRET_KEY

# KJ business site domain — slug.karaokespot.us serves auto-generated pages
KARAOKESPOT_DOMAIN = "karaokespot.us"

# True when we are pointed at Stripe's live environment (real money).
STRIPE_LIVE_MODE = STRIPE_SECRET_KEY.startswith("sk_live_")

# Stripe Connect manager for marketplace payments (Express accounts)
connect = ConnectManager()

# ---------------------------------------------------------------------------
# Twilio SMS configuration (for phone verification + KJ notifications)
# ---------------------------------------------------------------------------

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
TWILIO_BASE_URL = "https://api.twilio.com/2010-04-01"

# Expo push notification server URL
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# Public endpoint URL the frontend hits. In local dev the Vite proxy handles
# this; in production the FastAPI server serves the built frontend.
API_PREFIX = "/api"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables and seed them if empty."""
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS venues (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                address         TEXT NOT NULL,
                city            TEXT NOT NULL,
                lat             REAL NOT NULL,
                lng             REAL NOT NULL,
                karaoke_nights  TEXT NOT NULL,   -- comma-separated day names
                start_time      TEXT NOT NULL,
                end_time        TEXT NOT NULL,
                kj_name         TEXT,
                phone           TEXT,
                website         TEXT,
                price_jump_queue REAL NOT NULL DEFAULT 5.0,
                vibe            TEXT
            );

            CREATE TABLE IF NOT EXISTS songs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                artist      TEXT NOT NULL,
                genre       TEXT NOT NULL,
                year        INTEGER,
                difficulty  INTEGER NOT NULL,    -- 1..5
                range_fit   TEXT NOT NULL,        -- comma-separated ranges
                notes       TEXT
            );

            CREATE TABLE IF NOT EXISTS payments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                stripe_session_id  TEXT,
                venue_id        INTEGER NOT NULL,
                amount_usd      REAL NOT NULL,
                singer_name     TEXT,
                song_request    TEXT,
                status          TEXT NOT NULL DEFAULT 'open',  -- open|paid|expired|failed
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                paid_at         TEXT,
                FOREIGN KEY (venue_id) REFERENCES venues(id)
            );

            CREATE TABLE IF NOT EXISTS kj_messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_id        INTEGER NOT NULL,
                singer_name     TEXT NOT NULL,
                message         TEXT NOT NULL,
                song_request    TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (venue_id) REFERENCES venues(id)
            );

            CREATE TABLE IF NOT EXISTS venue_chat (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_id        INTEGER NOT NULL,
                nickname        TEXT NOT NULL,
                message         TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (venue_id) REFERENCES venues(id)
            );
            CREATE INDEX IF NOT EXISTS idx_venue_chat_venue ON venue_chat(venue_id, id);

            CREATE TABLE IF NOT EXISTS kjs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                phone           TEXT NOT NULL UNIQUE,
                bio             TEXT,
                photo_url       TEXT,
                instagram       TEXT,
                website         TEXT,
                stripe_account_id   TEXT,
                stripe_onboarding_status TEXT NOT NULL DEFAULT 'none',
                verified        INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS venue_submissions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                address         TEXT NOT NULL,
                city            TEXT NOT NULL,
                lat             REAL,
                lng             REAL,
                karaoke_nights  TEXT NOT NULL,
                start_time      TEXT NOT NULL,
                end_time        TEXT NOT NULL,
                kj_name         TEXT,
                phone           TEXT,
                website         TEXT,
                instagram       TEXT,
                vibe            TEXT,
                is_kj           INTEGER NOT NULL DEFAULT 0,
                kj_id           INTEGER,
                submitter_phone TEXT,
                status          TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                reviewed_at     TEXT,
                venue_id        INTEGER,  -- set when approved → venue created
                FOREIGN KEY (kj_id) REFERENCES kjs(id)
            );

            CREATE TABLE IF NOT EXISTS phone_verifications (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL,
                code            TEXT NOT NULL,
                verified        INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at      TEXT NOT NULL
            );

            -- Session tokens minted by /phone/verify. Until this table existed
            -- the token was generated, returned, and immediately forgotten, so
            -- nothing could act on it. Possession of a row here is the proof
            -- that a caller controls `phone`.
            CREATE TABLE IF NOT EXISTS phone_sessions (
                token           TEXT PRIMARY KEY,
                phone           TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS devices (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT,
                kj_id           INTEGER,
                push_token      TEXT NOT NULL,
                platform         TEXT,
                venue_id        INTEGER,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (kj_id) REFERENCES kjs(id)
            );
            """
        )

        # ------------------------------------------------------------------
        # Migrations: Stripe Connect — track connected accounts per venue
        # ------------------------------------------------------------------
        vcols = {row["name"] for row in conn.execute("PRAGMA table_info(venues)")}
        if "stripe_account_id" not in vcols:
            conn.execute(
                "ALTER TABLE venues ADD COLUMN stripe_account_id TEXT"
            )
        if "stripe_onboarding_status" not in vcols:
            conn.execute(
                "ALTER TABLE venues ADD COLUMN stripe_onboarding_status "
                "TEXT NOT NULL DEFAULT 'none'"
            )

        # ------------------------------------------------------------------
        # Migrations: add premium-slot columns to venues if missing.
        # `premium_slot_position` (INTEGER, default 3) — where in the rotation
        #   the KJ places premium-slot singers. 3rd position by default, NOT
        #   "next", so it stays a respectful reservation rather than a queue
        #   jump.
        # `premium_slot_price` (REAL, default 5.0) — the support amount for a
        #   premium slot. Reuses `price_jump_queue` as the seed value when the
        #   column is first added so KJ-configured prices carry over.
        # ------------------------------------------------------------------
        vcols = {row["name"] for row in conn.execute("PRAGMA table_info(venues)")}
        if "premium_slot_position" not in vcols:
            conn.execute(
                "ALTER TABLE venues ADD COLUMN premium_slot_position INTEGER NOT NULL DEFAULT 3"
            )
        if "premium_slot_price" not in vcols:
            conn.execute(
                "ALTER TABLE venues ADD COLUMN premium_slot_price REAL NOT NULL DEFAULT 5.0"
            )
            # Backfill from the legacy price_jump_queue column so existing KJ
            # pricing carries over to the renamed concept.
            conn.execute(
                "UPDATE venues SET premium_slot_price = price_jump_queue "
                "WHERE premium_slot_price = 5.0 AND price_jump_queue != 5.0"
            )

        # ------------------------------------------------------------------
        # Migrations: KJ-configurable products (premium slot variants)
        # ------------------------------------------------------------------
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kj_products (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                venue_id        INTEGER NOT NULL,
                stripe_product_id  TEXT,
                stripe_price_id    TEXT,
                name            TEXT NOT NULL,
                description     TEXT DEFAULT '',
                amount_cents    INTEGER NOT NULL,
                active          INTEGER NOT NULL DEFAULT 1,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (venue_id) REFERENCES venues(id)
            );
            CREATE INDEX IF NOT EXISTS idx_kj_products_venue ON kj_products(venue_id, active);
            """
        )

        # ------------------------------------------------------------------
        # ------------------------------------------------------------------
        # Migration: add site_slug + business_name to kjs for auto-generated
        # static websites (Stripe requires a business_profile.url).
        # ------------------------------------------------------------------
        kj_cols = {row["name"] for row in conn.execute("PRAGMA table_info(kjs)")}
        if "site_slug" not in kj_cols:
            conn.execute("ALTER TABLE kjs ADD COLUMN site_slug TEXT")
        if "business_name" not in kj_cols:
            conn.execute("ALTER TABLE kjs ADD COLUMN business_name TEXT")
        if "city" not in kj_cols:
            conn.execute("ALTER TABLE kjs ADD COLUMN city TEXT")

        # Migration: add kj_id column to venues (links venue → KJ record)
        # ------------------------------------------------------------------
        vcols = {row["name"] for row in conn.execute("PRAGMA table_info(venues)")}
        if "kj_id" not in vcols:
            conn.execute("ALTER TABLE venues ADD COLUMN kj_id INTEGER REFERENCES kjs(id)")

        # Seed venues if empty
        cur = conn.execute("SELECT COUNT(*) as c FROM venues")
        if cur.fetchone()["c"] == 0:
            for v in VENUES:
                conn.execute(
                    """INSERT INTO venues
                       (name, address, city, lat, lng, karaoke_nights, start_time,
                        end_time, kj_name, phone, website, price_jump_queue,
                        premium_slot_position, premium_slot_price, vibe)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        v["name"], v["address"], v["city"], v["lat"], v["lng"],
                        ",".join(v["karaoke_nights"]), v["start_time"], v["end_time"],
                        v["kj_name"], v["phone"], v["website"],
                        v["price_jump_queue"],
                        v.get("premium_slot_position", 3),
                        v.get("premium_slot_price", v["price_jump_queue"]),
                        v["vibe"],
                    ),
                )

        # Seed songs if empty — de-duplicate by (title, artist)
        cur = conn.execute("SELECT COUNT(*) as c FROM songs")
        if cur.fetchone()["c"] == 0:
            seen: set[tuple[str, str]] = set()
            for s in SONGS:
                key = (s["title"].strip().lower(), s["artist"].strip().lower())
                if key in seen:
                    continue
                seen.add(key)
                conn.execute(
                    """INSERT INTO songs
                       (title, artist, genre, year, difficulty, range_fit, notes)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        s["title"], s["artist"], s["genre"], s["year"],
                        s["difficulty"], ",".join(s["range_fit"]), s.get("notes", ""),
                    ),
                )

        # Migration: add paid_at column if missing (defensive for older DBs)
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(payments)")}
        if "paid_at" not in cols:
            conn.execute("ALTER TABLE payments ADD COLUMN paid_at TEXT")

        # kj_messages table is created by the executescript above (IF NOT EXISTS),
        # but older DBs that predate it need the table added here too.
        tables = {
            row["name"] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "kj_messages" not in tables:
            conn.execute(
                """
                CREATE TABLE kj_messages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    venue_id        INTEGER NOT NULL,
                    singer_name     TEXT NOT NULL,
                    message         TEXT NOT NULL,
                    song_request    TEXT,
                    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (venue_id) REFERENCES venues(id)
                )
                """
            )

        # Migration: add singer_phone to kj_messages
        kj_msg_cols = {row["name"] for row in conn.execute("PRAGMA table_info(kj_messages)")}
        if "singer_phone" not in kj_msg_cols:
            conn.execute("ALTER TABLE kj_messages ADD COLUMN singer_phone TEXT")

        # Migration: add song_request_required to kjs (KJ preference)
        kj_cols = {row["name"] for row in conn.execute("PRAGMA table_info(kjs)")}
        if "song_request_required" not in kj_cols:
            conn.execute(
                "ALTER TABLE kjs ADD COLUMN song_request_required INTEGER NOT NULL DEFAULT 0"
            )

        # Patrons table — tiny profiles so KJs can reply
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS patrons (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                phone           TEXT NOT NULL UNIQUE,
                name            TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_patrons_phone ON patrons(phone);
            """
        )


# ---------------------------------------------------------------------------
# Geolocation helpers
# ---------------------------------------------------------------------------


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles between two lat/lng points."""
    R = 3958.756  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def _normalize_venue_name(name: str) -> str:
    """Normalize a venue name for fuzzy matching.

    Lowercase, strip common suffixes (the, bar, grill, etc.),
    collapse whitespace and punctuation.
    """
    import re
    n = name.lower().strip()
    # Remove common business suffixes
    for suffix in [" the ", " bar ", " grill ", " pub ", " lounge ",
                   " restaurant ", " & grill", " bar and grill",
                   " sports bar", " tavern", " taproom"]:
        n = n.replace(suffix, " ")
    # Remove punctuation
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    # Collapse whitespace
    n = re.sub(r"\s+", " ", n).strip()
    # Remove "the" prefix
    if n.startswith("the "):
        n = n[4:]
    return n


def _check_duplicate_venue(
    conn: sqlite3.Connection,
    name: str,
    address: str,
    city: str,
    lat: float | None = None,
    lng: float | None = None,
) -> dict | None:
    """Check if a venue already exists (fuzzy match by name + location).

    Returns the existing venue dict if a duplicate is found, None otherwise.
    Uses name similarity + geographic proximity (within ~500ft / 0.1 miles)
    or exact address match.
    """
    norm_name = _normalize_venue_name(name)
    if not norm_name:
        return None

    # Check existing venues
    venues = conn.execute("SELECT * FROM venues").fetchall()
    for v in venues:
        existing_norm = _normalize_venue_name(v["name"])
        # Exact normalized name match
        if existing_norm == norm_name:
            # Same city or same address
            if (city and v["city"].lower() == city.lower()) or \
               (address and address.lower().strip() in v["address"].lower()):
                return venue_row_to_dict(v)

        # Geographic proximity check (within ~500ft)
        if lat is not None and lng is not None and v["lat"] and v["lng"]:
            dist = haversine_miles(lat, lng, v["lat"], v["lng"])
            if dist < 0.1:  # within ~0.1 miles (~528ft)
                # Name similarity — check if one name contains the other
                if norm_name in existing_norm or existing_norm in norm_name:
                    return venue_row_to_dict(v)

    # Also check pending submissions to flag duplicates early
    pending = conn.execute(
        "SELECT * FROM venue_submissions WHERE status='pending'"
    ).fetchall()
    for p in pending:
        existing_norm = _normalize_venue_name(p["name"])
        if existing_norm == norm_name:
            if (city and p["city"].lower() == city.lower()) or \
               (address and address.lower().strip() in p["address"].lower()):
                return {
                    "id": p["id"],
                    "name": p["name"],
                    "address": p["address"],
                    "city": p["city"],
                    "is_pending": True,
                }

    return None


# ---------------------------------------------------------------------------
# SMS helper (Twilio REST API — no SDK needed)
# ---------------------------------------------------------------------------


def send_sms(to: str, body: str) -> bool:
    """Send an SMS via Twilio REST API. Returns True on success."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        # Dev mode: just log it
        print(f"[SMS] (no Twilio configured) To: {to} | Body: {body}")
        return True
    try:
        url = f"{TWILIO_BASE_URL}/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        data = urlencode({"From": TWILIO_FROM_NUMBER, "To": to, "Body": body}).encode()
        req = UrllibRequest(url, data=data, method="POST")
        import base64
        creds = base64.b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
        with urlopen(req, timeout=10) as resp:
            return resp.status == 201
    except Exception as e:
        print(f"[SMS] Error sending to {to}: {e}")
        return False


# ---------------------------------------------------------------------------
# Push notification helper (Expo Push API)
# ---------------------------------------------------------------------------


def send_push(tokens: list[str], title: str, body: str, data: dict | None = None) -> None:
    """Send a push notification to one or more Expo push tokens."""
    if not tokens:
        return
    messages = []
    for token in tokens:
        msg = {"to": token, "title": title, "body": body, "sound": "default"}
        if data:
            msg["data"] = data
        messages.append(msg)
    try:
        payload = json.dumps(messages).encode()
        req = UrllibRequest(EXPO_PUSH_URL, data=payload, method="POST")
        req.add_header("Accept", "application/json")
        req.add_header("Content-Type", "application/json")
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                print(f"[Push] Expo returned {resp.status}")
    except Exception as e:
        print(f"[Push] Error: {e}")


def notify_kj_for_venue(conn: sqlite3.Connection, venue_id: int, title: str, body: str, data: dict | None = None) -> None:
    """Send push + SMS to the KJ associated with a venue."""
    venue = conn.execute("SELECT kj_id, kj_name, phone FROM venues WHERE id = ?", (venue_id,)).fetchone()
    if not venue:
        return
    kj_id = venue["kj_id"] if "kj_id" in venue.keys() else None
    # Push notification
    if kj_id:
        devices = conn.execute("SELECT push_token FROM devices WHERE kj_id = ?", (kj_id,)).fetchall()
        tokens = [d["push_token"] for d in devices]
        send_push(tokens, title, body, data)
    # SMS fallback
    phone = venue["phone"] if venue["phone"] else None
    if phone:
        send_sms(phone, f"{title}: {body}")


# ---------------------------------------------------------------------------
# Phone verification helpers
# ---------------------------------------------------------------------------


def normalize_phone(phone: str) -> str:
    """Normalize a phone number to E.164-ish format (US default)."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    if digits.startswith("1") and len(digits) > 11:
        return f"+{digits}"
    return f"+{digits}" if digits else phone


def generate_code() -> str:
    """Generate a 6-digit verification code."""
    return "".join(random.choices(string.digits, k=6))


# How long a token from /phone/verify stays usable. Long enough that a KJ who
# onboarded weeks ago can still edit their profile without re-verifying.
PHONE_SESSION_TTL_SECONDS = 30 * 24 * 3600


def phone_for_token(conn: sqlite3.Connection, token: str | None) -> str | None:
    """Return the phone a session token proves ownership of, or None.

    None covers every failure the caller should treat identically: no token,
    unknown token, or expired token.
    """
    if not token:
        return None
    row = conn.execute(
        "SELECT phone, expires_at FROM phone_sessions WHERE token=?", (token,)
    ).fetchone()
    if not row:
        return None
    try:
        if float(row["expires_at"]) < time.time():
            return None
    except (TypeError, ValueError):
        return None
    return row["phone"]


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    import re
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "kj"


def unique_slug(conn: sqlite3.Connection, base: str) -> str:
    """Find a unique site_slug not already in use."""
    base = slugify(base)
    slug = base
    suffix = 2
    while conn.execute(
        "SELECT id FROM kjs WHERE site_slug=?", (slug,)
    ).fetchone():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


# ---------------------------------------------------------------------------
# Song matching algorithm
# ---------------------------------------------------------------------------
#
# Vocal range "rank" on a 0..1 scale, used to bias difficulty scoring:
#   bass=0.0, baritone=0.2, tenor=0.4, alto=0.6, mezzo=0.8, soprano=1.0
# This is a heuristic — we don't have per-song exact ranges, just which ranges
# the song suits. The algorithm:
#   1. Strong base score if the user's range is in the song's range_fit list.
#   2. Difficulty preference: we want songs that are a *comfortable challenge*
#      — not trivial (difficulty 1) and not a guaranteed trainwreck (5).
#      Ideal difficulty ~ 2-3.
#   3. Boost songs by favorite artists (exact match) or genres (style match).
#   4. Normalize to 0..100 and sort descending.
# ---------------------------------------------------------------------------

RANGE_RANK = {
    "bass": 0.0,
    "baritone": 0.2,
    "tenor": 0.4,
    "alto": 0.6,
    "mezzo": 0.8,
    "soprano": 1.0,
}

VALID_RANGES = list(RANGE_RANK.keys())


def score_song(
    song: dict, user_range: str, fav_artists: list[str], fav_genres: list[str]
) -> float:
    """Return a 0..100 match score for a song given user inputs."""
    score = 0.0

    # --- 1. Range fit (the dominant factor: 60% weight) ---
    rf = song["range_fit"]
    if isinstance(rf, str):
        range_fit = [r.strip().lower() for r in rf.split(",") if r.strip()]
    elif isinstance(rf, list):
        range_fit = [r.strip().lower() for r in rf if r.strip()]
    else:
        range_fit = []
    if user_range in range_fit:
        # direct match: full 60
        score += 60.0
    elif user_range in RANGE_RANK and range_fit:
        # partial credit by proximity of range on the bass..soprano ladder
        user_rank = RANGE_RANK[user_range]
        closest = min(
            (RANGE_RANK[r] for r in range_fit if r in RANGE_RANK),
            key=lambda r: abs(r - user_rank),
            default=None,
        )
        if closest is not None:
            # within one ladder step gets partial credit
            distance = abs(closest - user_rank)
            score += max(0.0, 60.0 * (1 - distance / 0.4))  # 0 credit if >0.4 away

    # --- 2. Difficulty sweet spot (25% weight) ---
    diff = song["difficulty"]
    # ideal is 2 or 3; 1 is too easy (boring), 4 is challenging, 5 is risky
    diff_score = {1: 12, 2: 25, 3: 25, 4: 15, 5: 5}.get(diff, 10)
    score += diff_score

    # --- 3. Artist match (10% weight, exact substring) ---
    artist_lc = song["artist"].lower()
    if any(a and a.strip().lower() in artist_lc for a in fav_artists if a.strip()):
        score += 10.0

    # --- 4. Genre match (5% weight) ---
    genre_lc = song["genre"].lower()
    if any(g and g.strip().lower() in genre_lc for g in fav_genres if g.strip()):
        score += 5.0

    return round(min(100.0, score), 1)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class VenueOut(BaseModel):
    id: int
    name: str
    address: str
    city: str
    lat: float
    lng: float
    karaoke_nights: list[str]
    start_time: str
    end_time: str
    kj_name: str | None
    phone: str | None
    website: str | None
    price_jump_queue: float
    premium_slot_position: int = 3
    premium_slot_price: float = 5.0
    vibe: str | None
    distance_miles: float | None = None
    stripe_account_id: str | None = None
    stripe_onboarding_status: str = "none"


class SongOut(BaseModel):
    id: int
    title: str
    artist: str
    genre: str
    year: int | None
    difficulty: int
    range_fit: list[str]
    notes: str | None


class SuggestionRequest(BaseModel):
    vocal_range: str
    favorite_artists: list[str] = []
    favorite_genres: list[str] = []
    limit: int = 12


class SuggestionOut(BaseModel):
    song: SongOut
    score: float
    reason: str


class PaymentRequest(BaseModel):
    venue_id: int
    singer_name: str = "Anonymous Singer"
    song_request: str = ""
    # amount is server-derived from venue.premium_slot_price; client cannot set it


class PaymentResponse(BaseModel):
    checkout_url: str
    session_id: str


class KJMessageRequest(BaseModel):
    """A singer's message to a venue's KJ (karaoke host).

    Stored in the `kj_messages` table. If the KJ has a phone number and
    Twilio is configured, the message is forwarded via SMS.
    """
    singer_name: str = "Anonymous Singer"
    singer_phone: str = ""
    message: str
    song_request: str = ""


class KJMessageResponse(BaseModel):
    id: int
    venue_id: int
    singer_name: str
    singer_phone: str | None
    message: str
    song_request: str | None
    created_at: str


class ChatMessageRequest(BaseModel):
    nickname: str
    message: str


class ChatMessageResponse(BaseModel):
    id: int
    venue_id: int
    nickname: str
    message: str
    created_at: str


# --- New models for venue submission, KJ onboarding, phone verification, devices ---

class VenueSubmissionRequest(BaseModel):
    """User-submitted new karaoke spot."""
    name: str
    address: str
    city: str
    karaoke_nights: list[str] = []
    start_time: str = "20:00"
    end_time: str = "00:00"
    kj_name: str | None = None
    phone: str | None = None
    website: str | None = None
    instagram: str | None = None
    vibe: str | None = None
    is_kj: bool = False
    submitter_phone: str | None = None  # for verification + notifications


class VenueSubmissionResponse(BaseModel):
    id: int
    status: str
    message: str


class PhoneSendCodeRequest(BaseModel):
    phone: str


class PhoneVerifyRequest(BaseModel):
    phone: str
    code: str


class PhoneVerifyResponse(BaseModel):
    verified: bool
    token: str | None = None  # session token for subsequent requests


class KJRegisterRequest(BaseModel):
    """Register or update a KJ profile."""
    name: str
    phone: str  # must be verified first
    bio: str | None = None
    instagram: str | None = None
    website: str | None = None
    photo_url: str | None = None
    business_name: str | None = None  # operating name for Stripe (defaults to name)
    city: str | None = None  # home city for "Centered in" on KJ site


class KJOut(BaseModel):
    id: int
    name: str
    phone: str
    bio: str | None
    photo_url: str | None
    instagram: str | None
    website: str | None
    stripe_onboarding_status: str = "none"
    verified: bool = False
    created_at: str
    business_name: str | None = None
    site_slug: str | None = None
    city: str | None = None
    song_request_required: bool = False


class KJProfileUpdateRequest(BaseModel):
    """Edit a KJ's stage name and/or phone number.

    Changing `phone` re-keys the account, so it additionally requires
    `new_phone_token` — a token from /phone/verify for the *new* number.
    """
    name: str | None = None
    phone: str | None = None
    new_phone_token: str | None = None


class KJLinkVenueRequest(BaseModel):
    """Link a KJ to a venue (claim ownership)."""
    kj_id: int
    venue_id: int


class PatronProfileRequest(BaseModel):
    """Create or update a patron's tiny profile."""
    name: str = ""
    phone: str = ""


class PatronProfileResponse(BaseModel):
    id: int
    name: str | None
    phone: str


class DeviceRegisterRequest(BaseModel):
    push_token: str
    platform: str = ""
    phone: str = ""
    kj_id: int | None = None
    venue_id: int | None = None


# ---------------------------------------------------------------------------
# Row -> dict helpers
# ---------------------------------------------------------------------------


def venue_row_to_dict(row: sqlite3.Row, distance: float | None = None, kj_song_required: bool = False) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "address": row["address"],
        "city": row["city"],
        "lat": row["lat"],
        "lng": row["lng"],
        "karaoke_nights": [n for n in row["karaoke_nights"].split(",") if n],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "kj_name": row["kj_name"],
        "phone": row["phone"],
        "website": row["website"],
        "price_jump_queue": row["price_jump_queue"],
        "premium_slot_position": row["premium_slot_position"],
        "premium_slot_price": row["premium_slot_price"],
        "vibe": row["vibe"],
        "distance_miles": round(distance, 1) if distance is not None else None,
        "stripe_account_id": row["stripe_account_id"] if "stripe_account_id" in row.keys() else None,
        "stripe_onboarding_status": row["stripe_onboarding_status"] if "stripe_onboarding_status" in row.keys() else "none",
        "song_request_required": kj_song_required,
    }


def song_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "artist": row["artist"],
        "genre": row["genre"],
        "year": row["year"],
        "difficulty": row["difficulty"],
        "range_fit": [r for r in row["range_fit"].split(",") if r],
        "notes": row["notes"],
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="TheHopper", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://thehopper.alchemycreativelounge.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# WebSocket connection manager (per-venue chat rooms)
# ---------------------------------------------------------------------------


class VenueConnectionManager:
    """Manages WebSocket connections grouped by venue_id."""

    def __init__(self) -> None:
        # venue_id -> set of WebSocket connections
        self._rooms: dict[int, set[WebSocket]] = {}

    def join(self, venue_id: int, ws: WebSocket) -> None:
        if venue_id not in self._rooms:
            self._rooms[venue_id] = set()
        self._rooms[venue_id].add(ws)

    def leave(self, venue_id: int, ws: WebSocket) -> None:
        room = self._rooms.get(venue_id)
        if room:
            room.discard(ws)
            if not room:
                del self._rooms[venue_id]

    async def broadcast(self, venue_id: int, message: dict) -> None:
        """Send a JSON message to all connections in a venue room."""
        room = self._rooms.get(venue_id)
        if not room:
            return
        text = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in room:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.leave(venue_id, ws)


chat_manager = VenueConnectionManager()


def _check_live_mode_config() -> None:
    """Refuse to serve live traffic with a half-migrated Stripe config.

    Every item here silently produces a broken or wrong charge at runtime
    rather than an obvious error, so we fail at boot instead.
    """
    if not STRIPE_LIVE_MODE:
        return

    problems: list[str] = []

    if not STRIPE_PUBLISHABLE_KEY.startswith("pk_live_"):
        problems.append(
            "STRIPE_PUBLISHABLE_KEY is not a live key (expected pk_live_…)"
        )
    if not STRIPE_WEBHOOK_SECRET:
        problems.append(
            "STRIPE_WEBHOOK_SECRET is unset — webhook payloads would be accepted "
            "unverified, so anyone could mark a payment as paid"
        )
    if not PUBLIC_APP_URL.startswith("https://"):
        problems.append(
            f"PUBLIC_APP_URL must be an absolute https URL for Stripe Checkout "
            f"redirects (got {PUBLIC_APP_URL!r})"
        )

    # Test-mode connected accounts do not exist in live mode; a destination
    # charge against one fails after the customer has already entered a card.
    with db() as conn:
        stale = sum(
            conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} "
                "WHERE stripe_account_id IS NOT NULL AND stripe_account_id != ''"
            ).fetchone()["n"]
            for table in ("venues", "kjs")
        )
    if stale:
        problems.append(
            f"{stale} venue/KJ row(s) still carry Stripe Connect accounts created in "
            "test mode — clear stripe_account_id and stripe_onboarding_status, then "
            "re-onboard those KJs against live mode"
        )

    if problems:
        raise RuntimeError(
            "Stripe live mode is enabled but the configuration is incomplete:\n  - "
            + "\n  - ".join(problems)
        )


@app.on_event("startup")
def _startup() -> None:
    init_db()
    _check_live_mode_config()


# ---------------------------------------------------------------------------
# API: health
# ---------------------------------------------------------------------------


@app.get(f"{API_PREFIX}/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "TheHopper", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# API: config (publishable key for frontend)
# ---------------------------------------------------------------------------


@app.get(f"{API_PREFIX}/config")
def config() -> dict[str, Any]:
    return {
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY,
        "stripe_configured": STRIPE_SECRET_KEY and not STRIPE_SECRET_KEY.startswith("sk_tes"),
    }


# ---------------------------------------------------------------------------
# API: venues
# ---------------------------------------------------------------------------


@app.get(f"{API_PREFIX}/venues", response_model=list[VenueOut])
def list_venues(
    lat: float | None = Query(None, description="User latitude"),
    lng: float | None = Query(None, description="User longitude"),
    city: str | None = Query(None, description="Filter by city name"),
):
    """List karaoke venues, optionally sorted by distance from (lat,lng)."""
    with db() as conn:
        rows = conn.execute("SELECT * FROM venues").fetchall()
        # Build a map of kj_id -> song_request_required for all KJs
        kj_req_map: dict[int, bool] = {}
        kj_rows = conn.execute("SELECT id, song_request_required FROM kjs").fetchall()
        for kj in kj_rows:
            kj_req_map[kj["id"]] = bool(kj["song_request_required"])

    out = []
    for r in rows:
        if city and city.lower() not in r["city"].lower():
            continue
        dist = None
        if lat is not None and lng is not None:
            dist = haversine_miles(lat, lng, r["lat"], r["lng"])
        kj_id = r["kj_id"] if "kj_id" in r.keys() else None
        song_required = kj_req_map.get(kj_id, False) if kj_id else False
        out.append(venue_row_to_dict(r, dist, song_required))

    if lat is not None and lng is not None:
        out.sort(key=lambda v: (v["distance_miles"] is None, v["distance_miles"]))

    return out


@app.get(f"{API_PREFIX}/venues/submissions")
def list_submissions(status: str | None = Query(None, description="Filter by status")):
    """List venue submissions (for admin/moderation)."""
    with db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM venue_submissions WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM venue_submissions ORDER BY created_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


@app.get(f"{API_PREFIX}/venues/{{venue_id}}", response_model=VenueOut)
def get_venue(venue_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM venues WHERE id = ?", (venue_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Venue not found")
    return venue_row_to_dict(row)


@app.post(
    f"{API_PREFIX}/venues/{{venue_id}}/message",
    response_model=KJMessageResponse,
)
def send_kj_message(venue_id: int, req: KJMessageRequest):
    """Store a message from a singer to a venue's KJ (karaoke host).

    If the KJ has a phone number and Twilio is configured, the message is
    forwarded via SMS so the KJ can respond directly to the patron.
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    singer_name = (req.singer_name or "Anonymous Singer").strip()[:120]
    singer_phone = req.singer_phone.strip() if req.singer_phone else ""
    normalized_phone = normalize_phone(singer_phone) if singer_phone else ""

    with db() as conn:
        venue = conn.execute(
            "SELECT * FROM venues WHERE id = ?", (venue_id,)
        ).fetchone()
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")

        # Look up the KJ's phone (prefer KJ phone over venue phone)
        kj_id = venue["kj_id"] if "kj_id" in venue.keys() else None
        kj_phone = ""
        if kj_id:
            kj_row = conn.execute(
                "SELECT phone FROM kjs WHERE id = ?", (kj_id,)
            ).fetchone()
            if kj_row and kj_row["phone"]:
                kj_phone = kj_row["phone"]

        # Upsert patron profile if phone provided
        if normalized_phone:
            conn.execute(
                """INSERT INTO patrons (phone, name) VALUES (?, ?)
                   ON CONFLICT(phone) DO UPDATE SET name=excluded.name""",
                (normalized_phone, singer_name),
            )

        cur = conn.execute(
            """INSERT INTO kj_messages
               (venue_id, singer_name, singer_phone, message, song_request)
               VALUES (?,?,?,?,?)""",
            (
                venue_id,
                singer_name,
                normalized_phone or None,
                req.message.strip()[:2000],
                (req.song_request or "").strip()[:200] or None,
            ),
        )
        msg_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM kj_messages WHERE id = ?", (msg_id,)
        ).fetchone()

        # Forward via SMS to KJ if Twilio is configured and KJ has a phone
        if kj_phone and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER:
            kj_name = venue["kj_name"] or "the KJ"
            song_part = f" (song: {req.song_request})" if req.song_request else ""
            reply_part = f" Reply: {normalized_phone}" if normalized_phone else ""
            msg_text = req.message.strip()[:500]
            sms_body = (
                f"New message from {singer_name} at {venue['name']}{song_part}:\n"
                f"{msg_text}{reply_part}"
            )
            send_sms(normalize_phone(kj_phone), sms_body)

    return KJMessageResponse(
        id=row["id"],
        venue_id=row["venue_id"],
        singer_name=row["singer_name"],
        singer_phone=row["singer_phone"],
        message=row["message"],
        song_request=row["song_request"],
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# API: venue chat
# ---------------------------------------------------------------------------


@app.get(
    f"{API_PREFIX}/venues/{{venue_id}}/chat",
    response_model=list[ChatMessageResponse],
)
def get_venue_chat(
    venue_id: int,
    since: int | None = Query(
        None, description="Only return messages with id > since (for polling)"
    ),
    limit: int = Query(100, ge=1, le=500),
):
    """Return recent chat messages for a venue, oldest first."""
    with db() as conn:
        venue = conn.execute(
            "SELECT id FROM venues WHERE id = ?", (venue_id,)
        ).fetchone()
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")

        if since is not None:
            rows = conn.execute(
                "SELECT * FROM venue_chat WHERE venue_id = ? AND id > ? "
                "ORDER BY id ASC LIMIT ?",
                (venue_id, since, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM venue_chat WHERE venue_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (venue_id, limit),
            ).fetchall()
            rows = list(reversed(rows))  # oldest first

    return [
        ChatMessageResponse(
            id=r["id"],
            venue_id=r["venue_id"],
            nickname=r["nickname"],
            message=r["message"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@app.post(
    f"{API_PREFIX}/venues/{{venue_id}}/chat",
    response_model=ChatMessageResponse,
)
async def post_venue_chat(venue_id: int, req: ChatMessageRequest):
    """Post a message to a venue's chat room and broadcast via WebSocket."""
    nick = req.nickname.strip()
    if not nick:
        raise HTTPException(status_code=400, detail="Nickname is required")
    if len(nick) > 60:
        nick = nick[:60]
    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(msg) > 500:
        msg = msg[:500]

    with db() as conn:
        venue = conn.execute(
            "SELECT id FROM venues WHERE id = ?", (venue_id,)
        ).fetchone()
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")

        cur = conn.execute(
            "INSERT INTO venue_chat (venue_id, nickname, message) VALUES (?,?,?)",
            (venue_id, nick, msg),
        )
        msg_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM venue_chat WHERE id = ?", (msg_id,)
        ).fetchone()

    response = ChatMessageResponse(
        id=row["id"],
        venue_id=row["venue_id"],
        nickname=row["nickname"],
        message=row["message"],
        created_at=row["created_at"],
    )

    # Broadcast to all WebSocket listeners in this venue room
    await chat_manager.broadcast(venue_id, response.model_dump())

    return response


@app.websocket(f"{API_PREFIX}/venues/{{venue_id}}/ws")
async def venue_chat_ws(venue_id: int, ws: WebSocket):
    """WebSocket endpoint for real-time venue chat.

    Clients connect to receive live messages. They can also send messages
    over the socket (preferred) — the server persists and broadcasts them.
    """
    # Verify venue exists before accepting
    with db() as conn:
        venue = conn.execute(
            "SELECT id FROM venues WHERE id = ?", (venue_id,)
        ).fetchone()
    if not venue:
        await ws.close(code=4004)
        return

    await ws.accept()
    chat_manager.join(venue_id, ws)
    try:
        while True:
            data = await ws.receive_text()
            try:
                payload = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                await ws.send_text(json.dumps({
                    "type": "error",
                    "detail": "Invalid JSON",
                }))
                continue

            nick = str(payload.get("nickname", "")).strip()
            msg = str(payload.get("message", "")).strip()
            if not nick:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "detail": "Nickname is required",
                }))
                continue
            if not msg:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "detail": "Message cannot be empty",
                }))
                continue
            if len(nick) > 60:
                nick = nick[:60]
            if len(msg) > 500:
                msg = msg[:500]

            with db() as conn:
                cur = conn.execute(
                    "INSERT INTO venue_chat (venue_id, nickname, message) "
                    "VALUES (?,?,?)",
                    (venue_id, nick, msg),
                )
                msg_id = cur.lastrowid
                row = conn.execute(
                    "SELECT * FROM venue_chat WHERE id = ?", (msg_id,)
                ).fetchone()

            response = ChatMessageResponse(
                id=row["id"],
                venue_id=row["venue_id"],
                nickname=row["nickname"],
                message=row["message"],
                created_at=row["created_at"],
            )

            # Broadcast to everyone in the room (including sender)
            await chat_manager.broadcast(
                venue_id, response.model_dump()
            )
    except WebSocketDisconnect:
        pass
    finally:
        chat_manager.leave(venue_id, ws)


# ---------------------------------------------------------------------------
# API: songs
# ---------------------------------------------------------------------------


@app.get(f"{API_PREFIX}/songs", response_model=list[SongOut])
def list_songs(
    search: str | None = Query(None, description="Search title or artist"),
    genre: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    with db() as conn:
        q = "SELECT * FROM songs"
        params: list[Any] = []
        clauses: list[str] = []
        if search:
            clauses.append("(LOWER(title) LIKE ? OR LOWER(artist) LIKE ?)")
            params += [f"%{search.lower()}%", f"%{search.lower()}%"]
        if genre:
            clauses.append("LOWER(genre) = ?")
            params.append(genre.lower())
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY title LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
    return [song_row_to_dict(r) for r in rows]


@app.get(f"{API_PREFIX}/songs/ranges")
def list_ranges() -> dict[str, Any]:
    """Return the valid vocal ranges + a friendly description for each."""
    return {
        "ranges": [
            {"value": "bass", "label": "Bass", "desc": "Low & deep (E2-E4)"},
            {"value": "baritone", "label": "Baritone", "desc": "Low-mid (A2-A4)"},
            {"value": "tenor", "label": "Tenor", "desc": "Mid-high (C3-C5)"},
            {"value": "alto", "label": "Alto", "desc": "Low female (F3-F5)"},
            {"value": "mezzo", "label": "Mezzo", "desc": "Mid female (A3-A5)"},
            {"value": "soprano", "label": "Soprano", "desc": "High female (C4-C6)"},
        ]
    }


# ---------------------------------------------------------------------------
# API: song suggestions
# ---------------------------------------------------------------------------


@app.post(f"{API_PREFIX}/song-suggestions", response_model=list[SuggestionOut])
def suggest_songs(req: SuggestionRequest):
    user_range = req.vocal_range.strip().lower()
    if user_range not in RANGE_RANK:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vocal range '{req.vocal_range}'. Valid: {VALID_RANGES}",
        )

    with db() as conn:
        rows = conn.execute("SELECT * FROM songs").fetchall()

    fav_artists = [a for a in req.favorite_artists if a and a.strip()]
    fav_genres = [g for g in req.favorite_genres if g and g.strip()]

    scored: list[tuple[float, dict, str]] = []
    for r in rows:
        song = song_row_to_dict(r)
        score = score_song(song, user_range, fav_artists, fav_genres)
        # build a human-readable reason
        reasons: list[str] = []
        range_fit = [x.lower() for x in song["range_fit"]]
        if user_range in range_fit:
            reasons.append(f"Great fit for your {user_range} range")
        elif score >= 40:
            reasons.append(f"Workable for {user_range}")
        diff_label = {1: "easy", 2: "easy-ish", 3: "moderate", 4: "challenging", 5: "killer"}.get(
            song["difficulty"], "moderate"
        )
        reasons.append(f"{diff_label} difficulty")
        if any(a.strip().lower() in song["artist"].lower() for a in fav_artists):
            reasons.append(f"by a favorite artist ({song['artist']})")
        elif any(g.strip().lower() in song["genre"].lower() for g in fav_genres):
            reasons.append(f"matches your {song['genre'].lower()} taste")
        scored.append((score, song, " · ".join(reasons)))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: req.limit]
    return [{"song": s, "score": sc, "reason": reason} for sc, s, reason in top]


# ---------------------------------------------------------------------------
# Pydantic models for Stripe Connect
# ---------------------------------------------------------------------------


class ConnectOnboardRequest(BaseModel):
    """Request to start Stripe Connect onboarding for a venue's KJ.

    Email is required. All KYC fields are optional but recommended --
    when provided, they are prefilled on the Stripe Express account
    so the KJ's hosted onboarding page is confirm-and-click instead
    of fill-out-form.
    """
    venue_id: int
    email: str  # KJ's email for the Stripe account

    # Optional KYC prefill fields
    first_name: str | None = None
    last_name: str | None = None
    dob_day: int | None = None
    dob_month: int | None = None
    dob_year: int | None = None
    address_line1: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    address_postal_code: str | None = None
    ssn_last_4: str | None = None
    phone: str | None = None


class ConnectOnboardResponse(BaseModel):
    onboarding_url: str
    account_id: str


class ConnectStatusResponse(BaseModel):
    venue_id: int
    account_id: str | None
    onboarding_status: str  # none | needs_onboarding | pending_verification | active
    charges_enabled: bool
    payouts_enabled: bool
    missing_info: list[str] = []


class ConnectDashboardResponse(BaseModel):
    dashboard_url: str


class FeeBreakdownResponse(BaseModel):
    """Preview of how a payment would be split."""
    total: float
    platform_fee: float
    connected_amount: float
    stripe_processing: float
    platform_net: float
    fee_percentage: float


# ---------------------------------------------------------------------------
# API: Stripe Connect — KJ onboarding, status, dashboard
# ---------------------------------------------------------------------------


@app.post(f"{API_PREFIX}/connect/onboard", response_model=ConnectOnboardResponse)
def connect_onboard(req: ConnectOnboardRequest):
    """Create a Stripe Express account for a venue's KJ and return an
    onboarding link.

    If the venue already has a Stripe account ID, we generate a new
    onboarding link for that account instead of creating a new one.

    If KYC prefill fields are provided (name, DOB, address, SSN last 4),
    they are submitted to Stripe via the Persons API BEFORE creating the
    onboarding link. This makes the KJ's hosted onboarding page faster
    -- they confirm prefilled data instead of typing everything.
    """
    with db() as conn:
        venue = conn.execute(
            "SELECT * FROM venues WHERE id = ?", (req.venue_id,)
        ).fetchone()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    existing_acct = venue["stripe_account_id"] if "stripe_account_id" in venue.keys() else None

    if existing_acct:
        # Account already exists -- generate a fresh onboarding link.
        # Note: if KYC was already locked (link previously created),
        # the prefill attempt will silently fail. That's fine -- the
        # KJ just fills in whatever's missing on the hosted page.
        try:
            onboarding_url = connect.create_onboarding_link(existing_acct)
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Stripe error generating link: {e}"
            )
        return ConnectOnboardResponse(
            onboarding_url=onboarding_url, account_id=existing_acct
        )

    # Create new Express account
    try:
        account = connect.create_connected_account(
            email=req.email,
            metadata={"venue_id": str(req.venue_id), "venue_name": venue["name"]},
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Stripe error creating account: {e}"
        )

    # Prefill KYC info via Persons API BEFORE creating the Account Link.
    # Once an Account Link is created, Stripe locks KYC for Express accounts.
    has_kyc_prefill = any([
        req.first_name, req.last_name,
        req.dob_day is not None,
        req.address_line1,
        req.ssn_last_4,
    ])
    if has_kyc_prefill:
        try:
            connect.create_or_update_person(
                account_id=account.id,
                first_name=req.first_name,
                last_name=req.last_name,
                dob_day=req.dob_day,
                dob_month=req.dob_month,
                dob_year=req.dob_year,
                address_line1=req.address_line1,
                address_city=req.address_city,
                address_state=req.address_state,
                address_postal_code=req.address_postal_code,
                ssn_last_4=req.ssn_last_4,
                phone=req.phone,
                email=req.email,
            )
        except Exception:
            # Prefill is best-effort. If it fails, the KJ fills
            # everything on Stripe's hosted page.
            pass

    # Generate onboarding link
    try:
        onboarding_url = connect.create_onboarding_link(account.id)
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Stripe error generating link: {e}"
        )

    # Persist the account ID
    with db() as conn:
        conn.execute(
            "UPDATE venues SET stripe_account_id=?, stripe_onboarding_status='needs_onboarding' "
            "WHERE id=?",
            (account.id, req.venue_id),
        )

    return ConnectOnboardResponse(
        onboarding_url=onboarding_url, account_id=account.id
    )


@app.get(f"{API_PREFIX}/connect/status", response_model=ConnectStatusResponse)
def connect_status(venue_id: int = Query(..., description="Venue ID")):
    """Check the Stripe Connect onboarding status for a venue's KJ."""
    with db() as conn:
        venue = conn.execute(
            "SELECT * FROM venues WHERE id = ?", (venue_id,)
        ).fetchone()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    acct_id = venue["stripe_account_id"] if "stripe_account_id" in venue.keys() else None
    if not acct_id:
        return ConnectStatusResponse(
            venue_id=venue_id,
            account_id=None,
            onboarding_status="none",
            charges_enabled=False,
            payouts_enabled=False,
        )

    # Fetch live status from Stripe
    try:
        account = connect.retrieve_account(acct_id)
    except Exception:
        # If Stripe is unreachable, return what we have in the DB
        db_status = venue["stripe_onboarding_status"] if "stripe_onboarding_status" in venue.keys() else "none"
        return ConnectStatusResponse(
            venue_id=venue_id,
            account_id=acct_id,
            onboarding_status=db_status,
            charges_enabled=False,
            payouts_enabled=False,
        )

    # Update our DB with the latest status
    with db() as conn:
        conn.execute(
            "UPDATE venues SET stripe_onboarding_status=? WHERE id=?",
            (account.onboarding_status, venue_id),
        )

    return ConnectStatusResponse(
        venue_id=venue_id,
        account_id=acct_id,
        onboarding_status=account.onboarding_status,
        charges_enabled=account.charges_enabled,
        payouts_enabled=account.payouts_enabled,
        missing_info=account.missing_info,
    )


@app.get(f"{API_PREFIX}/connect/dashboard", response_model=ConnectDashboardResponse)
def connect_dashboard(venue_id: int = Query(..., description="Venue ID")):
    """Generate a login link to the Stripe Express Dashboard for a KJ."""
    with db() as conn:
        venue = conn.execute(
            "SELECT * FROM venues WHERE id = ?", (venue_id,)
        ).fetchone()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    acct_id = venue["stripe_account_id"] if "stripe_account_id" in venue.keys() else None
    if not acct_id:
        raise HTTPException(
            status_code=400,
            detail="This venue does not have a Stripe Connect account yet.",
        )

    try:
        url = connect.create_dashboard_link(acct_id)
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Stripe error generating dashboard link: {e}"
        )

    return ConnectDashboardResponse(dashboard_url=url)


@app.get(f"{API_PREFIX}/connect/fee-preview", response_model=FeeBreakdownResponse)
def connect_fee_preview(amount: float = Query(..., description="Amount in USD")):
    """Preview how a payment would be split between platform and KJ."""
    amount_cents = int(round(amount * 100))
    breakdown = connect.calculate_fee(amount_cents)
    return FeeBreakdownResponse(**breakdown.as_dict())


# ---------------------------------------------------------------------------
# API: KJ product management (configurable premium slot products)
# ---------------------------------------------------------------------------


class ProductCreateRequest(BaseModel):
    """Create a new premium slot product for a venue."""
    venue_id: int
    name: str  # e.g. "Premium Slot - $5", "Skip the Queue - $6"
    description: str = ""
    amount_usd: float  # e.g. 5.00, 6.00


class ProductUpdateRequest(BaseModel):
    """Update an existing product (e.g. enable/disable)."""
    product_id: int  # local DB ID
    active: bool | None = None
    name: str | None = None
    description: str | None = None


class ProductOut(BaseModel):
    id: int  # local DB ID
    venue_id: int
    name: str
    description: str
    amount_usd: float
    active: bool
    stripe_product_id: str | None = None
    stripe_price_id: str | None = None


class ProductListResponse(BaseModel):
    products: list[ProductOut]


@app.get(
    f"{API_PREFIX}/connect/products",
    response_model=ProductListResponse,
)
def list_products(venue_id: int = Query(..., description="Venue ID")):
    """List all premium slot products for a venue.

    Returns both active and inactive products. Products are created on
    Stripe (on the KJ's connected account) and tracked locally.
    """
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM kj_products WHERE venue_id=? ORDER BY active DESC, id ASC",
            (venue_id,),
        ).fetchall()

    products = [
        ProductOut(
            id=r["id"],
            venue_id=r["venue_id"],
            name=r["name"],
            description=r["description"] or "",
            amount_usd=r["amount_cents"] / 100,
            active=bool(r["active"]),
            stripe_product_id=r["stripe_product_id"],
            stripe_price_id=r["stripe_price_id"],
        )
        for r in rows
    ]
    return ProductListResponse(products=products)


@app.post(
    f"{API_PREFIX}/connect/products",
    response_model=ProductOut,
)
def create_product(req: ProductCreateRequest):
    """Create a new premium slot product for a venue's KJ.

    Creates a Stripe Product + Price on the KJ's connected account and
    tracks it locally. The KJ can create multiple products (e.g. a $5
    skip on slow nights, a $6 skip on busy nights) and enable/disable
    them based on traffic.
    """
    with db() as conn:
        venue = conn.execute(
            "SELECT * FROM venues WHERE id = ?", (req.venue_id,)
        ).fetchone()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    acct_id = venue["stripe_account_id"] if "stripe_account_id" in venue.keys() else None
    onboarding = venue["stripe_onboarding_status"] if "stripe_onboarding_status" in venue.keys() else "none"

    if not acct_id or onboarding != "active":
        raise HTTPException(
            status_code=400,
            detail="KJ must complete Stripe onboarding before creating products.",
        )

    amount_cents = int(round(req.amount_usd * 100))

    # Create product + price on Stripe (on the connected account)
    try:
        stripe_product_id = connect.create_product(
            connected_account_id=acct_id,
            name=req.name,
            description=req.description,
            metadata={"venue_id": str(req.venue_id)},
        )
        stripe_price_id = connect.create_price(
            connected_account_id=acct_id,
            product_id=stripe_product_id,
            amount_cents=amount_cents,
            metadata={"venue_id": str(req.venue_id)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Stripe error creating product: {e}"
        )

    # Track locally
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO kj_products
               (venue_id, stripe_product_id, stripe_price_id, name, description, amount_cents, active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (req.venue_id, stripe_product_id, stripe_price_id,
             req.name, req.description, amount_cents),
        )
        product_db_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM kj_products WHERE id=?", (product_db_id,)
        ).fetchone()

    return ProductOut(
        id=row["id"],
        venue_id=row["venue_id"],
        name=row["name"],
        description=row["description"] or "",
        amount_usd=row["amount_cents"] / 100,
        active=bool(row["active"]),
        stripe_product_id=row["stripe_product_id"],
        stripe_price_id=row["stripe_price_id"],
    )


@app.patch(
    f"{API_PREFIX}/connect/products",
    response_model=ProductOut,
)
def update_product(req: ProductUpdateRequest):
    """Update a product (rename, change description, enable/disable).

    Disabling a product (active=False) deactivates it on Stripe and
    hides it from the patron-facing app. The product remains in the
    KJ's Stripe dashboard for re-enabling later.
    """
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM kj_products WHERE id=?", (req.product_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")

    with db() as conn:
        venue = conn.execute(
            "SELECT * FROM venues WHERE id=?", (row["venue_id"],)
        ).fetchone()
    acct_id = venue["stripe_account_id"] if venue and "stripe_account_id" in venue.keys() else None

    # Update on Stripe if we have the account
    if acct_id and row["stripe_product_id"] and not STRIPE_SECRET_KEY.startswith("sk_tes"):
        try:
            connect.update_product(
                connected_account_id=acct_id,
                product_id=row["stripe_product_id"],
                active=req.active,
                name=req.name,
                description=req.description,
            )
        except Exception:
            pass  # Best-effort sync

    # Update locally
    with db() as conn:
        if req.active is not None:
            conn.execute(
                "UPDATE kj_products SET active=? WHERE id=?",
                (int(req.active), req.product_id),
            )
        if req.name:
            conn.execute(
                "UPDATE kj_products SET name=? WHERE id=?",
                (req.name, req.product_id),
            )
        if req.description is not None:
            conn.execute(
                "UPDATE kj_products SET description=? WHERE id=?",
                (req.description, req.product_id),
            )
        row = conn.execute(
            "SELECT * FROM kj_products WHERE id=?", (req.product_id,)
        ).fetchone()

    return ProductOut(
        id=row["id"],
        venue_id=row["venue_id"],
        name=row["name"],
        description=row["description"] or "",
        amount_usd=row["amount_cents"] / 100,
        active=bool(row["active"]),
        stripe_product_id=row["stripe_product_id"],
        stripe_price_id=row["stripe_price_id"],
    )


# ---------------------------------------------------------------------------
# API: Stripe checkout for premium slot reservation
# ---------------------------------------------------------------------------


@app.post(f"{API_PREFIX}/create-payment-session", response_model=PaymentResponse)
def create_payment_session(req: PaymentRequest):
    """Create a Stripe Checkout session for reserving a premium slot.

    A "premium slot" is a preferred singing time (default 3rd position in the
    rotation) that the KJ has agreed to offer as a way for singers to support
    the show. It is *not* a queue jump — the KJ confirms the final position.
    The price is KJ-configurable per venue (`premium_slot_price`).

    If the venue's KJ has completed Stripe Connect onboarding, the payment
    uses a destination charge: the platform fee (15-20%) is taken as
    `application_fee_amount` and the remainder is transferred to the KJ's
    connected account automatically.
    """
    with db() as conn:
        venue = conn.execute(
            "SELECT * FROM venues WHERE id = ?", (req.venue_id,)
        ).fetchone()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    amount = float(venue["premium_slot_price"])
    # Stripe expects cents
    amount_cents = int(round(amount * 100))

    kj_name = venue["kj_name"] or "the KJ"
    slot_pos = int(venue["premium_slot_position"])

    # Check if the KJ has a connected Stripe account
    connected_account_id = venue["stripe_account_id"] if "stripe_account_id" in venue.keys() else None
    onboarding_status = venue["stripe_onboarding_status"] if "stripe_onboarding_status" in venue.keys() else "none"

    # Record the payment attempt locally first
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO payments
               (stripe_session_id, venue_id, amount_usd, singer_name, song_request, status)
               VALUES (?,?,?,?,?, 'open')""",
            ("pending", req.venue_id, amount, req.singer_name, req.song_request),
        )
        payment_id = cur.lastrowid

    # If Stripe isn't configured, return a no-op "test" URL so the flow is
    # demonstrable without a real Stripe account.
    if STRIPE_SECRET_KEY.startswith("sk_tes"):
        return PaymentResponse(
            checkout_url=f"/api/payment-test?payment_id={payment_id}&venue={venue['name']}",
            session_id=f"test_session_{payment_id}",
        )

    # Build product info
    product_name = f"Premium Slot Reservation — {venue['name']}"
    product_desc = (
        f"Support {kj_name} and secure a preferred singing time "
        f"(~{slot_pos}{_ordinal(slot_pos)} slot)"
        + (f". Song: {req.song_request}" if req.song_request else "")
    )

    # Calculate fee breakdown for this charge
    fee = connect.calculate_fee(amount_cents)

    # If the KJ has an active connected account, use a destination charge
    # so the KJ gets their share automatically. Otherwise, the charge
    # lands on the platform account only (legacy behavior).
    use_connect = False
    if connected_account_id and onboarding_status == "active":
        if STRIPE_SECRET_KEY.startswith("sk_tes"):
            # Test mode — mock the Connect status check
            use_connect = True
        else:
            try:
                acct = connect.retrieve_account(connected_account_id)
                use_connect = acct.charges_enabled
            except Exception:
                use_connect = False

    try:
        if use_connect:
            # Destination charge: customer pays, platform fee is taken,
            # remainder transfers to KJ's connected account.
            # Deep link redirects back to the mobile app via custom scheme
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "product_data": {
                                "name": product_name,
                                "description": product_desc,
                            },
                            "unit_amount": amount_cents,
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url=f"thehopper://payment-success?venue_id={req.venue_id}",
                cancel_url=f"thehopper://payment-cancelled?venue_id={req.venue_id}",
                payment_intent_data={
                    "application_fee_amount": fee.platform_fee_cents,
                    "transfer_data": {
                        "destination": connected_account_id,
                    },
                },
                metadata={
                    "payment_id": str(payment_id),
                    "venue_id": str(req.venue_id),
                    "singer_name": req.singer_name,
                    "song_request": req.song_request,
                    "connected_account_id": connected_account_id,
                    "platform_fee_cents": str(fee.platform_fee_cents),
                    "connected_amount_cents": str(fee.connected_amount_cents),
                },
            )
        else:
            # No Connect account — charge lands on platform only
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "product_data": {
                                "name": product_name,
                                "description": product_desc,
                            },
                            "unit_amount": amount_cents,
                        },
                        "quantity": 1,
                    }
                ],
                mode="payment",
                success_url=f"thehopper://payment-success?venue_id={req.venue_id}",
                cancel_url=f"thehopper://payment-cancelled?venue_id={req.venue_id}",
                metadata={
                    "payment_id": str(payment_id),
                    "venue_id": str(req.venue_id),
                    "singer_name": req.singer_name,
                    "song_request": req.song_request,
                },
            )
    except stripe.error.StripeError as e:
        # Record failure on the payment row
        with db() as conn:
            conn.execute(
                "UPDATE payments SET status='failed' WHERE id=?", (payment_id,)
            )
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")

    # Persist the real session id
    with db() as conn:
        conn.execute(
            "UPDATE payments SET stripe_session_id=?, status='open' WHERE id=?",
            (session.id, payment_id),
        )

    return PaymentResponse(checkout_url=session.url, session_id=session.id)


def _ordinal(n: int) -> str:
    """Return the ordinal suffix for an integer: 1 -> 'st', 2 -> 'nd', 3 -> 'rd'."""
    n = abs(n)
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


@app.get("/api/payment-test")
def payment_test(payment_id: int, venue: str):
    """Stand-in success page when Stripe isn't configured."""
    with db() as conn:
        conn.execute(
            "UPDATE payments SET status='paid', paid_at=datetime('now') WHERE id=?",
            (payment_id,),
        )
    return {
        "status": "paid (test mode)",
        "payment_id": payment_id,
        "venue": venue,
        "message": (
            "Your premium slot request has been sent to the KJ. They'll confirm "
            "your position. (Stripe is not configured — in test mode we mark the "
            "payment as paid immediately. Set STRIPE_SECRET_KEY for real checkout.)"
        ),
    }


@app.post(f"{API_PREFIX}/stripe-webhook")
async def stripe_webhook(request: Request) -> dict[str, str]:
    """Webhook for Stripe events.

    Handles both standard payment events and Stripe Connect events:
      - checkout.session.completed: mark payment as paid
      - account.updated: sync connected account status in our DB
    """
    import json

    body = await request.body()

    # Verify webhook signature in production
    if STRIPE_WEBHOOK_SECRET:
        sig = request.headers.get("stripe-signature", "")
        try:
            event = ConnectManager.verify_webhook_event(
                body, sig, STRIPE_WEBHOOK_SECRET
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid signature: {e}")
    else:
        # Local dev: accept raw payload
        try:
            event = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type", "")
    print(f"[Webhook] Received event: {event_type}", flush=True)

    # --- Payment completed ---
    if event_type == "checkout.session.completed":
        sess = event["data"]["object"]
        pid = sess.get("metadata", {}).get("payment_id")
        venue_id = sess.get("metadata", {}).get("venue_id")
        singer_name = sess.get("metadata", {}).get("singer_name", "Someone")
        song_request = sess.get("metadata", {}).get("song_request", "")
        print(f"[Webhook] checkout.session.completed: payment_id={pid}, venue_id={venue_id}, metadata={sess.get('metadata', {})}", flush=True)
        if pid:
            with db() as conn:
                conn.execute(
                    "UPDATE payments SET status='paid', paid_at=datetime('now') "
                    "WHERE id=?",
                    (pid,),
                )
                # Notify the KJ about the premium slot payment
                if venue_id:
                    notify_kj_for_venue(
                        conn,
                        int(venue_id),
                        "Premium Slot Reserved",
                        f"{singer_name} just reserved a premium slot" + (f" (song: {song_request})" if song_request else ""),
                        {"venue_id": int(venue_id), "type": "premium_slot"},
                    )

    # --- Connect: account updated (KYC status changed) ---
    elif event_type == "account.updated":
        acct = event["data"]["object"]
        acct_id = acct.get("id")
        charges_enabled = acct.get("charges_enabled", False)
        payouts_enabled = acct.get("payouts_enabled", False)
        details_submitted = acct.get("details_submitted", False)

        # Determine status
        if charges_enabled and payouts_enabled:
            status = "active"
        elif details_submitted:
            status = "pending_verification"
        else:
            status = "needs_onboarding"

        # When account becomes active, configure daily payouts
        if status == "active" and not STRIPE_SECRET_KEY.startswith("sk_tes"):
            connect.set_daily_payouts(acct_id)

        # Update the venue that owns this account (legacy)
        with db() as conn:
            conn.execute(
                "UPDATE venues SET stripe_onboarding_status=? "
                "WHERE stripe_account_id=?",
                (status, acct_id),
            )
            # Also update any KJ with this account
            conn.execute(
                "UPDATE kjs SET stripe_onboarding_status=? "
                "WHERE stripe_account_id=?",
                (status, acct_id),
            )
            # Notify the KJ
            kj = conn.execute(
                "SELECT id, phone FROM kjs WHERE stripe_account_id=?", (acct_id,)
            ).fetchone()
            if kj and status == "active":
                send_sms(
                    kj["phone"],
                    "Your Stripe account is active! You can now receive payments for premium slots on TheHopper."
                )
                # Push notification
                devices = conn.execute(
                    "SELECT push_token FROM devices WHERE kj_id=?", (kj["id"],)
                ).fetchall()
                send_push(
                    [d["push_token"] for d in devices],
                    "Stripe Ready",
                    "Your Stripe account is active. You can now get paid for premium slots!",
                )

    # --- Connect: transfer created (money moved to KJ) ---
    elif event_type == "transfer.created":
        transfer = event["data"]["object"]
        # Could log this or update a transfers table
        # For now we just acknowledge it
        pass

    return {"received": "ok"}


# ---------------------------------------------------------------------------
# API: Venue submission (add a karaoke spot)
# ---------------------------------------------------------------------------


@app.post(f"{API_PREFIX}/venues/submit", response_model=VenueSubmissionResponse)
def submit_venue(req: VenueSubmissionRequest):
    """Submit a new karaoke spot for moderation.

    If is_kj=True, the submitter is claiming to be the KJ. They'll need
    to complete phone verification + KJ onboarding after submission.

    Checks for duplicate venues using fuzzy name matching + geographic
    proximity before accepting the submission.
    """
    if not req.name.strip() or not req.address.strip() or not req.city.strip():
        raise HTTPException(status_code=400, detail="Name, address, and city are required")

    nights = ",".join(req.karaoke_nights) if req.karaoke_nights else ""

    # Geocode the address (simple approach — just store nulls if it fails)
    lat, lng = None, None
    try:
        import urllib.parse as up
        geocode_url = f"https://nominatim.openstreetmap.org/search?q={up.quote(req.address + ', ' + req.city + ', FL')}&format=json&limit=1"
        geo_req = UrllibRequest(geocode_url)
        geo_req.add_header("User-Agent", "TheHopper/1.0")
        with urlopen(geo_req, timeout=10) as resp:
            results = json.loads(resp.read())
            if results:
                lat = float(results[0]["lat"])
                lng = float(results[0]["lon"])
    except Exception:
        pass  # Geocoding is optional — admin can fix later

    # Canonicalization: check for duplicates before accepting
    with db() as conn:
        dupe = _check_duplicate_venue(conn, req.name, req.address, req.city, lat, lng)
    if dupe:
        is_pending = dupe.get("is_pending", False)
        if is_pending:
            return VenueSubmissionResponse(
                id=dupe["id"],
                status="duplicate_pending",
                message=f"A submission for '{dupe['name']}' is already pending review.",
            )
        return VenueSubmissionResponse(
            id=dupe["id"],
            status="duplicate",
            message=f"'{dupe['name']}' already exists in {dupe['city']}. Use that venue instead.",
        )

    submitter_phone = normalize_phone(req.submitter_phone) if req.submitter_phone else None

    with db() as conn:
        cur = conn.execute(
            """INSERT INTO venue_submissions
               (name, address, city, lat, lng, karaoke_nights, start_time, end_time,
                kj_name, phone, website, instagram, vibe, is_kj, submitter_phone, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending')""",
            (
                req.name.strip(), req.address.strip(), req.city.strip(),
                lat, lng, nights, req.start_time, req.end_time,
                req.kj_name, req.phone, req.website, req.instagram, req.vibe,
                1 if req.is_kj else 0, submitter_phone,
            ),
        )
        submission_id = cur.lastrowid

    return VenueSubmissionResponse(
        id=submission_id,
        status="pending",
        message="Thanks! Your submission is pending review. We'll text you when it's approved."
    )


@app.post(f"{API_PREFIX}/venues/submissions/{{submission_id}}/approve")
def approve_submission(submission_id: int):
    """Approve a venue submission — creates a real venue record."""
    with db() as conn:
        sub = conn.execute(
            "SELECT * FROM venue_submissions WHERE id = ? AND status = 'pending'",
            (submission_id,),
        ).fetchone()
        if not sub:
            raise HTTPException(status_code=404, detail="Submission not found or already reviewed")

        # Create the venue
        cur = conn.execute(
            """INSERT INTO venues
               (name, address, city, lat, lng, karaoke_nights, start_time, end_time,
                kj_name, phone, website, price_jump_queue, premium_slot_position,
                premium_slot_price, vibe)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sub["name"], sub["address"], sub["city"],
                sub["lat"] if sub["lat"] is not None else 0.0,
                sub["lng"] if sub["lng"] is not None else 0.0,
                sub["karaoke_nights"], sub["start_time"], sub["end_time"],
                sub["kj_name"], sub["phone"], sub["website"],
                5.0, 3, 5.0, sub["vibe"],
            ),
        )
        venue_id = cur.lastrowid

        # Mark submission as approved
        conn.execute(
            "UPDATE venue_submissions SET status='approved', reviewed_at=datetime('now'), venue_id=? WHERE id=?",
            (venue_id, submission_id),
        )

        # If the submitter is the KJ and we have their phone, create a KJ record
        if sub["is_kj"] and sub["submitter_phone"]:
            existing_kj = conn.execute(
                "SELECT id FROM kjs WHERE phone = ?", (sub["submitter_phone"],)
            ).fetchone()
            if existing_kj:
                kj_id = existing_kj["id"]
            else:
                kj_cur = conn.execute(
                    "INSERT INTO kjs (name, phone) VALUES (?, ?)",
                    (sub["kj_name"] or sub["name"], sub["submitter_phone"]),
                )
                kj_id = kj_cur.lastrowid
            # Link KJ to venue
            conn.execute("UPDATE venues SET kj_id=? WHERE id=?", (kj_id, venue_id))

    # Notify submitter
    if sub["submitter_phone"]:
        send_sms(
            sub["submitter_phone"],
            f"Your karaoke spot '{sub['name']}' is now live on TheHopper! "
            f"Download the app to manage your gigs."
        )

    return {"status": "approved", "venue_id": venue_id}


@app.post(f"{API_PREFIX}/venues/submissions/{{submission_id}}/reject")
def reject_submission(submission_id: int):
    """Reject a venue submission."""
    with db() as conn:
        sub = conn.execute(
            "SELECT * FROM venue_submissions WHERE id = ? AND status = 'pending'",
            (submission_id,),
        ).fetchone()
        if not sub:
            raise HTTPException(status_code=404, detail="Submission not found or already reviewed")
        conn.execute(
            "UPDATE venue_submissions SET status='rejected', reviewed_at=datetime('now') WHERE id=?",
            (submission_id,),
        )
    return {"status": "rejected"}


# ---------------------------------------------------------------------------
# API: Phone verification
# ---------------------------------------------------------------------------


@app.post(f"{API_PREFIX}/phone/send-code")
def send_phone_code(req: PhoneSendCodeRequest):
    """Send a 6-digit verification code via SMS."""
    phone = normalize_phone(req.phone)
    code = generate_code()
    expires = time.time() + 600  # 10 minutes

    with db() as conn:
        # Invalidate any previous codes for this phone by expiring them. Do NOT
        # mark them verified=1 to retire them: that made "verified" mean either
        # "the caller proved ownership" or "we superseded this row", so a second
        # send-code call would leave a verified row for a number nobody proved.
        conn.execute(
            "UPDATE phone_verifications SET expires_at='0' WHERE phone=? AND verified=0",
            (phone,),
        )
        conn.execute(
            "INSERT INTO phone_verifications (phone, code, expires_at) VALUES (?, ?, ?)",
            (phone, code, str(expires)),
        )

    sent = send_sms(phone, f"TheHopper verification code: {code}")
    if not sent:
        raise HTTPException(status_code=502, detail="Failed to send SMS")

    return {"status": "sent", "message": "Verification code sent"}


@app.post(f"{API_PREFIX}/phone/verify", response_model=PhoneVerifyResponse)
def verify_phone(req: PhoneVerifyRequest):
    """Verify a phone with the code sent via SMS."""
    phone = normalize_phone(req.phone)
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM phone_verifications WHERE phone=? AND code=? AND verified=0 "
            "ORDER BY created_at DESC LIMIT 1",
            (phone, req.code),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Invalid or expired code")
        if float(row["expires_at"]) < time.time():
            raise HTTPException(status_code=400, detail="Code expired. Request a new one.")
        conn.execute("UPDATE phone_verifications SET verified=1 WHERE id=?", (row["id"],))

        # Mint a session token and persist it, so later requests can prove the
        # caller controls this number.
        token = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO phone_sessions (token, phone, expires_at) VALUES (?,?,?)",
            (token, phone, str(time.time() + PHONE_SESSION_TTL_SECONDS)),
        )

    return PhoneVerifyResponse(verified=True, token=token)


# ---------------------------------------------------------------------------
# API: KJ (Karaoke Jockey) onboarding
# ---------------------------------------------------------------------------


def _kj_row_to_out(row: sqlite3.Row) -> KJOut:
    """Build a KJOut from a db row, handling optional columns safely."""
    keys = set(row.keys())
    stripe_status = row["stripe_onboarding_status"] if "stripe_onboarding_status" in keys else "none"
    return KJOut(
        id=row["id"], name=row["name"], phone=row["phone"], bio=row["bio"],
        photo_url=row["photo_url"], instagram=row["instagram"], website=row["website"],
        stripe_onboarding_status=stripe_status or "none",
        verified=bool(row["verified"]), created_at=row["created_at"],
        business_name=row["business_name"] if "business_name" in keys else None,
        site_slug=row["site_slug"] if "site_slug" in keys else None,
        city=row["city"] if "city" in keys else None,
        song_request_required=bool(row["song_request_required"]) if "song_request_required" in keys else False,
    )


@app.post(f"{API_PREFIX}/kjs/register", response_model=KJOut)
def register_kj(req: KJRegisterRequest):
    """Register a new KJ or update an existing one by phone number."""
    phone = normalize_phone(req.phone)
    with db() as conn:
        existing = conn.execute("SELECT * FROM kjs WHERE phone=?", (phone,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE kjs SET name=?, bio=?, instagram=?, website=?, photo_url=?, business_name=COALESCE(?, business_name), city=COALESCE(?, city) WHERE id=?",
                (req.name.strip(), req.bio, req.instagram, req.website, req.photo_url, req.business_name, req.city, existing["id"]),
            )
            row = conn.execute("SELECT * FROM kjs WHERE id=?", (existing["id"],)).fetchone()
        else:
            cur = conn.execute(
                "INSERT INTO kjs (name, phone, bio, instagram, website, photo_url, business_name, city) VALUES (?,?,?,?,?,?,?,?)",
                (req.name.strip(), phone, req.bio, req.instagram, req.website, req.photo_url, req.business_name, req.city),
            )
            row = conn.execute("SELECT * FROM kjs WHERE id=?", (cur.lastrowid,)).fetchone()
    return _kj_row_to_out(row)


# NOTE: must be declared before /kjs/{kj_id} — that route types kj_id as int,
# so "me" would fail parsing with a 422 rather than falling through to here.
@app.get(f"{API_PREFIX}/kjs/me", response_model=KJOut)
def get_my_kj(x_session_token: str | None = Header(default=None)):
    """Return the KJ owned by the caller's verified phone number.

    404 when the number has never been onboarded as a KJ — that is the normal
    "new KJ" case, not an error.
    """
    with db() as conn:
        phone = phone_for_token(conn, x_session_token)
        if not phone:
            raise HTTPException(status_code=401, detail="Verify your phone number")
        row = conn.execute("SELECT * FROM kjs WHERE phone=?", (phone,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No KJ profile for this number")
    return _kj_row_to_out(row)


@app.patch(f"{API_PREFIX}/kjs/{{kj_id}}/profile", response_model=KJOut)
def update_kj_profile(kj_id: int, req: KJProfileUpdateRequest,
                      x_session_token: str | None = Header(default=None)):
    """Edit a KJ's stage name and/or phone number.

    Two separate proofs are required to move a number, because either one alone
    is an account-takeover path:
      - X-Session-Token must match the KJ's *current* phone. Without it, anyone
        who guessed a kj_id could repoint someone else's account at themselves.
      - new_phone_token must match the *new* phone. Without it, a KJ could
        claim a number they do not control and capture its SMS notifications.
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="KJ not found")

        caller_phone = phone_for_token(conn, x_session_token)
        if not caller_phone or caller_phone != row["phone"]:
            raise HTTPException(status_code=401, detail="Verify your phone number")

        new_name = req.name.strip() if req.name is not None else None
        if new_name is not None and not new_name:
            raise HTTPException(status_code=400, detail="Stage name cannot be empty")

        new_phone = normalize_phone(req.phone) if req.phone else None
        if new_phone and new_phone != row["phone"]:
            proven = phone_for_token(conn, req.new_phone_token)
            if proven != new_phone:
                raise HTTPException(
                    status_code=401,
                    detail="Verify the new phone number before changing it",
                )
            clash = conn.execute(
                "SELECT id FROM kjs WHERE phone=? AND id!=?", (new_phone, kj_id)
            ).fetchone()
            if clash:
                raise HTTPException(
                    status_code=409,
                    detail="That number already belongs to another KJ profile",
                )
        else:
            new_phone = None

        if new_name is not None:
            conn.execute("UPDATE kjs SET name=? WHERE id=?", (new_name, kj_id))
        if new_phone:
            conn.execute("UPDATE kjs SET phone=? WHERE id=?", (new_phone, kj_id))
            # Push notifications are routed by phone, so move the device rows
            # too or the KJ silently stops receiving alerts.
            conn.execute(
                "UPDATE devices SET phone=? WHERE phone=?", (new_phone, row["phone"])
            )
            # The old number must no longer authenticate this account.
            conn.execute("DELETE FROM phone_sessions WHERE phone=?", (row["phone"],))

        updated = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()
    return _kj_row_to_out(updated)


@app.get(f"{API_PREFIX}/kjs/{{kj_id}}", response_model=KJOut)
def get_kj(kj_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="KJ not found")
    return _kj_row_to_out(row)


@app.patch(f"{API_PREFIX}/kjs/{{kj_id}}/settings", response_model=KJOut)
def update_kj_settings(kj_id: int, song_request_required: bool | None = None):
    """Update KJ preferences. Currently supports song_request_required."""
    with db() as conn:
        row = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="KJ not found")
        if song_request_required is not None:
            conn.execute(
                "UPDATE kjs SET song_request_required=? WHERE id=?",
                (1 if song_request_required else 0, kj_id),
            )
        row = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()
    return _kj_row_to_out(row)


@app.get(f"{API_PREFIX}/kjs", response_model=list[KJOut])
def list_kjs():
    """List all KJs."""
    with db() as conn:
        rows = conn.execute("SELECT * FROM kjs ORDER BY created_at DESC").fetchall()
    return [_kj_row_to_out(r) for r in rows]


@app.post(f"{API_PREFIX}/kjs/link-venue")
def link_kj_to_venue(req: KJLinkVenueRequest):
    """Link a KJ to a venue (claim ownership)."""
    with db() as conn:
        kj = conn.execute("SELECT * FROM kjs WHERE id=?", (req.kj_id,)).fetchone()
        if not kj:
            raise HTTPException(status_code=404, detail="KJ not found")
        venue = conn.execute("SELECT * FROM venues WHERE id=?", (req.venue_id,)).fetchone()
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")
        conn.execute("UPDATE venues SET kj_id=?, kj_name=? WHERE id=?", (req.kj_id, kj["name"], req.venue_id))
    return {"status": "linked", "kj_id": req.kj_id, "venue_id": req.venue_id}


@app.get(f"{API_PREFIX}/kjs/{{kj_id}}/venues")
def get_kj_venues(kj_id: int):
    """Get all venues associated with a KJ."""
    with db() as conn:
        rows = conn.execute("SELECT * FROM venues WHERE kj_id=? ORDER BY name", (kj_id,)).fetchall()
    return [venue_row_to_dict(r) for r in rows]


class KJAddVenueRequest(BaseModel):
    """KJ adds a venue to their profile — either claiming an existing
    venue or submitting a new one."""
    name: str
    address: str
    city: str
    karaoke_nights: list[str] = []
    start_time: str = "20:00"
    end_time: str = "00:00"
    phone: str | None = None
    website: str | None = None
    instagram: str | None = None
    vibe: str | None = None


class KJAddVenueResponse(BaseModel):
    status: str  # "linked" (claimed existing) | "submitted" (new, pending) | "duplicate"
    venue_id: int | None = None
    submission_id: int | None = None
    message: str


@app.post(f"{API_PREFIX}/kjs/{{kj_id}}/venues", response_model=KJAddVenueResponse)
def kj_add_venue(kj_id: int, req: KJAddVenueRequest):
    """Add a venue to a KJ's profile.

    If the venue already exists (fuzzy match), the KJ is linked to it
    instead of creating a duplicate. If it's genuinely new, a venue
    submission is created (pending admin approval) with the KJ pre-linked.
    """
    with db() as conn:
        kj = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()
    if not kj:
        raise HTTPException(status_code=404, detail="KJ not found")

    if not req.name.strip() or not req.address.strip() or not req.city.strip():
        raise HTTPException(status_code=400, detail="Name, address, and city are required")

    # Geocode
    lat, lng = None, None
    try:
        import urllib.parse as up
        geocode_url = f"https://nominatim.openstreetmap.org/search?q={up.quote(req.address + ', ' + req.city + ', FL')}&format=json&limit=1"
        geo_req = UrllibRequest(geocode_url)
        geo_req.add_header("User-Agent", "TheHopper/1.0")
        with urlopen(geo_req, timeout=10) as resp:
            results = json.loads(resp.read())
            if results:
                lat = float(results[0]["lat"])
                lng = float(results[0]["lon"])
    except Exception:
        pass

    # Canonicalization check
    with db() as conn:
        dupe = _check_duplicate_venue(conn, req.name, req.address, req.city, lat, lng)

    if dupe:
        venue_id = dupe.get("id")
        if venue_id and not dupe.get("is_pending"):
            # Link the KJ to the existing venue
            with db() as conn:
                existing_kj = conn.execute(
                    "SELECT kj_id FROM venues WHERE id=?", (venue_id,)
                ).fetchone()
                if existing_kj and existing_kj["kj_id"]:
                    return KJAddVenueResponse(
                        status="duplicate",
                        venue_id=venue_id,
                        message=f"'{dupe['name']}' already has a KJ assigned.",
                    )
                conn.execute(
                    "UPDATE venues SET kj_id=?, kj_name=? WHERE id=?",
                    (kj_id, kj["name"], venue_id),
                )
            return KJAddVenueResponse(
                status="linked",
                venue_id=venue_id,
                message=f"You're now linked to '{dupe['name']}'.",
            )
        return KJAddVenueResponse(
            status="duplicate",
            message=f"A submission for '{dupe['name']}' is already pending.",
        )

    # New venue — create a submission with KJ pre-linked
    nights = ",".join(req.karaoke_nights) if req.karaoke_nights else ""
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO venue_submissions
               (name, address, city, lat, lng, karaoke_nights, start_time, end_time,
                kj_name, phone, website, instagram, vibe, is_kj, submitter_phone, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending')""",
            (
                req.name.strip(), req.address.strip(), req.city.strip(),
                lat, lng, nights, req.start_time, req.end_time,
                kj["name"], req.phone, req.website, req.instagram, req.vibe,
                1, kj["phone"],
            ),
        )
        submission_id = cur.lastrowid

    return KJAddVenueResponse(
        status="submitted",
        submission_id=submission_id,
        message=f"'{req.name}' submitted for review. We'll text you when it's approved.",
    )


@app.post(f"{API_PREFIX}/kjs/{{kj_id}}/stripe-onboard")
def kj_stripe_onboard(
    kj_id: int,
    email: str = Query(..., description="KJ email for Stripe"),
    business_name: str | None = Query(None, description="Business name for Stripe (defaults to KJ name)"),
    first_name: str | None = Query(None, description="KJ first name for KYC prefill"),
    last_name: str | None = Query(None, description="KJ last name for KYC prefill"),
    dob_day: int | None = Query(None, description="Date of birth day"),
    dob_month: int | None = Query(None, description="Date of birth month"),
    dob_year: int | None = Query(None, description="Date of birth year"),
    address_line1: str | None = Query(None, description="Street address"),
    address_city: str | None = Query(None, description="City"),
    address_state: str | None = Query(None, description="State"),
    address_postal_code: str | None = Query(None, description="ZIP code"),
    ssn_last_4: str | None = Query(None, description="Last 4 of SSN"),
):
    """Start Stripe Connect onboarding for a KJ.

    Accepts optional KYC fields for prefilling the Stripe Express
    onboarding form. The KJ's name and phone from the kjs table
    are used automatically if available.

    If business_name is provided (or the KJ already has one), a
    site_slug is generated and a public business page is served at
    /kj-sites/{slug}. That URL is passed to Stripe as
    business_profile.url, which Stripe requires to verify the business.
    """
    with db() as conn:
        kj = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()
    if not kj:
        raise HTTPException(status_code=404, detail="KJ not found")

    existing_acct = kj["stripe_account_id"]

    # Always save the business_name if the KJ provided one (even if
    # they already have a Stripe account — they may be re-onboarding
    # with a different name).
    if business_name and business_name != kj["business_name"]:
        with db() as conn:
            conn.execute(
                "UPDATE kjs SET business_name=? WHERE id=?",
                (business_name, kj_id),
            )

    if existing_acct:
        # Update the business_profile.name on the existing Stripe account
        # so it matches what the KJ entered.
        if business_name:
            try:
                import stripe
                stripe.Account.modify(existing_acct, business_profile={"name": business_name})
            except Exception:
                pass  # Best-effort — not all account states allow this
        try:
            onboarding_url = connect.create_onboarding_link(existing_acct)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
        return {"onboarding_url": onboarding_url, "account_id": existing_acct}

    # Determine the business name and generate a site slug if needed.
    # If the KJ already has their own website, use that as the Stripe
    # business_profile.url. Only auto-generate a kj-site for KJs who
    # don't have one.
    biz_name = business_name or kj["business_name"] or kj["name"]
    kj_website = kj["website"] if kj["website"] else None

    if not kj_website:
        # No existing website — auto-generate one
        with db() as conn:
            if not kj["site_slug"]:
                slug = unique_slug(conn, biz_name)
                conn.execute(
                    "UPDATE kjs SET site_slug=?, business_name=? WHERE id=?",
                    (slug, biz_name, kj_id),
                )
            elif business_name and business_name != kj["business_name"]:
                conn.execute(
                    "UPDATE kjs SET business_name=? WHERE id=?",
                    (business_name, kj_id),
                )
            # Re-read to get the current slug
            kj = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()

        site_slug = kj["site_slug"]
        business_url = f"https://{site_slug}.{KARAOKESPOT_DOMAIN}"
    else:
        business_url = kj_website
        # Still save the business_name if provided
        if business_name and business_name != kj["business_name"]:
            with db() as conn:
                conn.execute(
                    "UPDATE kjs SET business_name=? WHERE id=?",
                    (business_name, kj_id),
                )

    try:
        account = connect.create_connected_account(
            email=email,
            business_name=biz_name,
            business_url=business_url,
            metadata={"kj_id": str(kj_id), "kj_name": kj["name"]},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error creating account: {e}")

    # Prefill KYC from provided fields + KJ's stored name/phone
    # Use the KJ's name from the DB if first_name/last_name not provided
    kj_name = kj["name"] or ""
    kj_name_parts = kj_name.split(" ", 1)
    prefill_first = first_name or (kj_name_parts[0] if kj_name_parts else None)
    prefill_last = last_name or (kj_name_parts[1] if len(kj_name_parts) > 1 else None)
    kj_phone = kj["phone"]

    has_kyc_prefill = any([prefill_first, prefill_last, dob_day is not None, address_line1, ssn_last_4])
    if has_kyc_prefill:
        try:
            connect.create_or_update_person(
                account_id=account.id,
                first_name=prefill_first,
                last_name=prefill_last,
                dob_day=dob_day,
                dob_month=dob_month,
                dob_year=dob_year,
                address_line1=address_line1,
                address_city=address_city,
                address_state=address_state,
                address_postal_code=address_postal_code,
                ssn_last_4=ssn_last_4,
                phone=kj_phone,
                email=email,
            )
        except Exception:
            pass  # Best-effort prefill

    try:
        onboarding_url = connect.create_onboarding_link(account.id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error generating link: {e}")

    with db() as conn:
        conn.execute(
            "UPDATE kjs SET stripe_account_id=?, stripe_onboarding_status='needs_onboarding' WHERE id=?",
            (account.id, kj_id),
        )

    return {"onboarding_url": onboarding_url, "account_id": account.id}


@app.get(f"{API_PREFIX}/kjs/{{kj_id}}/stripe-status")
def kj_stripe_status(kj_id: int):
    """Check Stripe Connect onboarding status for a KJ."""
    with db() as conn:
        kj = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()
    if not kj:
        raise HTTPException(status_code=404, detail="KJ not found")

    acct_id = kj["stripe_account_id"]
    if not acct_id:
        return {"kj_id": kj_id, "onboarding_status": "none", "charges_enabled": False, "payouts_enabled": False}

    try:
        account = connect.retrieve_account(acct_id)
    except Exception:
        return {"kj_id": kj_id, "onboarding_status": kj["stripe_onboarding_status"], "charges_enabled": False, "payouts_enabled": False}

    with db() as conn:
        conn.execute(
            "UPDATE kjs SET stripe_onboarding_status=? WHERE id=?",
            (account.onboarding_status, kj_id),
        )

    return {
        "kj_id": kj_id,
        "onboarding_status": account.onboarding_status,
        "charges_enabled": account.charges_enabled,
        "payouts_enabled": account.payouts_enabled,
        "missing_info": account.missing_info,
    }


# ---------------------------------------------------------------------------
# Stripe onboarding return pages
# ---------------------------------------------------------------------------


@app.get("/connect/complete")
def connect_complete_page():
    """Landing page after Stripe onboarding completes."""
    return HTMLResponse(
        content="""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Onboarding Complete | TheHopper</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; background: #1a1a2e; color: #e8e4f0; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
    .card { text-align: center; max-width: 400px; padding: 2rem; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
    p { color: #a09ab8; line-height: 1.5; }
    .check { font-size: 3rem; margin-bottom: 1rem; }
  </style>
</head>
<body>
  <div class="card">
    <div class="check">&#10003;</div>
    <h1>Onboarding Complete</h1>
    <p>You can close this page and return to TheHopper.</p>
  </div>
</body>
</html>""",
        media_type="text/html",
    )


@app.get("/connect/refresh")
def connect_refresh_page():
    """Landing page for Stripe onboarding refresh."""
    return HTMLResponse(
        content="""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Onboarding | TheHopper</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; background: #1a1a2e; color: #e8e4f0; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
    .card { text-align: center; max-width: 400px; padding: 2rem; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
    p { color: #a09ab8; line-height: 1.5; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Need to refresh?</h1>
    <p>Return to TheHopper and tap "Set up payments" to restart onboarding.</p>
  </div>
</body>
</html>""",
        media_type="text/html",
    )


# ---------------------------------------------------------------------------
# KJ public site (auto-generated static page for Stripe business_profile)
# ---------------------------------------------------------------------------

def _format_phone(phone: str) -> str:
    """Format a phone number as (XXX) XXX-XXXX."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone


def _format_time(t: str) -> str:
    """Convert 24-hour time (HH:MM) to 12-hour with am/pm."""
    try:
        h, m = t.split(":")
        h = int(h)
        suffix = "pm" if h >= 12 else "am"
        h12 = h % 12
        if h12 == 0:
            h12 = 12
        return f"{h12}:{m}{suffix}"
    except Exception:
        return t


def _kj_site_html(kj: sqlite3.Row, venues: list[sqlite3.Row]) -> str:
    """Render a self-contained HTML page for a KJ's business.

    Layout: full-width header > hero (left-justified) > schedule+map (two-col)
    > venue details (reorderable) > services > footer. Includes Google Maps
    embed with venue markers and click-to-zoom interactivity.
    """
    import html, json as _json

    GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    biz = kj["business_name"] or kj["name"]
    biz_esc = html.escape(biz)
    bio = html.escape(kj["bio"] or "Karaoke host. Live karaoke nights, song suggestions, and premium slot bookings through TheHopper.")
    kj_phone = kj["phone"] or ""
    kj_phone_fmt = _format_phone(kj_phone)
    kj_instagram = kj["instagram"] or ""
    kj_website = kj["website"] or ""

    # Social links
    links = []
    if kj_instagram:
        ig = html.escape(kj_instagram.lstrip("@"))
        links.append(f'<a href="https://instagram.com/{ig}" target="_blank" rel="noopener" class="social-link"><span class="ico">IG</span> @{ig}</a>')
    if kj_website:
        ws = html.escape(kj_website)
        display = ws.replace("https://","").replace("http://","")
        links.append(f'<a href="{ws}" target="_blank" rel="noopener" class="social-link"><span class="ico">WWW</span> {display}</a>')
    if kj_phone:
        links.append(f'<a href="tel:{html.escape(kj_phone)}" class="social-link"><span class="ico">TEL</span> {html.escape(kj_phone_fmt)}</a>')
    social_html = "\n      ".join(links) if links else ""

    # Build venue data for JS + schedule
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_short = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}
    schedule_by_day: dict[str, list[dict]] = {}
    venue_js_data = []

    for v in venues:
        vid = v["id"]
        v_name = html.escape(v["name"])
        v_addr = html.escape(v["address"])
        v_city = html.escape(v["city"])
        v_lat = v["lat"] or 0
        v_lng = v["lng"] or 0
        v_phone = v["phone"] or ""
        v_phone_fmt = _format_phone(v_phone)
        v_website = v["website"] or ""
        v_vibe = html.escape(v["vibe"] or "")
        nights_raw = v["karaoke_nights"] or ""
        nights_list = [n.strip() for n in nights_raw.split(",") if n.strip()]
        nights_display = ", ".join(nights_list) if nights_list else "schedule varies"
        start = html.escape(_format_time(v["start_time"] or ""))
        end = html.escape(_format_time(v["end_time"] or ""))

        venue_js_data.append({
            "id": vid, "name": v_name, "address": v_addr, "city": v_city,
            "lat": v_lat, "lng": v_lng, "phone": v_phone, "phoneFmt": v_phone_fmt,
            "website": v_website, "vibe": v_vibe, "nights": nights_display,
            "start": start, "end": end,
        })

        for night in nights_list:
            if night not in schedule_by_day:
                schedule_by_day[night] = []
            schedule_by_day[night].append({"name": v_name, "vid": vid, "start": start, "end": end})

    # Schedule rows — columnar: day | start | venue
    schedule_rows = []
    for day in day_order:
        gigs = schedule_by_day.get(day, [])
        if gigs:
            for g in gigs:
                schedule_rows.append(
                    f'<tr class="has-gig"><td class="day">{day_short[day]}</td>'
                    f'<td class="time">{g["start"]}</td>'
                    f'<td class="gig" onclick="selectVenue({g["vid"]})">{g["name"]}</td></tr>'
                )
        else:
            schedule_rows.append(
                f'<tr><td class="day dim">{day_short[day]}</td>'
                f'<td class="dim"></td><td class="dim">dark</td></tr>'
            )
    schedule_html = "\n      ".join(schedule_rows)

    # Venue JSON for JS
    venues_json = _json.dumps(venue_js_data)

    # Determine KJ's home city for "Centered in" line
    kj_city = kj["city"] if "city" in kj.keys() and kj["city"] else ""
    # Fallback to most common venue city if KJ has no city set
    if not kj_city and venue_js_data:
        city_counts: dict[str, int] = {}
        for v in venue_js_data:
            c = v["city"]
            if c:
                city_counts[c] = city_counts.get(c, 0) + 1
        kj_city = max(city_counts, key=lambda k: city_counts[k]) if city_counts else ""
    centered_in = f"Centered in {html.escape(kj_city)}, FL" if kj_city else ""

    # Map: use Maps JavaScript API for smooth panTo, fallback to iframe embed
    if venue_js_data:
        center_lat = venue_js_data[0]["lat"]
        center_lng = venue_js_data[0]["lng"]
        has_map = True
    else:
        center_lat = 0
        center_lng = 0
        has_map = False

    # Venue detail cards
    venue_cards = []
    for v in venue_js_data:
        v_links = ""
        v_link_items = []
        if v["website"]:
            v_link_items.append(f'<a href="{html.escape(v["website"])}" target="_blank" rel="noopener">website</a>')
        if v["phone"]:
            v_link_items.append(f'<a href="tel:{html.escape(v["phone"])}">call</a>')
        if v_link_items:
            v_links = f'<div class="v-links">{" &middot; ".join(v_link_items)}</div>'

        venue_cards.append(f"""
        <div class="venue-card" id="venue-{v["id"]}" onclick="selectVenue({v["id"]})">
          <h3>{v["name"]}</h3>
          <p class="v-addr">{v["address"]}, {v["city"]}</p>
          <p class="v-sched">{v["nights"]} &middot; {v["start"]}&ndash;{v["end"]}</p>
          {f'<p class="v-vibe">{v["vibe"]}</p>' if v["vibe"] else ''}
          {v_links}
        </div>""")
    venues_html = "\n".join(venue_cards) if venue_cards else '<p class="empty">No venues listed yet.</p>'

    venues_count = len(venues)
    services_html = f"""
    <div class="service">
      <h3>Live Karaoke Hosting</h3>
      <p>Professional karaoke hosting at {venues_count} venue{'s' if venues_count != 1 else ''}. Full song catalog, sound equipment setup, and crowd engagement.</p>
    </div>
    <div class="service">
      <h3>Song Suggestions</h3>
      <p>Singers get personalized song recommendations matched to their vocal range and style through TheHopper app.</p>
    </div>
    <div class="service">
      <h3>Premium Slots</h3>
      <p>Reserve a preferred singing time slot in the rotation. A community-focused feature that supports the venue and the KJ while keeping the night flowing.</p>
    </div>"""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{biz_esc} &mdash; Karaoke Host | karaokespot.us</title>
  <meta name="description" content="{biz_esc} is a professional karaoke host. View upcoming karaoke nights, venues, and booking information.">
  <style>
    :root {{
      --bg: #1a1a2e;
      --bg2: #22223a;
      --panel: #2a2a48;
      --panel2: #333355;
      --border: #3d3d5c;
      --text: #f0f0f8;
      --dim: #b8b8d0;
      --mute: #7a7a98;
      --pink: #d0669a;
      --cyan: #6fc8b8;
      --yellow: #e0d078;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, system-ui, "Segoe UI", roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }}
    .wrap {{ max-width: 900px; margin: 0 auto; padding: 0 1.5rem 4rem; }}

    /* full-width site header */
    .site-header {{
      background: #111120;
      border-bottom: 1px solid var(--border);
      padding: 0.5rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      position: relative;
      z-index: 10;
    }}
    .brand {{
      font-family: "courier new", courier, monospace;
      font-size: 0.85rem;
      font-weight: 700;
      color: var(--cyan);
      letter-spacing: 0.02em;
      text-transform: lowercase;
    }}
    .brand a {{ color: var(--cyan); text-decoration: none; }}
    .brand-tag {{
      color: var(--mute);
      font-size: 0.72rem;
      text-transform: lowercase;
    }}

    /* hero with blurred background image */
    .hero-bg {{
      position: relative;
      overflow: hidden;
      padding: 3rem 0 2.5rem;
    }}
    .hero-bg::before {{
      content: '';
      position: absolute;
      top: -20px; left: -20px; right: -20px; bottom: -20px;
      background: url('https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=1200&q=80') center/cover no-repeat;
      filter: blur(10px) brightness(0.6) saturate(1.3);
      z-index: 0;
    }}
    .hero-bg::after {{
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background: linear-gradient(to bottom, rgba(26,26,46,0.5) 0%, rgba(26,26,46,0.75) 100%);
      z-index: 1;
    }}
    .hero {{ position: relative; z-index: 2; }}
    .hero-bg .wrap {{ padding-bottom: 0; }}
    .hero h1 {{
      font-size: 2.2rem;
      font-weight: 800;
      margin-bottom: 0.4rem;
      letter-spacing: -0.03em;
      text-align: left;
    }}
    .hero .tagline {{
      color: var(--dim);
      font-size: 1.05rem;
      max-width: 520px;
      margin-bottom: 0.5rem;
      text-align: left;
    }}
    .centered-in {{
      color: var(--cyan);
      font-size: 0.9rem;
      font-weight: 600;
      margin-bottom: 1.2rem;
    }}
    .social-row {{
      display: flex;
      gap: 0.6rem;
      flex-wrap: wrap;
      justify-content: flex-start;
    }}
    .social-link {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 0.35rem 0.8rem;
      color: var(--text);
      text-decoration: none;
      font-size: 0.82rem;
    }}
    .social-link:hover {{ border-color: var(--cyan); }}
    .social-link .ico {{
      background: var(--panel2);
      border-radius: 4px;
      padding: 0.1rem 0.25rem;
      font-size: 0.65rem;
      font-weight: 700;
      color: var(--mute);
    }}

    /* sections */
    .section {{ margin-top: 2.5rem; }}
    .section-title {{
      font-size: 0.78rem;
      font-weight: 700;
      color: var(--mute);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 0.8rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.4rem;
    }}

    /* schedule + map two-column */
    .schedule-map {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
      align-items: start;
    }}
    table.schedule {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
    }}
    table.schedule td {{
      padding: 0.55rem 0.4rem;
      border-bottom: 1px solid var(--bg2);
      vertical-align: top;
    }}
    table.schedule td.day {{
      font-weight: 700;
      color: var(--cyan);
      width: 38px;
      white-space: nowrap;
    }}
    table.schedule td.time {{
      color: var(--mute);
      width: 52px;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }}
    table.schedule td.dim, .dim {{ color: var(--mute); }}
    .gig {{
      cursor: pointer;
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      transition: background 0.15s;
    }}
    .gig:hover {{ background: var(--panel); }}
    .map-container {{
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border);
      height: 272px;
      background: var(--panel);
      position: sticky;
      top: 1rem;
    }}
    .map-container iframe {{ display: block; width: 100%; height: 100%; }}
    .no-map {{ display: flex; align-items: center; justify-content: center; height: 300px; color: var(--mute); font-size: 0.85rem; }}

    /* venue cards */
    #venues-list {{ }}
    .venue-card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.1rem 1.3rem;
      margin-bottom: 0.7rem;
      cursor: pointer;
      transition: border-color 0.15s, box-shadow 0.15s;
    }}
    .venue-card:hover {{ border-color: var(--cyan); }}
    .venue-card.active {{ border-color: var(--cyan); box-shadow: 0 0 0 2px var(--cyan); }}
    .venue-card h3 {{ font-size: 1.15rem; font-weight: 700; margin-bottom: 0.2rem; }}
    .v-addr {{ color: var(--dim); font-size: 0.88rem; }}
    .v-sched {{ color: var(--pink); font-size: 0.85rem; margin-top: 0.3rem; }}
    .v-vibe {{ color: var(--mute); font-size: 0.82rem; margin-top: 0.4rem; }}
    .v-links {{ margin-top: 0.4rem; font-size: 0.82rem; }}
    .v-links a {{ color: var(--cyan); text-decoration: none; }}
    .v-links a:hover {{ text-decoration: underline; }}

    /* services */
    .services-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 0.7rem;
    }}
    .service {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.1rem 1.3rem;
    }}
    .service h3 {{
      font-size: 1rem;
      font-weight: 700;
      color: var(--yellow);
      margin-bottom: 0.3rem;
    }}
    .service p {{
      color: var(--dim);
      font-size: 0.88rem;
    }}

    .empty {{ color: var(--mute); padding: 1rem 0; }}

    /* footer */
    .site-footer {{
      margin-top: 2.5rem;
      padding-top: 1.2rem;
      border-top: 1px solid var(--border);
    }}
    .site-footer p {{
      color: var(--mute);
      font-size: 0.8rem;
      margin-bottom: 0.3rem;
    }}
    .site-footer .powered a {{ color: var(--cyan); text-decoration: none; }}

    /* responsive */
    @media (max-width: 640px) {{
      .schedule-map {{ grid-template-columns: 1fr; }}
      .map-container {{ height: 218px; position: static; }}
      .hero h1 {{ font-size: 1.7rem; }}
      .hero .tagline {{ font-size: 1rem; }}
    }}
  </style>
</head>
<body>

  <div class="site-header">
    <div class="brand"><a href="https://karaokespot.us">karaokespot.us</a></div>
    <div class="brand-tag">karaoke, worldwide</div>
  </div>

  <div class="hero-bg">
    <div class="wrap">
      <div class="hero">
        <h1>{biz_esc}</h1>
        <p class="tagline">{bio}</p>
        {f'<p class="centered-in">{centered_in}</p>' if centered_in else ''}
        <div class="social-row">
        {social_html}
        </div>
      </div>
    </div>
  </div>

  <div class="wrap">
    <div class="section" id="schedule-section">
      <div class="section-title">Schedule & Locations</div>
      <div class="schedule-map">
        <div>
          <table class="schedule">
          {schedule_html}
          </table>
        </div>
        <div class="map-container" id="map-container">
          {f'<div id="map" style="width:100%;height:100%;"></div>' if has_map else '<div class="no-map">map unavailable</div>'}
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Venues</div>
      <div id="venues-list">
      {venues_html}
      </div>
    </div>

    <div class="section">
      <div class="section-title">Services</div>
      <div class="services-grid">
        {services_html}
      </div>
    </div>

    <div class="site-footer">
      <p>{biz_esc} &middot; professional karaoke host</p>
      <p>{f'Contact: {html.escape(kj_phone_fmt)}' if kj_phone else ''}</p>
      <p class="powered">Powered by <a href="https://karaokespot.us">karaokespot.us</a> &middot; Book through <a href="https://thehopper.alchemycreativelounge.com">TheHopper</a></p>
    </div>
  </div>

  <script>
    var venues = {venues_json};
    var mapKey = "{GOOGLE_MAPS_KEY}";
    var centerLat = {center_lat};
    var centerLng = {center_lng};
    var map = null;
    var markers = {{}};

    function initMap() {{
      map = new google.maps.Map(document.getElementById('map'), {{
        center: {{ lat: centerLat, lng: centerLng }},
        zoom: 11,
        streetViewControl: false,
        mapTypeControl: false,
        fullscreenControl: false,
        styles: [{{ elementType: "geometry", stylers: [{{ color: "#1c1c34" }}] }},
                 {{ elementType: "labels.text.stroke", stylers: [{{ color: "#1c1c34" }}] }},
                 {{ elementType: "labels.text.fill", stylers: [{{ color: "#7a7a98" }}] }},
                 {{ featureType: "road", elementType: "geometry", stylers: [{{ color: "#2a2a48" }}] }},
                 {{ featureType: "water", elementType: "geometry", stylers: [{{ color: "#161628" }}] }},
                 {{ featureType: "poi", elementType: "geometry", stylers: [{{ color: "#22223a" }}] }}]
      }});

      // Add markers for all venues
      venues.forEach(function(v) {{
        var marker = new google.maps.Marker({{
          position: {{ lat: v.lat, lng: v.lng }},
          map: map,
          title: v.name
        }});
        marker.addListener('click', function() {{ selectVenue(v.id); }});
        markers[v.id] = marker;
      }});
    }}

    function selectVenue(id) {{
      var v = venues.find(function(x) {{ return x.id === id; }});
      if (!v) return;

      // Highlight card
      document.querySelectorAll('.venue-card').forEach(function(c) {{
        c.classList.remove('active');
      }});
      var card = document.getElementById('venue-' + id);
      if (card) card.classList.add('active');

      // Move selected venue card to top of the list
      if (card) {{
        var list = document.getElementById('venues-list');
        list.insertBefore(card, list.firstChild);
      }}

      // Smooth pan to venue and zoom in
      if (map) {{
        map.panTo({{ lat: v.lat, lng: v.lng }});
        map.setZoom(15);
      }}

      // Scroll to the schedule section so the map is at the top of the screen
      document.getElementById('schedule-section').scrollIntoView({{
        behavior: 'smooth', block: 'start'
      }});
    }}
  </script>
  {(f'<script src="https://maps.googleapis.com/maps/api/js?key={GOOGLE_MAPS_KEY}&callback=initMap" async defer></script>') if has_map else ''}

</body>
</html>"""


@app.get("/kj-sites/{slug}")
def kj_site(slug: str, theme: str | None = None):
    """Serve an auto-generated HTML page for a KJ's business.

    This is the public URL that Stripe's business_profile.url points to.
    It shows the KJ's name, bio, venues, and schedule — enough for Stripe
    to verify the business is real.

    Pass ?theme=light for the light-theme variant.
    """
    with db() as conn:
        kj = conn.execute(
            "SELECT * FROM kjs WHERE site_slug=?", (slug,)
        ).fetchone()
        if not kj:
            raise HTTPException(status_code=404, detail="KJ site not found")
        venues = conn.execute(
            """SELECT v.* FROM venues v
               JOIN kjs k ON v.kj_id = k.id
               WHERE k.site_slug=?""",
            (slug,),
        ).fetchall()

    if theme == "dark":
        html_content = _kj_site_html(kj, venues)
    else:
        html_content = _kj_site_html_light(kj, venues)
    return HTMLResponse(content=html_content, media_type="text/html")


# ---------------------------------------------------------------------------
# API: Device registration (push tokens)
# ---------------------------------------------------------------------------


@app.post(f"{API_PREFIX}/patrons/profile", response_model=PatronProfileResponse)
def save_patron_profile(req: PatronProfileRequest):
    """Create or update a patron's tiny profile (name + phone).

    Called when a patron enters their name/phone in the app, even before
    sending a message. This lets us pre-populate fields and build a profile
    that KJs can use to reply.
    """
    name = req.name.strip()[:120] if req.name else ""
    phone = normalize_phone(req.phone) if req.phone else ""

    if not phone:
        raise HTTPException(status_code=400, detail="Phone is required")

    with db() as conn:
        conn.execute(
            """INSERT INTO patrons (phone, name) VALUES (?, ?)
               ON CONFLICT(phone) DO UPDATE SET name=excluded.name""",
            (phone, name or None),
        )
        row = conn.execute(
            "SELECT * FROM patrons WHERE phone = ?", (phone,)
        ).fetchone()

    return PatronProfileResponse(
        id=row["id"],
        name=row["name"],
        phone=row["phone"],
    )


@app.post(f"{API_PREFIX}/devices/register")
def register_device(req: DeviceRegisterRequest):
    """Register a device push token for notifications."""
    with db() as conn:
        # De-dupe by push_token
        existing = conn.execute(
            "SELECT id FROM devices WHERE push_token=?", (req.push_token,)
        ).fetchone()
        if existing:
            # Update metadata
            conn.execute(
                "UPDATE devices SET platform=?, phone=?, kj_id=?, venue_id=? WHERE id=?",
                (req.platform, req.phone, req.kj_id, req.venue_id, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO devices (push_token, platform, phone, kj_id, venue_id) VALUES (?,?,?,?,?)",
                (req.push_token, req.platform, req.phone, req.kj_id, req.venue_id),
            )
    return {"status": "registered"}


# ---------------------------------------------------------------------------
# API: Admin — approve/reject submissions (protected by simple token)
# ---------------------------------------------------------------------------


ADMIN_TOKEN = os.environ.get("THEHOPPER_ADMIN_TOKEN", "")


# ---------------------------------------------------------------------------
# Subdomain routing — slug.karaokespot.us serves the KJ's business page
# ---------------------------------------------------------------------------


@app.middleware("http")
async def kj_subdomain_middleware(request: Request, call_next):
    """Intercept requests to *.karaokespot.us and serve KJ pages by slug.

    For slug.karaokespot.us, look up the KJ by site_slug and return their
    auto-generated business page. API paths (slug.karaokespot.us/api/...)
    fall through to the normal app.
    """
    host = request.url.hostname or ""
    if (
        host.endswith(f".{KARAOKESPOT_DOMAIN}")
        and host != f"www.{KARAOKESPOT_DOMAIN}"
        and not request.url.path.startswith("/api")
    ):
        slug = host[: -len(f".{KARAOKESPOT_DOMAIN}")].lower()
        if slug:
            kj = None
            venues = []
            with db() as conn:
                kj = conn.execute(
                    "SELECT * FROM kjs WHERE site_slug=?", (slug,)
                ).fetchone()
                if kj:
                    venues = conn.execute(
                        """SELECT v.* FROM venues v
                           JOIN kjs k ON v.kj_id = k.id
                           WHERE k.site_slug=?""",
                        (slug,),
                    ).fetchall()
            if kj:
                theme = request.query_params.get("theme")
                if theme == "dark":
                    return HTMLResponse(
                        content=_kj_site_html(kj, venues),
                        media_type="text/html",
                    )
                return HTMLResponse(
                    content=_kj_site_html_light(kj, venues),
                    media_type="text/html",
                )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Static file serving (production: built frontend)
# ---------------------------------------------------------------------------

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # Serve the SPA index.html for any non-API route (client-side routing)
        if full_path.startswith("api"):
            raise HTTPException(status_code=404)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend not built")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
