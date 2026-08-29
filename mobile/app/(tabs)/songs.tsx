import { useEffect, useMemo, useState } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import type { Song, Suggestion, VocalRange } from '../../src/types';
import { api } from '../../src/api';
import {
  Banner,
  Button,
  Card,
  Chip,
  EmptyState,
  Loading,
  SectionTitle,
  SongCard,
} from '../../src/components';
import { Colors, Radius, Spacing, TAP_HEIGHT, Typography } from '../../src/theme';
import { usePrefsContext } from '../../src/prefs-context';
import { toggleFavorite } from '../../src/prefs';

type FilterMode = 'all' | 'favorites';

export default function SongsScreen() {
  const [songs, setSongs] = useState<Song[]>([]);
  const [allSongs, setAllSongs] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [genre, setGenre] = useState('');
  const [filterMode, setFilterMode] = useState<FilterMode>('all');
  const [showSuggestions, setShowSuggestions] = useState(false);

  const [prefs, setPrefs] = usePrefsContext();
  const favorites = prefs.favorites;

  // Load all songs (for favorites filtering) once, plus filtered results on search
  useEffect(() => {
    // Always keep a full list for favorites mode
    api.getSongs(undefined, undefined, 500).then(setAllSongs).catch(() => {});
  }, []);

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
    (filterMode === 'favorites' ? allSongs : songs).forEach((s) => set.add(s.genre));
    return Array.from(set).sort();
  }, [songs, allSongs, filterMode]);

  const toggleFav = (id: number) => {
    setPrefs((p) => toggleFavorite(p, id));
  };

  // Compute the displayed list based on filter mode
  const displayedSongs: Song[] = useMemo(() => {
    if (filterMode === 'favorites') {
      const favSet = new Set(favorites);
      let favSongs = allSongs.filter((s) => favSet.has(s.id));
      // Apply search/genre filter on favorites too
      if (search.trim()) {
        const q = search.trim().toLowerCase();
        favSongs = favSongs.filter(
          (s) =>
            s.title.toLowerCase().includes(q) ||
            s.artist.toLowerCase().includes(q),
        );
      }
      if (genre) {
        favSongs = favSongs.filter((s) => s.genre === genre);
      }
      return favSongs;
    }
    return songs;
  }, [filterMode, favorites, allSongs, search, genre, songs]);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      {/* Filter mode toggle */}
      <View style={styles.filterRow}>
        <Chip
          label="All Songs"
          active={filterMode === 'all'}
          onPress={() => setFilterMode('all')}
        />
        <Chip
          label={`⭐ Saved (${favorites.length})`}
          active={filterMode === 'favorites'}
          onPress={() => setFilterMode('favorites')}
        />
        <Chip
          label="✨ Suggestions"
          onPress={() => setShowSuggestions(true)}
        />
      </View>

      {/* Search bar */}
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

      {/* Genre chips */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipsScroll}
        contentContainerStyle={styles.chipsContent}
      >
        <Chip label="All Genres" active={genre === ''} onPress={() => setGenre('')} />
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

      {filterMode === 'favorites' && favorites.length === 0 ? (
        <EmptyState
          icon="⭐"
          message="No saved songs yet. Tap the ☆ on any song to save it here."
        />
      ) : loading && filterMode === 'all' ? (
        <Loading label="Loading songbook…" />
      ) : displayedSongs.length === 0 ? (
        <EmptyState
          icon="🎵"
          message={
            filterMode === 'favorites'
              ? 'No saved songs match your filters.'
              : 'No songs match your search.'
          }
        />
      ) : (
        <>
          {filterMode === 'favorites' && (
            <SectionTitle>Your saved songs ({displayedSongs.length})</SectionTitle>
          )}
          {displayedSongs.map((s) => (
            <SongCard
              key={s.id}
              song={s}
              isFavorite={favorites.includes(s.id)}
              onToggleFavorite={() => toggleFav(s.id)}
            />
          ))}
        </>
      )}

      {/* Suggestions popup */}
      <SuggestionsModal
        visible={showSuggestions}
        onClose={() => setShowSuggestions(false)}
        prefs={prefs}
        setPrefs={setPrefs}
        toggleFav={toggleFav}
      />
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------
// Suggestions popup (modal) — moved from suggestions.tsx
// ---------------------------------------------------------------------------

