import { useEffect, useMemo, useState } from 'react';
import { ScrollView, StyleSheet, TextInput, View } from 'react-native';
import type { Song } from '../../src/types';
import { api } from '../../src/api';
import {
  Banner,
  Chip,
  EmptyState,
  Loading,
  SongCard,
} from '../../src/components';
import { Colors, Radius, Spacing, TAP_HEIGHT } from '../../src/theme';
import { usePrefsContext } from '../../src/prefs-context';
import { toggleFavorite } from '../../src/prefs';

export default function SongsScreen() {
  const [songs, setSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState('');

  const [prefs, setPrefs] = usePrefsContext();
  const favorites = prefs.favorites;

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
    setPrefs((p) => toggleFavorite(p, id));
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <View style={styles.searchBar}>
        <TextInput
          style={styles.input}
          placeholder="🔍 Search songs or artists…"
          placeholderTextColor={Colors.textMute}
          value={search}
          onChangeText={setSearch}
          returnKeyType="search"
        />
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipsScroll}
        contentContainerStyle={styles.chipsContent}
      >
        <Chip label="All" active={genre === ''} onPress={() => setGenre('')} />
        {genres.map((g) => (
          <Chip
            key={g}
            label={g}
            active={genre === g}
            onPress={() => setGenre(genre === g ? '' : g)}
          />
        ))}
      </ScrollView>

      {error && <Banner message={`⚠️ ${error}`} variant="warn" />}

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
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  content: { padding: Spacing.lg, paddingBottom: 100 },
  searchBar: { marginBottom: Spacing.md },
  input: {
    minHeight: TAP_HEIGHT,
    backgroundColor: Colors.bg2,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.sm,
    paddingHorizontal: 14,
    color: Colors.text,
    fontSize: 16,
  },
  chipsScroll: {
    flexGrow: 0,
    marginBottom: Spacing.md,
  },
  chipsContent: {
    flexDirection: 'row',
    paddingRight: Spacing.lg,
  },
});
