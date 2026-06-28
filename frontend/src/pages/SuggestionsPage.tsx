import { useEffect, useState } from 'react';
import type { Song, Suggestion, VocalRange } from '../types';
import { api } from '../api';
import { EmptyState, Loading, SongCard } from '../components';
import type { PrefsTuple } from '../prefs-types';

interface Props {
  prefs: PrefsTuple;
}

export default function SuggestionsPage({ prefs }: Props) {
  const [ranges, setRanges] = useState<VocalRange[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const [prefsState, setPrefsState] = prefs;
  const {
    vocal_range,
    favorite_artists,
    favorite_genres,
    favorites,
  } = prefsState;

  useEffect(() => {
    api
      .getRanges()
      .then((r) => setRanges(r.ranges))
      .catch(() => setRanges([]));
  }, []);

  const setField = (field: keyof typeof prefsState, value: string) => {
    setPrefsState((p) => ({ ...p, [field]: value }));
  };

  const toggleFav = (id: number) => {
    setPrefsState((p) => {
      const has = p.favorites.includes(id);
      return {
        ...p,
        favorites: has
          ? p.favorites.filter((x: number) => x !== id)
          : [...p.favorites, id],
      };
    });
  };

  const handleSuggest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!vocal_range) {
      setError('Pick your vocal range first.');
      return;
    }
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const artists = favorite_artists
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const genres = favorite_genres
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const data = await api.getSuggestions(vocal_range, artists, genres, 15);
      setSuggestions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to get suggestions');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="card">
        <form onSubmit={handleSuggest}>
          <div className="field">
            <label>Your vocal range</label>
            <div className="chips">
              {ranges.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  className={`chip ${vocal_range === r.value ? 'active' : ''}`}
                  onClick={() => setField('vocal_range', r.value)}
                  title={r.desc}
                >
                  {r.label}
                </button>
              ))}
            </div>
            {vocal_range && (
              <div style={{ fontSize: 12, color: 'var(--text-mute)', marginTop: 6 }}>
                {ranges.find((r) => r.value === vocal_range)?.desc}
              </div>
            )}
          </div>

          <div className="field">
            <label htmlFor="artists">Favorite artists (comma-separated)</label>
            <input
              id="artists"
              className="input"
              placeholder="e.g. Queen, Adele, Bon Jovi"
              value={favorite_artists}
              onChange={(e) => setField('favorite_artists', e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="genres">Favorite genres (comma-separated)</label>
            <input
              id="genres"
              className="input"
              placeholder="e.g. Rock, Pop, Soul"
              value={favorite_genres}
              onChange={(e) => setField('favorite_genres', e.target.value)}
            />
          </div>

          <button className="btn cyan" type="submit" disabled={loading || !vocal_range}>
            ✨ Suggest songs for me
          </button>
        </form>
      </div>

      {error && <div className="banner warn">⚠️ {error}</div>}

      {loading ? (
        <Loading label="Finding your perfect songs…" />
      ) : searched && suggestions.length === 0 ? (
        <EmptyState icon="🎤" message="No suggestions. Try a different range." />
      ) : suggestions.length > 0 ? (
        <>
          <div className="section-title">Top picks for you</div>
          {suggestions.map((s) => (
            <SongCard
              key={s.song.id}
              song={s.song}
              score={s.score}
              reason={s.reason}
              isFavorite={favorites.includes(s.song.id)}
              onToggleFavorite={() => toggleFav(s.song.id)}
            />
          ))}
        </>
      ) : (
        <div className="empty">
          <span className="big" aria-hidden="true">
            ✨
          </span>
          Pick your range above and we'll suggest songs that fit your voice.
        </div>
      )}
    </div>
  );
}

// Re-export Song type to satisfy isolated modules when needed
export type { Song };
