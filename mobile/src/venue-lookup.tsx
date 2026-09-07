/**
 * Venue lookup for the submission forms.
 *
 * Built around the two things a submitter already knows: the venue's name and
 * the city it's in. Nobody adding "Coconuts on the Beach in Cocoa Beach"
 * should have to go and find out that it sits at 2 Minutemen Causeway — the
 * street address, state and coordinates come back from the lookup and fill the
 * fields below. Making them type the address first would defeat the point.
 *
 * The two inputs here are the form's own name and city fields, hoisted up so
 * they're typed once rather than duplicated above and below the search.
 *
 * Assist, not replace: accepting a result prefills, but every field stays
 * editable and a venue the geocoder has never heard of is still enterable by
 * hand. Plenty of the bars in this directory are exactly that.
 *
 * Search runs on demand rather than per keystroke — Nominatim's usage policy
 * forbids autocomplete, and the backend throttles to one call a second.
 */

import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { api } from './api';
import { getLastKnownGeo, type Coords } from './geo';
import type { VenueSuggestion } from './types';
import { Colors, Radius, Spacing, TAP_HEIGHT } from './theme';

/** "also has phone · website" — says what accepting will fill in beyond the address. */
function extrasNote(s: VenueSuggestion): string | null {
  const has = [
    s.phone ? 'phone' : null,
    s.website ? 'website' : null,
    s.instagram ? 'instagram' : null,
  ].filter((x): x is string => !!x);
  return has.length ? `also has ${has.join(' · ')}` : null;
}

export function VenueLookup({
  name,
  city,
  onChangeName,
  onChangeCity,
  onAccept,
  labelStyle,
}: {
  name: string;
  city: string;
  onChangeName: (v: string) => void;
  onChangeCity: (v: string) => void;
  onAccept: (s: VenueSuggestion) => void;
  /** Lets each form keep its own field-label styling. */
  labelStyle?: object;
}) {
  const [results, setResults] = useState<VenueSuggestion[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [anchor, setAnchor] = useState<Coords | null>(null);

  // Read-only: reuses a fix from an earlier search and never prompts. Asking
  // for the location permission because someone typed a bar name is the wrong
  // trade — the backend falls back to its own default anchor without it.
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
    if (name.trim().length < 2) {
      setNote('Enter the venue name first.');
      return;
    }
    setSearching(true);
    setNote(null);
    setResults(null);
    try {
      const found = await api.venueLookup(name.trim(), city, anchor);
      setResults(found);
      if (found.length === 0) {
        setNote("Couldn't find it — fill in the address below by hand.");
      }
    } catch (e) {
      setNote(
        e instanceof Error ? e.message : 'Lookup failed — fill in the address below by hand.',
      );
    } finally {
      setSearching(false);
    }
  };

  const accept = (s: VenueSuggestion) => {
    onAccept(s);
    setResults(null);
    setNote(null);
  };

  return (
    <View style={styles.wrap}>
      <Text style={[styles.label, labelStyle]}>Venue name *</Text>
      <TextInput
        style={styles.input}
        placeholder="e.g. Coconuts on the Beach"
        placeholderTextColor={Colors.textMute}
        value={name}
        onChangeText={onChangeName}
        autoCapitalize="words"
      />

      <Text style={[styles.label, labelStyle]}>City *</Text>
      <TextInput
        style={styles.input}
        placeholder="e.g. Cocoa Beach"
        placeholderTextColor={Colors.textMute}
        value={city}
        onChangeText={onChangeCity}
        onSubmitEditing={search}
        returnKeyType="search"
        autoCapitalize="words"
      />

      <Pressable
        onPress={search}
        disabled={searching}
        style={({ pressed }) => [
          styles.btn,
          pressed && styles.btnPressed,
          searching && styles.btnBusy,
        ]}
      >
        {searching ? (
          <ActivityIndicator color="#fff" size="small" />
        ) : (
          <Text style={styles.btnText}>Look up the address</Text>
        )}
      </Pressable>

      {note ? <Text style={styles.note}>{note}</Text> : null}

      {results && results.length > 0 && (
        <View style={styles.results}>
          {results.map((s) => (
            <Pressable
              key={`${s.lat},${s.lng},${s.label}`}
              onPress={() => accept(s)}
              style={({ pressed }) => [styles.result, pressed && styles.resultPressed]}
            >
              {s.name ? <Text style={styles.resultName}>{s.name}</Text> : null}
              <Text style={styles.resultAddr}>{s.label}</Text>
              {extrasNote(s) ? <Text style={styles.resultExtras}>{extrasNote(s)}</Text> : null}
              <Text style={styles.resultUse}>Use this →</Text>
            </Pressable>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: Spacing.xs },
  label: { color: Colors.textDim, fontSize: 13, fontWeight: '600', marginTop: Spacing.md, marginBottom: 6 },
  input: {
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
    marginTop: Spacing.md,
    borderRadius: Radius.sm,
    backgroundColor: Colors.purple,
    alignItems: 'center',
    justifyContent: 'center',
  },
  btnPressed: { opacity: 0.85 },
  btnBusy: { opacity: 0.7 },
  btnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  note: { color: Colors.textDim, fontSize: 13, marginTop: Spacing.sm },
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
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.border,
    backgroundColor: Colors.bg2,
  },
  resultPressed: { backgroundColor: Colors.panel2 },
  resultName: { color: Colors.text, fontSize: 15, fontWeight: '700' },
  resultAddr: { color: Colors.textDim, fontSize: 14, marginTop: 2 },
  resultExtras: { color: Colors.cyan, fontSize: 12, marginTop: 4 },
  resultUse: { color: Colors.cyan, fontSize: 12, fontWeight: '700', marginTop: 6 },
});