function SuggestionsModal({
  visible,
  onClose,
  prefs,
  setPrefs,
  toggleFav,
}: {
  visible: boolean;
  onClose: () => void;
  prefs: ReturnType<typeof usePrefsContext>[0];
  setPrefs: ReturnType<typeof usePrefsContext>[1];
  toggleFav: (id: number) => void;
}) {
  const [ranges, setRanges] = useState<VocalRange[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const { vocal_range, favorite_artists, favorite_genres, favorites } = prefs;

  useEffect(() => {
    if (visible && ranges.length === 0) {
      api
        .getRanges()
        .then((r) => setRanges(r.ranges))
        .catch(() => setRanges([]));
    }
  }, [visible, ranges.length]);

  // Reset state when modal closes
  useEffect(() => {
    if (!visible) {
      setSuggestions([]);
      setError(null);
      setSearched(false);
    }
  }, [visible]);

  const setField = (
    field: 'vocal_range' | 'favorite_artists' | 'favorite_genres',
    value: string,
  ) => {
    setPrefs((p) => ({ ...p, [field]: value }));
  };

  const handleSuggest = async () => {
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

  const selectedRange = ranges.find((r) => r.value === vocal_range);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.suggBackdrop} onPress={onClose}>
        <Pressable
          style={styles.suggModal}
          onPress={(e) => e.stopPropagation()}
        >
          <Pressable style={styles.modalClose} onPress={onClose} hitSlop={12}>
            <Text style={styles.modalCloseText}>×</Text>
          </Pressable>

          <Text style={styles.modalTitle}>✨ Song Suggestions</Text>

          <ScrollView
            style={styles.suggScroll}
            contentContainerStyle={styles.suggScrollContent}
            keyboardShouldPersistTaps="handled"
          >
            <Card>
              <Text style={styles.fieldLabel}>Your vocal range</Text>
              <View style={styles.chipsWrap}>
                {ranges.map((r) => (
                  <Chip
                    key={r.value}
                    label={r.label}
                    active={vocal_range === r.value}
                    onPress={() => setField('vocal_range', r.value)}
                  />
                ))}
              </View>
              {selectedRange ? (
                <Text style={styles.rangeDesc}>{selectedRange.desc}</Text>
              ) : null}

              <Text style={styles.fieldLabel}>Favorite artists (comma-separated)</Text>
              <TextInput
                style={styles.input}
                placeholder="e.g. Queen, Adele, Bon Jovi"
                placeholderTextColor={Colors.textMute}
                value={favorite_artists}
                onChangeText={(v) => setField('favorite_artists', v)}
              />

              <Text style={styles.fieldLabel}>Favorite genres (comma-separated)</Text>
              <TextInput
                style={styles.input}
                placeholder="e.g. Rock, Pop, Soul"
                placeholderTextColor={Colors.textMute}
                value={favorite_genres}
                onChangeText={(v) => setField('favorite_genres', v)}
              />

              <Button
                label="✨ Suggest songs for me"
                variant="cyan"
                onPress={handleSuggest}
                disabled={loading || !vocal_range}
              />
            </Card>

            {error && <Banner message={`⚠️ ${error}`} variant="warn" />}

            {loading ? (
              <Loading label="Finding your perfect songs…" />
            ) : searched && suggestions.length === 0 ? (
              <EmptyState icon="🎤" message="No suggestions. Try a different range." />
            ) : suggestions.length > 0 ? (
              <>
                <SectionTitle>Top picks for you</SectionTitle>
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
              <EmptyState
                icon="✨"
                message="Pick your range above and we'll suggest songs that fit your voice."
              />
            )}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  content: { padding: Spacing.lg, paddingBottom: 100 },

  // Filter row
  filterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: Spacing.md,
    gap: Spacing.xs,
  },

  // Search
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
    marginBottom: Spacing.md,
  },

  // Genre chips
  chipsScroll: {
    flexGrow: 0,
    marginBottom: Spacing.md,
  },
  chipsContent: {
    flexDirection: 'row',
    paddingRight: Spacing.lg,
  },

  // Suggestions modal
  suggBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  suggModal: {
    backgroundColor: Colors.panel,
    borderTopLeftRadius: Radius.md,
    borderTopRightRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.xl,
    maxHeight: '90%',
  },
  modalClose: {
    position: 'absolute',
    top: 8,
    right: 12,
    zIndex: 1,
  },
  modalCloseText: {
    fontSize: 28,
    color: Colors.textDim,
  },
  modalTitle: {
    ...Typography.heading,
    color: Colors.text,
    marginBottom: Spacing.md,
  },
  suggScroll: {
    maxHeight: '80%',
  },
  suggScrollContent: {
    paddingBottom: Spacing.xl,
  },

  // Suggestion form
  fieldLabel: {
    ...Typography.small,
    color: Colors.textDim,
    fontWeight: '600',
    marginBottom: Spacing.sm,
    marginTop: Spacing.sm,
  },
  chipsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  rangeDesc: {
    fontSize: 12,
    color: Colors.textMute,
    marginTop: Spacing.xs,
  },
});
