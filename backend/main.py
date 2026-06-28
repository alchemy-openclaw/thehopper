"""TheHopper — Karaoke companion app backend.

FastAPI app providing:
  - Venues (Brevard County, FL) sorted by geolocation
  - Songs catalog (50+ karaoke songs with range/difficulty metadata)
  - Song suggestions matching user vocal range + favorite artists/genres
  - KJ messaging (singers can leave a message for the karaoke host)
  - Stripe Checkout for reserving a "premium slot" (preferred singing time
    set by the KJ — a community-focused support mechanism, not a queue jump)

Run with: uvicorn main:app --reload
"""

from __future__ import annotations

import math
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import stripe
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from seed_data import SONGS, VENUES

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
            """
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
        "stripe_configured": not STRIPE_SECRET_KEY.startswith("sk_tes...T_ME"),
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
# API: Stripe checkout for premium slot reservation
# ---------------------------------------------------------------------------


@app.post(f"{API_PREFIX}/create-payment-session", response_model=PaymentResponse)
def create_payment_session(req: PaymentRequest):
    """Create a Stripe Checkout session for reserving a premium slot.

    A "premium slot" is a preferred singing time (default 3rd position in the
    rotation) that the KJ has agreed to offer as a way for singers to support
    the show. It is *not* a queue jump — the KJ confirms the final position.
    The price is KJ-configurable per venue (`premium_slot_price`).
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
    if STRIPE_SECRET_KEY.startswith("sk_tes...T_ME"):
        return PaymentResponse(
            checkout_url=f"/api/payment-test?payment_id={payment_id}&venue={venue['name']}",
            session_id=f"test_session_{payment_id}",
        )

    # Real Stripe Checkout session
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"Premium Slot Reservation — {venue['name']}",
                            "description": (
                                f"Support {kj_name} and secure a preferred singing time "
                                f"(~{slot_pos}{_ordinal(slot_pos)} slot)"
                                + (f". Song: {req.song_request}" if req.song_request else "")
                            ),
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
async def stripe_webhook(request: Any) -> dict[str, str]:
    """Webhook for Stripe to confirm payments. (Best-effort in test mode.)"""
    import json
    from fastapi import Request

    # Note: in production you'd verify the signature. For local dev we accept
    # the payload as-is and mark the matching payment paid.
    body = await request.body()
    try:
        event = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if event.get("type") == "checkout.session.completed":
        sess = event["data"]["object"]
        pid = sess.get("metadata", {}).get("payment_id")
        if pid:
            with db() as conn:
                conn.execute(
                    "UPDATE payments SET status='paid', paid_at=datetime('now') WHERE id=?",
                    (pid,),
                )
    return {"received": "ok"}


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
