import { useEffect, useState } from 'react';
import type { AppConfig, Venue } from '../types';
import { api } from '../api';
import { getGeolocation } from '../prefs';
import { EmptyState, Loading } from '../components';

interface Props {
  config: AppConfig | null;
}

export default function VenuesPage({ config }: Props) {
  const [venues, setVenues] = useState<Venue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [city, setCity] = useState('');
  const [hasLocation, setHasLocation] = useState(false);
  const [payVenue, setPayVenue] = useState<Venue | null>(null);

  const loadVenues = async (lat?: number, lng?: number, cityFilter?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getVenues(lat, lng, cityFilter);
      setVenues(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load venues');
    } finally {
      setLoading(false);
    }
  };

  // initial load: all venues, no location
  useEffect(() => {
    loadVenues();
  }, []);

  const handleLocate = async () => {
    setError(null);
    try {
      const { lat, lng } = await getGeolocation();
      setHasLocation(true);
      setCity('');
      await loadVenues(lat, lng);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not get location');
    }
  };

  const handleCitySearch = (e: React.FormEvent) => {
    e.preventDefault();
    setHasLocation(false);
    loadVenues(undefined, undefined, city.trim() || undefined);
  };

  const handlePay = async (venue: Venue, singerName: string, songRequest: string) => {
    try {
      const res = await api.createPaymentSession(
        venue.id,
        singerName || 'Anonymous Singer',
        songRequest,
      );
      // Redirect to Stripe checkout (or test-mode URL)
      window.location.href = res.checkout_url;
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Payment session could not be created',
      );
    }
  };

  return (
    <div>
      <div className="card" style={{ marginBottom: 12 }}>
        <button className="btn" onClick={handleLocate} disabled={loading}>
          📍 Find karaoke near me
        </button>
        <form
          onSubmit={handleCitySearch}
          style={{ display: 'flex', gap: 8, marginTop: 10 }}
        >
          <input
            className="input"
            placeholder="or search by city…"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            aria-label="City search"
          />
          <button
            className="btn secondary"
            type="submit"
            style={{ width: 'auto', padding: '0 18px' }}
          >
            Go
          </button>
        </form>
        {hasLocation && (
          <div className="banner info" style={{ marginTop: 10, marginBottom: 0 }}>
            Sorted by distance from your location.
          </div>
        )}
      </div>

      {error && <div className="banner warn">⚠️ {error}</div>}

      {loading ? (
        <Loading label="Finding karaoke…" />
      ) : venues.length === 0 ? (
        <EmptyState icon="🗺️" message="No venues found. Try another city." />
      ) : (
        venues.map((v) => (
          <VenueCard
            key={v.id}
            venue={v}
            onPay={() => setPayVenue(v)}
            stripeConfigured={config?.stripe_configured ?? false}
          />
        ))
      )}

      {payVenue && (
        <PaymentModal
          venue={payVenue}
          stripeConfigured={config?.stripe_configured ?? false}
          onClose={() => setPayVenue(null)}
          onConfirm={handlePay}
        />
      )}
    </div>
  );
}

function VenueCard({
  venue,
  onPay,
  stripeConfigured,
}: {
  venue: Venue;
  onPay: () => void;
  stripeConfigured: boolean;
}) {
  return (
    <div className="venue">
      <div className="venue-header">
        <div>
          <div className="venue-name">{venue.name}</div>
          <div className="venue-city">{venue.city}</div>
        </div>
        {venue.distance_miles != null && (
          <span className="venue-dist">{venue.distance_miles} mi</span>
        )}
      </div>

      <div className="venue-meta">
        {venue.karaoke_nights.map((n) => (
          <span key={n} className="meta-pill nights">
            {n}
          </span>
        ))}
        <span className="meta-pill">
          🕘 {venue.start_time}–{venue.end_time}
        </span>
        {venue.kj_name && (
          <span className="meta-pill">KJ: {venue.kj_name}</span>
        )}
      </div>

      {venue.vibe && <div className="venue-vibe">{venue.vibe}</div>}

      <div className="venue-actions">
        <button className="btn" onClick={onPay}>
          ⏭️ Jump Queue · ${venue.price_jump_queue.toFixed(2)}
        </button>
      </div>

      <div
        style={{
          marginTop: 10,
          display: 'flex',
          gap: 12,
          fontSize: 12,
          color: 'var(--text-mute)',
          flexWrap: 'wrap',
        }}
      >
        {venue.phone && <span>📞 {venue.phone}</span>}
        {venue.website && (
          <a
            href={venue.website}
            target="_blank"
            rel="noreferrer"
            style={{ color: 'var(--cyan)' }}
          >
            🌐 website
          </a>
        )}
        {!stripeConfigured && (
          <span style={{ color: 'var(--yellow)' }}>· test mode (no real charge)</span>
        )}
      </div>
    </div>
  );
}

function PaymentModal({
  venue,
  stripeConfigured,
  onClose,
  onConfirm,
}: {
  venue: Venue;
  stripeConfigured: boolean;
  onClose: () => void;
  onConfirm: (venue: Venue, singerName: string, songRequest: string) => void;
}) {
  const [singer, setSinger] = useState('');
  const [song, setSong] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    await onConfirm(venue, singer, song);
    setSubmitting(false);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <h3>⏭️ Jump the Queue</h3>
        <div className="modal-sub">
          {venue.name} · KJ: {venue.kj_name || 'TBA'}
        </div>
        <div className="price-display">
          ${venue.price_jump_queue.toFixed(2)}{' '}
          <small>to sing next</small>
        </div>

        {!stripeConfigured && (
          <div className="banner info" style={{ marginBottom: 12 }}>
            ⚠️ Stripe not configured — you'll be redirected to a test success page.
          </div>
        )}

        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="singer">Your name (optional)</label>
            <input
              id="singer"
              className="input"
              placeholder="Anonymous Singer"
              value={singer}
              onChange={(e) => setSinger(e.target.value)}
              maxLength={60}
            />
          </div>
          <div className="field">
            <label htmlFor="song">Song request (optional)</label>
            <input
              id="song"
              className="input"
              placeholder="e.g. Don't Stop Believin' — Journey"
              value={song}
              onChange={(e) => setSong(e.target.value)}
              maxLength={120}
            />
          </div>
          <button className="btn" type="submit" disabled={submitting}>
            {submitting ? 'Creating checkout…' : `Pay $${venue.price_jump_queue.toFixed(2)} & jump queue`}
          </button>
        </form>
      </div>
    </div>
  );
}
