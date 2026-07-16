# KaraokeStar MVP

A starter MVP for discovering local karaoke events, queuing, tipping, favorites, and a basic payouts scaffolding using Stripe.

Core features:
- Location-based discovery of local karaoke events
- Join queue and tip KJs to move up the line
- Favorites-based recommendations
- Basic payout scaffolding (Stripe) for monetization
- Admin views for venues and KJs (early MVP)

Tech notes:
- Mobile-first approach (Flutter) with an optional web dashboard
- Local data store for events, queues, tips, and favorites; optional server backend later
- Privacy-first by design: opt-in location sharing and minimal data retention

Next steps:
- Implement a minimal data model (events, KJs, queues, tips, favorites)
- Build a simple UI to discover events, join queue, and tip
- Integrate Stripe in a separate pass
