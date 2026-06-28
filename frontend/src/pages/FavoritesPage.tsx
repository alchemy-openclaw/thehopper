import { useEffect, useState } from 'react';
import type { Song } from '../types';
import { api } from '../api';
import { EmptyState, Loading, SongCard } from '../components';
import type { PrefsTuple } from '../prefs-types';

interface Props {
  prefs: PrefsTuple;
}

export default function FavoritesPage({ prefs }: Props) {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [prefsState, setPrefsState] = prefs;
  const favorites = prefsState.favorites;

  useEffect(() => {
    let cancelled = false;
    if (favorites.length === 0) {
      setSongs([]);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    setLoading(true);
    api
      .getSongs()
      .then((all) => {
        if (cancelled) return;
        const favSet = new Set(favorites);
        setSongs(all.filter((s) => favSet.has(s.id)));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [favorites]);

  const toggleFav = (id: number) => {
    setPrefsState((p) => ({
      ...p,
      favorites: p.favorites.filter((x) => x !== id),
    }));
  };

  if (loading) return <Loading label="Loading your saved songs…" />;

  if (songs.length === 0) {
    return (
      <EmptyState
        icon="⭐"
        message="No saved songs yet. Tap the ☆ on any song to save it here."
      />
    );
  }

  return (
    <div>
      <div className="section-title">Your saved songs ({songs.length})</div>
      {songs.map((s) => (
        <SongCard
          key={s.id}
          song={s}
          isFavorite
          onToggleFavorite={() => toggleFav(s.id)}
        />
      ))}
    </div>
  );
}
