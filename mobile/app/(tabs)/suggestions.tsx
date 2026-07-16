import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import type { Suggestion, VocalRange } from '../../src/types';
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

export default function SuggestionsScreen() {
  const [ranges, setRanges] = useState<VocalRange[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const [prefs, setPrefs] = usePrefsContext();
  const { vocal_range, favorite_artists, favorite_genres, favorites } = prefs;

  useEffect(() => {
    api
      .getRanges()
      .then((r) => setRanges(r.ranges))
      .catch(() => setRanges([]));
  }, []);

  const setField = (field: 'vocal_range' | 'favorite_artists' | 'favorite_genres', value: string) => {
    setPrefs((p) => ({ ...p, [field]: value }));
  };

  const toggleFav = (id: number) => {
    setPrefs((p) => toggleFavorite(p, id));
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
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
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
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  content: { padding: Spacing.lg, paddingBottom: 100 },
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
});
