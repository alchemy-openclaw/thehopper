# TheHopper — Mobile App (React Native + Expo)

Karaoke companion app: find nearby karaoke nights, get song suggestions for your voice, and jump the queue with in-app payments.

## Setup

### Prerequisites
- Node.js 18+ (via nvm)
- Python 3.11+ (for backend)
- Expo CLI: `npm install -g @expo/cli`

### Install
```bash
cd /home/openclaw/projects/thehopper/mobile
npm install
```

### Configure
```bash
# .env already exists with dev config:
# EXPO_PUBLIC_API_URL=http://localhost:8000/api

# For production:
echo "EXPO_PUBLIC_API_URL=https://api.thehopper.app/api" > .env
```

### Run the backend
```bash
cd ../  # thehopper/
./start.sh --build  # serves at http://localhost:8000
```

### Run the app
```bash
cd mobile/
npx expo start
```

- Press `i` for iOS simulator
- Press `a` for Android emulator
- Press `w` for web
- Scan QR code with Expo Go app on your phone

## Features

| Tab | Feature |
|-----|---------|
| **Find** | Location-aware karaoke venue finder, sorted by distance. Stripe checkout for queue jumps. |
| **Songs** | Browse 90+ songs, search, filter by genre. Difficulty badges, vocal range chips. |
| **Suggestions** | Enter your vocal range + favorite artists → get ranked song matches. |
| **Favorites** | Save songs to AsyncStorage. No login required. |

## App Icon

Generated from `assets/app-icon.svg` — a neon microphone with sound waves on dark background.

```bash
# Regenerate all icon sizes:
bash scripts/generate_icons.sh
```

Icons output to `assets/icons/` (15 sizes for iOS, Android, Play Store, web).

## Fastlane (App Store / Play Store deployment)

### Setup
```bash
cd mobile/
gem install fastlane

# iOS: Login to App Store Connect
fastlane fastlane-credentials add --username roscoe@alchemycreativelounge.com

# Android: Create service account key in Google Play Console
# Save as fastlane/google-play-service-account.json
```

### Beta (TestFlight / Internal Testing)
```bash
# iOS
fastlane beta

# Android
fastlane android beta
```

### Production Release
```bash
# iOS
fastlane release

# Android
fastlane android release
```

### Metadata
Store metadata is in `fastlane/metadata/`:
- `en-US/description.txt` — full 4000-char store description
- `en-US/subtitle.txt` — 30-char subtitle
- `en-US/keywords.txt` — search keywords
- `en-US/release_notes.txt` — version release notes
- `fastlane/Fastfile` — build and deploy lanes
- `fastlane/Appfile` — bundle IDs and team config

### Screenshots
```bash
# iOS (requires simulator)
fastlane screenshots

# Android (requires emulator)
fastlane android screenshots
```

See `fastlane/metadata/screenshots/README.txt` for requirements.

## Project Structure

```
mobile/
├── app/                        # expo-router file-based routing
│   ├── _layout.tsx             # Root layout (PrefsProvider, GestureHandler)
│   └── (tabs)/
│       ├── _layout.tsx         # Tab navigator (Find, Songs, Suggestions, Favorites)
│       ├── index.tsx           # Venues + payment modal
│       ├── songs.tsx           # Song browser
│       ├── suggestions.tsx     # Vocal range suggestions
│       └── favorites.tsx       # Saved songs
├── src/
│   ├── api.ts                  # Typed API client
│   ├── types.ts                # TypeScript types
│   ├── theme.ts                # Neon palette + styles
│   ├── prefs.ts                # AsyncStorage hook
│   ├── prefs-context.ts        # Context type
│   ├── prefs-provider.tsx     # Global state provider
│   └── components.tsx          # SongCard, DifficultyBadge, etc.
├── assets/
│   ├── app-icon.svg            # Source SVG for app icon
│   └── icons/                  # Generated PNG icons (all sizes)
├── scripts/
│   └── generate_icons.sh      # Icon generation script
├── fastlane/
│   ├── Fastfile                # Build & deploy lanes
│   ├── Appfile                 # Bundle IDs, team config
│   └── metadata/               # Store descriptions, keywords, etc.
├── app.json                    # Expo config
├── .env                        # API URL config
└── package.json
```

## Tech Stack
- **Expo SDK 56** (latest)
- **React Native** + **TypeScript**
- **expo-router** for navigation
- **expo-location** for geolocation
- **expo-web-browser** for Stripe checkout
- **@react-native-async-storage/async-storage** for local persistence
- Backend: **FastAPI** (Python) — shared with web app, unchanged

## Notes
- The backend CORS is configured for `localhost:5173` (Vite dev). Native iOS/Android apps don't have CORS restrictions, but Expo web dev at `:8081` may need a CORS update or proxy.
- Stripe is in test mode. Set `STRIPE_SECRET_KEY` env var on the backend for production.
- App is seeded with 15 Brevard County, FL venues and 90 popular karaoke songs.
