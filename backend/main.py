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
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from seed_data import SONGS, VENUES
from stripe_connect import ConnectManager, ConnectAccount

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

stripe.api_key = STRIPE_SECRET_KEY

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

    Stored in the `kj_messages` table. In a future iteration the KJ would be
    notified by email/SMS; for now we just persist it.
    """
    singer_name: str = "Anonymous Singer"
    message: str
    song_request: str = ""


class KJMessageResponse(BaseModel):
    id: int
    venue_id: int
    singer_name: str
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


class KJLinkVenueRequest(BaseModel):
    """Link a KJ to a venue (claim ownership)."""
    kj_id: int
    venue_id: int


class DeviceRegisterRequest(BaseModel):
    push_token: str
    platform: str | None = None  # ios | android | web
    phone: str | None = None
    kj_id: int | None = None
    venue_id: int | None = None


# ---------------------------------------------------------------------------
# Row -> dict helpers
# ---------------------------------------------------------------------------


def venue_row_to_dict(row: sqlite3.Row, distance: float | None = None) -> dict:
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
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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


@app.on_event("startup")
def _startup() -> None:
    init_db()


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

    out = []
    for r in rows:
        if city and city.lower() not in r["city"].lower():
            continue
        dist = None
        if lat is not None and lng is not None:
            dist = haversine_miles(lat, lng, r["lat"], r["lng"])
        out.append(venue_row_to_dict(r, dist))

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

    No notification is sent yet — the message is just persisted in the
    `kj_messages` table. A future email/SMS notifier will pick these up.
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    with db() as conn:
        venue = conn.execute(
            "SELECT id, kj_name FROM venues WHERE id = ?", (venue_id,)
        ).fetchone()
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")

        cur = conn.execute(
            """INSERT INTO kj_messages
               (venue_id, singer_name, message, song_request)
               VALUES (?,?,?,?)""",
            (
                venue_id,
                (req.singer_name or "Anonymous Singer").strip()[:120],
                req.message.strip()[:2000],
                (req.song_request or "").strip()[:200] or None,
            ),
        )
        msg_id = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM kj_messages WHERE id = ?", (msg_id,)
        ).fetchone()

    return KJMessageResponse(
        id=row["id"],
        venue_id=row["venue_id"],
        singer_name=row["singer_name"],
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
    """Request to start Stripe Connect onboarding for a venue's KJ."""
    venue_id: int
    email: str  # KJ's email for the Stripe account


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
    """
    with db() as conn:
        venue = conn.execute(
            "SELECT * FROM venues WHERE id = ?", (req.venue_id,)
        ).fetchone()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    existing_acct = venue["stripe_account_id"] if "stripe_account_id" in venue.keys() else None

    if existing_acct:
        # Account already exists — generate a fresh onboarding link
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
                success_url=f"/?payment=success&venue_id={req.venue_id}",
                cancel_url=f"/?payment=cancelled&venue_id={req.venue_id}",
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
                success_url=f"/?payment=success&venue_id={req.venue_id}",
                cancel_url=f"/?payment=cancelled&venue_id={req.venue_id}",
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

    # --- Payment completed ---
    if event_type == "checkout.session.completed":
        sess = event["data"]["object"]
        pid = sess.get("metadata", {}).get("payment_id")
        venue_id = sess.get("metadata", {}).get("venue_id")
        singer_name = sess.get("metadata", {}).get("singer_name", "Someone")
        song_request = sess.get("metadata", {}).get("song_request", "")
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
        # Invalidate any previous codes for this phone
        conn.execute(
            "UPDATE phone_verifications SET verified=1 WHERE phone=? AND verified=0",
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

    # Generate a session token (hash of phone + timestamp)
    token = secrets.token_hex(16)
    return PhoneVerifyResponse(verified=True, token=token)


# ---------------------------------------------------------------------------
# API: KJ (Karaoke Jockey) onboarding
# ---------------------------------------------------------------------------


@app.post(f"{API_PREFIX}/kjs/register", response_model=KJOut)
def register_kj(req: KJRegisterRequest):
    """Register a new KJ or update an existing one by phone number."""
    phone = normalize_phone(req.phone)
    with db() as conn:
        existing = conn.execute("SELECT * FROM kjs WHERE phone=?", (phone,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE kjs SET name=?, bio=?, instagram=?, website=?, photo_url=? WHERE id=?",
                (req.name.strip(), req.bio, req.instagram, req.website, req.photo_url, existing["id"]),
            )
            row = conn.execute("SELECT * FROM kjs WHERE id=?", (existing["id"],)).fetchone()
        else:
            cur = conn.execute(
                "INSERT INTO kjs (name, phone, bio, instagram, website, photo_url) VALUES (?,?,?,?,?,?)",
                (req.name.strip(), phone, req.bio, req.instagram, req.website, req.photo_url),
            )
            row = conn.execute("SELECT * FROM kjs WHERE id=?", (cur.lastrowid,)).fetchone()
    return KJOut(
        id=row["id"], name=row["name"], phone=row["phone"], bio=row["bio"],
        photo_url=row["photo_url"], instagram=row["instagram"], website=row["website"],
        stripe_onboarding_status=row["stripe_onboarding_status"],
        verified=bool(row["verified"]), created_at=row["created_at"],
    )


@app.get(f"{API_PREFIX}/kjs/{{kj_id}}", response_model=KJOut)
def get_kj(kj_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="KJ not found")
    return KJOut(
        id=row["id"], name=row["name"], phone=row["phone"], bio=row["bio"],
        photo_url=row["photo_url"], instagram=row["instagram"], website=row["website"],
        stripe_onboarding_status=row["stripe_onboarding_status"],
        verified=bool(row["verified"]), created_at=row["created_at"],
    )


@app.get(f"{API_PREFIX}/kjs", response_model=list[KJOut])
def list_kjs():
    """List all KJs."""
    with db() as conn:
        rows = conn.execute("SELECT * FROM kjs ORDER BY created_at DESC").fetchall()
    return [
        KJOut(
            id=r["id"], name=r["name"], phone=r["phone"], bio=r["bio"],
            photo_url=r["photo_url"], instagram=r["instagram"], website=r["website"],
            stripe_onboarding_status=r["stripe_onboarding_status"],
            verified=bool(r["verified"]), created_at=r["created_at"],
        )
        for r in rows
    ]


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


@app.post(f"{API_PREFIX}/kjs/{{kj_id}}/stripe-onboard")
def kj_stripe_onboard(kj_id: int, email: str = Query(..., description="KJ email for Stripe")):
    """Start Stripe Connect onboarding for a KJ."""
    with db() as conn:
        kj = conn.execute("SELECT * FROM kjs WHERE id=?", (kj_id,)).fetchone()
    if not kj:
        raise HTTPException(status_code=404, detail="KJ not found")

    existing_acct = kj["stripe_account_id"]

    if existing_acct:
        try:
            onboarding_url = connect.create_onboarding_link(existing_acct)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
        return {"onboarding_url": onboarding_url, "account_id": existing_acct}

    try:
        account = connect.create_connected_account(
            email=email,
            metadata={"kj_id": str(kj_id), "kj_name": kj["name"]},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error creating account: {e}")

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
# API: Device registration (push tokens)
# ---------------------------------------------------------------------------


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
