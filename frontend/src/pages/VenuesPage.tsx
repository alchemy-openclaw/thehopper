import { useEffect, useState } from 'react';
import type { AppConfig, KJMessageResponse, Venue } from '../types';
import { ordinal } from '../types';
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
  const [selectedVenue, setSelectedVenue] = useState<Venue | null>(null);

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

  // Venue detail view
  if (selectedVenue) {
    return (
      <VenueDetail
        venue={selectedVenue}
        config={config}
        onBack={() => setSelectedVenue(null)}
        onError={setError}
      />
    );
  }

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
          <VenueCard key={v.id} venue={v} onOpen={() => setSelectedVenue(v)} />
        ))
      )}
    </div>
  );
}

function VenueCard({
  venue,
  onOpen,
}: {
  venue: Venue;
  onOpen: () => void;
}) {
  return (
    <button
      className="venue venue-tap"
      onClick={onOpen}
      aria-label={`View details for ${venue.name}`}
      style={{ textAlign: 'left', cursor: 'pointer', width: '100%' }}
    >
      <div className="venue-header">
        <div>
          <div className="venue-name">{venue.name}</div>
          <div className="venue-city">
            {venue.address.split(',').slice(-2).join(',').trim() || venue.city}
          </div>
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
          <span className="meta-pill kj-pill">🎤 {venue.kj_name}</span>
        )}
      </div>

      <div className="venue-tap-hint">Tap for details & reserve →</div>
    </button>
  );
}

function VenueDetail({
  venue,
  config,
  onBack,
  onError,
}: {
  venue: Venue;
  config: AppConfig | null;
  onBack: () => void;
  onError: (msg: string) => void;
}) {
  const [showMessage, setShowMessage] = useState(false);
  const [showReserve, setShowReserve] = useState(false);

  const stripeConfigured = config?.stripe_configured ?? false;
  const kjName = venue.kj_name || 'the KJ';
  const slotPos = venue.premium_slot_position ?? 3;
  const slotPrice = venue.premium_slot_price ?? venue.price_jump_queue ?? 5.0;

  // KJ avatar: deterministic emoji from kj_name
  const kjAvatar = kjEmoji(venue.kj_name);

  return (
    <div>
      <button className="btn ghost back-btn" onClick={onBack}>
        ← Back to venues
      </button>

      <div className="venue venue-detail">
        <div className="venue-header">
          <div>
            <div className="venue-name">{venue.name}</div>
            <div className="venue-city">{venue.address}</div>
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
        </div>

        {venue.vibe && <div className="venue-vibe">{venue.vibe}</div>}

        {/* KJ card */}
        <div className="kj-card">
          <div className="kj-avatar" aria-hidden="true">
            {kjAvatar}
          </div>
          <div className="kj-info">
            <div className="kj-label">Your karaoke host</div>
            <div className="kj-name">{kjName}</div>
          </div>
        </div>

        {/* Community actions */}
        <div className="venue-actions">
          <button
            className="btn cyan"
            onClick={() => {
              setShowMessage(true);
              setShowReserve(false);
            }}
          >
            💬 Message KJ
          </button>
          <button
            className="btn"
            onClick={() => {
              setShowReserve(true);
              setShowMessage(false);
            }}
          >
            🎤 Reserve a premium slot
          </button>
        </div>

        <div className="premium-blurb">
          Support {kjName} and secure a preferred singing time (~{ordinal(slotPos)}{' '}
          slot). {kjName} will confirm your position.
        </div>

        {!stripeConfigured && showReserve && (
          <div className="banner info" style={{ marginTop: 10 }}>
            ⚠️ Stripe not configured — you'll be redirected to a test success page.
          </div>
        )}

        <div className="venue-contact">
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
        </div>
      </div>

      {showMessage && (
        <MessageKJForm
          venue={venue}
          onClose={() => setShowMessage(false)}
          onError={onError}
        />
      )}

      {showReserve && (
        <ReserveSlotModal
          venue={venue}
          stripeConfigured={stripeConfigured}
          onClose={() => setShowReserve(false)}
          onError={onError}
        />
      )}
    </div>
  );
}

