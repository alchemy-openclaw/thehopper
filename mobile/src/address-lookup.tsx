/**
 * Address lookup for the venue/show submission forms.
 *
 * Assist, not replace: picking a result prefills address / city / state (and
 * hands back coordinates), but every field stays editable afterwards. A venue
 * the geocoder has never heard of must never become unenterable — plenty of
 * the bars in this directory are exactly that.
 *
 * Search is on demand (a button, plus keyboard submit) rather than typeahead.
 * Nominatim's usage policy forbids per-keystroke autocomplete, and the backend
 * throttles to one call a second, so a live-updating field would mostly show
 * the user a spinner anyway.
 */

import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { api } from './api';
import { getLastKnownGeo, type Coords } from './geo';
import type { AddressSuggestion } from './types';
import { Colors, Radius, Spacing, TAP_HEIGHT } from './theme';

export function AddressLookup({
  city,
  onPick,
}: {
  /** Current value of the form's city field, used as a fallback anchor. */
  city?: string;
  onPick: (s: AddressSuggestion) => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<AddressSuggestion[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anchor, setAnchor] = useState<Coords | null>(null);

  // Read-only: this reuses a fix from an earlier search and never prompts.
  // The backend falls back to the city field, then its own default anchor.
  useEffect(() => {
    let live = true;
    getLastKnownGeo().then((c) => {
      if (live) setAnchor(c);
    });
    return () => {
      live = false;
    };
  }, []);

  const search = async () => {
    const q = query.trim();
    if (q.length < 3) {
      setError('Type at least 3 characters.');
      return;
    }
    setSearching(true);
    setError(null);
    try {
      const found = await api.geocodeSearch(q, anchor, city);
      setResults(found);
      if (found.length === 0) setError('No matches — type the address in below instead.');
    } catch (e) {
      setResults(null);
      setError(e instanceof Error ? e.message : 'Lookup failed — type the address in below instead.');
    } finally {
      setSearching(false);
    }
  };

  const pick = (s: AddressSuggestion) => {
    onPick(s);
    setResults(null);
    setQuery('');
    setError(null);
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>Find the address</Text>
      <View style={styles.row}>
        <TextInput
          style={styles.input}
          placeholder="123 Main St, or the bar's name"
          placeholderTextColor={Colors.textMute}
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={search}
          returnKeyType="search"
          autoCapitalize="words"
          autoCorrect={false}
        />
        <Pressable
          onPress={search}
          disabled={searching}
          style={({ pressed }) => [styles.btn, pressed && styles.btnPressed, searching && styles.btnBusy]}
        >
          {searching ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.btnText}>Find</Text>
          )}
        </Pressable>
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {results && results.length > 0 && (
        <View style={styles.results}>
          {results.map((s) => (
            <Pressable
              key={`${s.lat},${s.lng},${s.label}`}
              onPress={() => pick(s)}
              style={({ pressed }) => [styles.result, pressed && styles.resultPressed]}
            >
              <Text style={styles.resultText}>{s.label}</Text>
            </Pressable>
          ))}
        </View>
      )}

      <Text style={styles.hint}>
        Optional — picking one fills the fields below, and you can still edit them.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: Spacing.md },
  label: { color: Colors.textDim, fontSize: 13, fontWeight: '600', marginBottom: 6 },
  row: { flexDirection: 'row', gap: Spacing.sm },
  input: {
    flex: 1,
    height: TAP_HEIGHT,
    backgroundColor: Colors.bg2,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.sm,
    paddingHorizontal: 14,
    color: Colors.text,
    fontSize: 16,
  },
  btn: {
    height: TAP_HEIGHT,
    minWidth: 72,
    paddingHorizontal: Spacing.lg,
    borderRadius: Radius.sm,
    backgroundColor: Colors.purple,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnPressed: { opacity: 0.85 },
  btnBusy: { opacity: 0.7 },
  btnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  error: { color: Colors.textDim, fontSize: 13, marginTop: 6 },
  results: {
    marginTop: Spacing.sm,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.sm,
    overflow: 'hidden',
  },
  result: {
    paddingHorizontal: 14,
    paddingVertical: 12,
    minHeight: 44,
    justifyContent: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.border,
    backgroundColor: Colors.bg2,
  },
  resultPressed: { backgroundColor: Colors.panel2 },
  resultText: { color: Colors.text, fontSize: 15 },
  hint: { color: Colors.textMute, fontSize: 12, marginTop: 6 },
});
