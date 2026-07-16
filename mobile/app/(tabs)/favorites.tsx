import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet } from 'react-native';
import type { Song } from '../../src/types';
import { api } from '../../src/api';
import {
  EmptyState,
  Loading,
  SectionTitle,
  SongCard,
} from '../../src/components';
import { Colors, Spacing } from '../../src/theme';
import { usePrefsContext } from '../../src/prefs-context';
import { toggleFavorite } from '../../src/prefs';

export default function FavoritesScreen() {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);

  const [prefs, setPrefs] = usePrefsContext();
  const favorites = prefs.favorites;

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
      .catch(() => {
        if (!cancelled) setSongs([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [favorites]);

  const toggleFav = (id: number) => {
    setPrefs((p) => toggleFavorite(p, id));
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
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
    >
      <SectionTitle>Your saved songs ({songs.length})</SectionTitle>
      {songs.map((s) => (
        <SongCard
          key={s.id}
          song={s}
          isFavorite
          onToggleFavorite={() => toggleFav(s.id)}
        />
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  content: { padding: Spacing.lg, paddingBottom: 100 },
});