function MessageKJForm({
  venue,
  onClose,
  onError,
}: {
  venue: Venue;
  onClose: () => void;
  onError: (msg: string) => void;
}) {
  const [singer, setSinger] = useState('');
  const [song, setSong] = useState('');
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState<KJMessageResponse | null>(null);

  const kjName = venue.kj_name || 'the KJ';

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) {
      onError('Please write a message before sending.');
      return;
    }
    setSubmitting(true);
    try {
      const res = await api.sendKJMessage(
        venue.id,
        singer || 'Anonymous Singer',
        message,
        song,
      );
      setSent(res);
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not send message');
    } finally {
      setSubmitting(false);
    }
  };

  if (sent) {
    return (
      <div className="card" style={{ marginTop: 12 }}>
        <div className="banner ok" style={{ marginBottom: 10 }}>
          ✉️ Message sent to {kjName}!
        </div>
        <p className="confirm-text">
          Thanks{sent.singer_name && sent.singer_name !== 'Anonymous Singer' ? `, ${sent.singer_name}` : ''}! Your message has been passed along to {kjName}. They'll see it next time they're at the show.
        </p>
        <button className="btn secondary" onClick={onClose}>
          Done
        </button>
      </div>
    );
  }

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="section-title" style={{ marginTop: 0 }}>
        Message {kjName}
      </div>
      <p className="form-blurb">
        Say hi, ask about the songbook, or request a tune for next time.
      </p>
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="msg-singer">Your name (optional)</label>
          <input
            id="msg-singer"
            className="input"
            placeholder="Anonymous Singer"
            value={singer}
            onChange={(e) => setSinger(e.target.value)}
            maxLength={60}
          />
        </div>
        <div className="field">
          <label htmlFor="msg-song">Song request (optional)</label>
          <input
            id="msg-song"
            className="input"
            placeholder="e.g. Don't Stop Believin' — Journey"
            value={song}
            onChange={(e) => setSong(e.target.value)}
            maxLength={120}
          />
        </div>
        <div className="field">
          <label htmlFor="msg-body">Your message</label>
          <textarea
            id="msg-body"
            className="input"
            placeholder={`Hi ${venue.kj_name || 'KJ'}! …`}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={500}
            required
          />
        </div>
        <div className="venue-actions">
          <button className="btn secondary" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="btn cyan" type="submit" disabled={submitting}>
            {submitting ? 'Sending…' : 'Send message'}
          </button>
        </div>
      </form>
    </div>
  );
}

function ReserveSlotModal({
  venue,
  stripeConfigured,
  onClose,
  onError,
}: {
  venue: Venue;
  stripeConfigured: boolean;
  onClose: () => void;
  onError: (msg: string) => void;
}) {
  const [singer, setSinger] = useState('');
  const [song, setSong] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const kjName = venue.kj_name || 'the KJ';
  const slotPos = venue.premium_slot_position ?? 3;
  const slotPrice = venue.premium_slot_price ?? venue.price_jump_queue ?? 5.0;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await api.createPaymentSession(
        venue.id,
        singer || 'Anonymous Singer',
        song,
      );
      // Redirect to Stripe checkout (or test-mode URL)
      window.location.href = res.checkout_url;
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not start reservation');
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <h3>🎤 Reserve a premium slot</h3>
        <div className="modal-sub">
          {venue.name} · KJ: {kjName}
        </div>

        <div className="reserve-info">
          <div className="price-display">
            ${slotPrice.toFixed(2)}{' '}
            <small>to support {kjName}</small>
          </div>
          <p className="reserve-blurb">
            Secure a preferred singing time — roughly the{' '}
            <strong>{ordinal(slotPos)} slot</strong> in the rotation. {kjName} will
            confirm your final position. This is a reservation and a way to support
            your local KJ, not a queue jump.
          </p>
        </div>

        {!stripeConfigured && (
          <div className="banner info" style={{ marginBottom: 12 }}>
            ⚠️ Stripe not configured — you'll be redirected to a test success page.
          </div>
        )}

        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="res-singer">Your name (optional)</label>
            <input
              id="res-singer"
              className="input"
              placeholder="Anonymous Singer"
              value={singer}
              onChange={(e) => setSinger(e.target.value)}
              maxLength={60}
            />
          </div>
          <div className="field">
            <label htmlFor="res-song">Song request (optional)</label>
            <input
              id="res-song"
              className="input"
              placeholder="e.g. Don't Stop Believin' — Journey"
              value={song}
              onChange={(e) => setSong(e.target.value)}
              maxLength={120}
            />
          </div>
          <div className="venue-actions">
            <button className="btn secondary" type="button" onClick={onClose}>
              Cancel
            </button>
            <button className="btn" type="submit" disabled={submitting}>
              {submitting
                ? 'Starting checkout…'
                : `Reserve · $${slotPrice.toFixed(2)}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** Pick a deterministic emoji avatar for a KJ based on their name. */
function kjEmoji(kjName: string | null): string {
  const emojis = ['🎤', '🎧', '🎶', '🎙️', '⭐', '🌟', '🎵', '🦜', '🦊', '🐙'];
  if (!kjName) return '🎤';
  let h = 0;
  for (let i = 0; i < kjName.length; i++) {
    h = (h * 31 + kjName.charCodeAt(i)) >>> 0;
  }
  return emojis[h % emojis.length];
}
