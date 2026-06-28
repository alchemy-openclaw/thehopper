import { useEffect, useState } from 'react';
import type { AppConfig } from './types';
import { api } from './api';
import { usePrefs } from './prefs';
import type { PrefsTuple } from './prefs-types';
import VenuesPage from './pages/VenuesPage';
import SongsPage from './pages/SongsPage';
import SuggestionsPage from './pages/SuggestionsPage';
import FavoritesPage from './pages/FavoritesPage';

type Tab = 'venues' | 'songs' | 'suggest' | 'fav';

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'venues', label: 'Find', icon: '📍' },
  { id: 'songs', label: 'Songs', icon: '🎵' },
  { id: 'suggest', label: 'For You', icon: '✨' },
  { id: 'fav', label: 'Saved', icon: '⭐' },
];

export default function App() {
  const [tab, setTab] = useState<Tab>('venues');
  const [config, setConfig] = useState<AppConfig | null>(null);
  const prefs: PrefsTuple = usePrefs();
  const [paymentStatus, setPaymentStatus] = useState<string | null>(null);

  // Load app config (publishable key, stripe configured?)
  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  // Check URL for payment success/cancel params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const p = params.get('payment');
    if (p === 'success') setPaymentStatus('success');
    else if (p === 'cancelled') setPaymentStatus('cancelled');
    if (p) {
      // clean the URL
      window.history.replaceState({}, '', window.location.pathname);
      const t = setTimeout(() => setPaymentStatus(null), 6000);
      return () => clearTimeout(t);
    }
  }, []);

  return (
    <div className="app">
      <header className="header">
        <div className="logo" aria-hidden="true">
          🎤
        </div>
        <div>
          <h1>TheHopper</h1>
          <div className="tag">Brevard karaoke companion</div>
        </div>
      </header>

      {paymentStatus === 'success' && (
        <div className="banner ok">🎉 You're up next! The KJ has been notified.</div>
      )}
      {paymentStatus === 'cancelled' && (
        <div className="banner warn">Payment cancelled — no charge.</div>
      )}

      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
            aria-pressed={tab === t.id}
          >
            <span className="tab-icon" aria-hidden="true">
              {t.icon}
            </span>
            <span>{t.label}</span>
          </button>
        ))}
      </nav>

      <main style={{ flex: 1, paddingTop: 12 }}>
        {tab === 'venues' && <VenuesPage config={config} />}
        {tab === 'songs' && <SongsPage prefs={prefs} />}
        {tab === 'suggest' && <SuggestionsPage prefs={prefs} />}
        {tab === 'fav' && <FavoritesPage prefs={prefs} />}
      </main>

      <footer className="footer">
        TheHopper · Made for Brevard County karaoke ·{' '}
        <a href="https://stripe.com/docs/testing" target="_blank" rel="noreferrer">
          test mode
        </a>
      </footer>
    </div>
  );
}
