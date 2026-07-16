# KaraokeStar (working title)

Concept: A location-based social app for local karaoke events. Users discover nearby karaoke sessions, join queues, and optionally tip the current host (KJ) to move their name up the line. The app collects user favorites and suggests KJs/events based on shared tastes. A Stripe-based marketplace/payout flow can be added for KJs who sign up to monetize their performances. The MVP will focus on discovery, queue/tipping, favorites, and basic payout scaffolding.

Key ideas:
- Location-driven discovery of nearby karaoke events
- Queue participation with tipping to influence position
- Subject approval for descriptors (for profile cards or event preferences)
- Favorites-driven discovery: suggest KJs and events with shared favorites
- Optional Stripe-based payout to KJs (merchant accounts) in later phases

Planned platform targets:
- Mobile-first (Flutter) with optional web dashboard for venues/KJs
- Backend data store for events, queues, KJs, tips, and payouts
- Privacy-first: opt-in location and minimal data retention

Why this matters:
- Karaoke is social, local, and often disorganized. This app aligns incentives to help users connect with KJs they enjoy and support venues and hosts via tips and payouts.
