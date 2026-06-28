import { useEffect, useMemo, useState } from 'react';
import type { Song } from '../types';
import { api } from '../api';
import { EmptyState, Loading, SongCard } from '../components';
import type { PrefsTuple } from '../prefs-types';

interface Props {
  prefs: PrefsTuple;
}

export default function SongsPage({ prefs }: Props) {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState('');

  const [prefsState, setPrefsState] = prefs;
  const favorites = prefsState.favorites;

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      setError(null);
      api
        .getSongs(search.trim() || undefined, genre || undefined)
        .then((data) => {
          setSongs(data);
          setLoading(false);
        })
        .catch((e) => {
          setError(e instanceof Error ? e.message : 'Failed to load songs');
          setLoading(false);
        });
    }, 250); // debounce
    return () => clearTimeout(t);
  }, [search, genre]);

  const genres = useMemo(() => {
    const set = new Set<string>();
    songs.forEach((s) => set.add(s.genre));
    return Array.from(set).sort();
  }, [songs]);

  const toggleFav = (id: number) => {
    setPrefsState((p) => {
      const has = p.favorites.includes(id);
      return {
        ...p,
        favorites: has
          ? p.favorites.filter((x) => x !== id)
          : [...p.favorites, id],
      };
    });
  };

  return (
    <div>
      <div className="search-bar">
        <input
          className="input"
          placeholder="🔍 Search songs or artists…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search songs"
        />
      </div>

      <div className="chips" style={{ marginBottom: 12, overflowX: 'auto' }}>
        <button
          className={`chip ${genre === '' ? 'active' : ''}`}
          onClick={() => setGenre('')}
        >
          All
        </button>
        {genres.map((g) => (
          <button
            key={g}
            className={`chip ${genre === g ? 'active' : ''}`}
            onClick={() => setGenre(genre === g ? '' : g)}
          >
            {g}
          </button>
        ))}
      </div>

      {error && <div className="banner warn">⚠️ {error}</div>}

      {loading ? (
        <Loading label="Loading songbook…" />
      ) : songs.length === 0 ? (
        <EmptyState icon="🎵" message="No songs match your search." />
      ) : (
        songs.map((s) => (
          <SongCard
            key={s.id}
            song={s}
            isFavorite={favorites.includes(s.id)}
            onToggleFavorite={() => toggleFav(s.id)}
          />
        ))
      )}
    </div>
  );
}
