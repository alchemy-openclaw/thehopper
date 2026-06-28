# 🎤 TheHopper

**Karaoke companion app for Brevard County, FL.**

Find karaoke near you, get song suggestions that fit your voice, and pay to jump the queue — all from your phone, no login required.

## Features

1. **Karaoke Finder** — Uses browser geolocation to show nearby karaoke nights/venues, sorted by distance (haversine). 15 seeded venues across Brevard County (Cocoa Beach, Melbourne, Palm Bay, Titusville, Viera, Satellite Beach, Cape Canaveral, Rockledge, Indian Harbour Beach).
2. **Premium Placement** — Pay the KJ (karaoke host) via Stripe Checkout to jump the queue. Works in test mode out of the box — no Stripe account needed to try it.
3. **Song Suggestions** — Enter your vocal range (bass/baritone/tenor/alto/mezzo/soprano) and favorite artists/genres. The matching algorithm scores 90+ curated karaoke songs by range fit, difficulty sweet-spot, and style match.
4. **No login required** — Anonymous use throughout. Preferences (vocal range, favorites) persist in `localStorage`. Stripe checkout is the only place payment info is ever needed.

## Tech Stack

- **Frontend**: React 18 + TypeScript + Vite (single-page app, mobile-first)
- **Backend**: Python FastAPI (serves API + static files in production)
- **Database**: SQLite (venues, songs, payment records)
- **Payments**: Stripe Checkout (test mode by default)

## Quick Start

```bash
cd /home/openclaw/projects/thehopper
./start.sh
```

Then open **http://localhost:5173** in your browser.

The script will:
1. Create a Python venv and install backend deps
2. Install npm deps for the frontend
3. Start the FastAPI backend on port 8000 (with hot reload)
4. Start the Vite dev server on port 5173 (proxies `/api` → backend)

### Production mode (single server)

```bash
./start.sh --build
```

This builds the frontend to `frontend/dist/` and serves everything from FastAPI on port 8000. Open **http://localhost:8000**.

## Project Structure

```
thehopper/
├── start.sh                  # One-command startup script
├── README.md
├── backend/
│   ├── main.py               # FastAPI app (venues, songs, suggestions, payments)
│   ├── seed_data.py          # 15 venues + 90 songs with range/difficulty metadata
│   ├── requirements.txt
│   ├── venv/                 # Created by start.sh
│   └── thehopper.db          # SQLite DB (created on first run)
└── frontend/
    ├── package.json
    ├── vite.config.ts        # Proxies /api → localhost:8000 in dev
    ├── tsconfig.json
    ├── index.html
    ├── public/
    │   └── mic.svg           # Favicon
    └── src/
        ├── main.tsx          # React entry
        ├── App.tsx           # Tab navigation + shell
        ├── api.ts            # Typed API client
        ├── prefs.ts          # localStorage prefs hook + geolocation helper
        ├── prefs-types.ts    # Shared prefs tuple type
        ├── types.ts          # API types + difficulty labels
        ├── styles.css        # Neon nightlife theme
        ├── components.tsx    # SongCard, DifficultyBadge, Loading, EmptyState
        └── pages/
            ├── VenuesPage.tsx        # Feature 1: Karaoke finder + Stripe checkout
            ├── SongsPage.tsx         # Songbook browser with search/filter/favorite
            ├── SuggestionsPage.tsx   # Feature 3: Vocal range → song matches
            └── FavoritesPage.tsx      # Saved songs (localStorage)
```

## API Endpoints

| Method | Path                          | Description                                          |
|--------|-------------------------------|------------------------------------------------------|
| GET    | `/api/health`                 | Health check                                         |
| GET    | `/api/config`                 | Stripe publishable key + configured flag            |
| GET    | `/api/venues`                 | List venues (optional `?lat=&lng=` for distance sort, `?city=` filter) |
| GET    | `/api/venues/{id}`            | Single venue                                         |
| GET    | `/api/songs`                  | List songs (optional `?search=&genre=&limit=`)       |
| GET    | `/api/songs/ranges`           | Valid vocal ranges + descriptions                    |
| POST   | `/api/song-suggestions`       | Body: `{vocal_range, favorite_artists, favorite_genres, limit}` → ranked suggestions |
| POST   | `/api/create-payment-session` | Body: `{venue_id, singer_name, song_request}` → Stripe checkout URL |
| POST   | `/api/stripe-webhook`         | Stripe webhook receiver (marks payments paid)        |
| GET    | `/api/payment-test`           | Test-mode success endpoint (when Stripe not configured) |

## Song Matching Algorithm

The `score_song()` function in `backend/main.py` scores each song 0–100:

- **Range fit (60%)** — Full 60 points if the user's vocal range is in the song's `range_fit` list. Partial credit (scaled by proximity on the bass→soprano ladder) for adjacent ranges.
- **Difficulty sweet-spot (25%)** — Songs at difficulty 2–3 score best (comfortable challenge). Difficulty 1 is too easy/boring, 5 is a likely trainwreck.
- **Artist match (10%)** — Boost if a favorite artist matches (substring, case-insensitive).
- **Genre match (5%)** — Boost if a favorite genre matches.

Results are sorted descending by score; the top N are returned with a human-readable reason string.

## Stripe Configuration

The app runs in **test mode** by default — no Stripe account required. The `create-payment-session` endpoint detects the placeholder secret key and redirects to a local test success page instead of real Stripe Checkout.

To enable real Stripe payments (still in test mode, no real charges):

```bash
export STRIPE_SECRET_KEY="sk_test_YOUR_TEST_SECRET_KEY"
export STRIPE_PUBLISHABLE_KEY="pk_test_YOUR_TEST_PUBLISHABLE_KEY"
./start.sh
```

Get test keys from the Stripe Dashboard → Developers → API keys. Use card number `4242 4242 4242 4242` with any future expiry and CVC for test payments.

## Vocal Ranges

| Range    | Description              |
|----------|--------------------------|
| Bass     | Low & deep (E2–E4)       |
| Baritone | Low-mid (A2–A4)          |
| Tenor    | Mid-high (C3–C5)         |
| Alto     | Low female (F3–F5)       |
| Mezzo    | Mid female (A3–A5)       |
| Soprano  | High female (C4–C6)      |

## Design

- **Dark nightlife aesthetic** — deep purple-black background with neon pink/purple/cyan accents
- **Mobile-first** — large 52px touch targets, 16px+ font sizes (no iOS zoom), bottom-sheet modals
- **Low friction** — 3 taps max to do anything. No login. No setup. Open the app and sing.
- **Fun** — emoji icons, gradient buttons, glow shadows, slide-up animations

## Seed Data

- **15 venues** across Brevard County, FL with real-ish coordinates, karaoke nights, KJ names, phone numbers, and vibes
- **90 songs** (after de-duplication from the source list of 101) spanning Rock, Pop, Soul, and Country — each with difficulty (1–5), range fit, and curator notes

## License

Made for Roscoe (MikeM). Have fun. Sing loud. 🎤
