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

/**
 * What we resolved, shown back as a card rather than a filled-in form.
 *
 * Once the lookup has found the place, the fields are answers, not questions.
 * Rendering them as inputs invites editing for its own sake — a text cursor is
 * a prompt — and the whole point of enrichment is that we own these facts and
 * keep them current. One tap behind an Edit button is enough friction to mean
 * "I actually know better than the map data", which is the only reason to
 * change them.
 */
export function ResolvedVenueCard({
  name,
  address,
  phone,
  website,
  instagram,
  facebook,
  openingHours,
  onEdit,
  onChangeVenue,
}: {
  name: string;
  address: string;
  phone?: string;
  website?: string;
  instagram?: string;
  facebook?: string;
  openingHours?: string | null;
  onEdit: () => void;
  onChangeVenue?: () => void;
}) {
  const rows: { label: string; value: string }[] = [];
  if (phone) rows.push({ label: 'Phone', value: phone });
  if (website) rows.push({ label: 'Website', value: website.replace(/^https?:\/\//, '') });
  if (instagram) rows.push({ label: 'Instagram', value: `@${instagram}` });
  if (facebook) rows.push({ label: 'Facebook', value: facebook });
  if (openingHours) rows.push({ label: 'Venue hours', value: openingHours });

  return (
    <View style={styles.resolved}>
      <View style={styles.resolvedHead}>
        <Text style={styles.resolvedTick}>✓</Text>
        <Text style={styles.resolvedFound}>Found it</Text>
      </View>

      <Text style={styles.resolvedName}>{name}</Text>
      <Text style={styles.resolvedAddr}>{address}</Text>

      {rows.length > 0 && (
        <View style={styles.resolvedRows}>
          {rows.map((r) => (
            <View key={r.label} style={styles.resolvedRow}>
              <Text style={styles.resolvedRowLabel}>{r.label}</Text>
              <Text style={styles.resolvedRowValue} numberOfLines={1}>
                {r.value}
              </Text>
            </View>
          ))}
        </View>
      )}

      <Text style={styles.resolvedNote}>
        {rows.length > 0
          ? "We keep these details up to date, so you don't have to."
          : "We'll fill in contact details as we find them."}
      </Text>

      <View style={styles.resolvedActions}>
        <Pressable
          onPress={onEdit}
          accessibilityRole="button"
          style={({ pressed }) => [styles.resolvedBtn, pressed && styles.resolvedBtnPressed]}
        >
          <Text style={styles.resolvedBtnText}>Edit details</Text>
        </Pressable>
        {onChangeVenue && (
          <Pressable
            onPress={onChangeVenue}
            accessibilityRole="button"
            style={({ pressed }) => [styles.resolvedBtnGhost, pressed && styles.resolvedBtnPressed]}
          >
            <Text style={styles.resolvedBtnGhostText}>Not this place</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

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
  resolved: {
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.bg2,
    borderRadius: Radius.sm,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
  },
  resolvedHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: Spacing.sm },
  resolvedTick: { color: Colors.cyan, fontSize: 13, fontWeight: '800' },
  resolvedFound: {
    color: Colors.cyan, fontSize: 11, fontWeight: '800',
    letterSpacing: 1, textTransform: 'uppercase',
  },
  resolvedName: { color: Colors.text, fontSize: 18, fontWeight: '800' },
  resolvedAddr: { color: Colors.textDim, fontSize: 14, marginTop: 2, lineHeight: 20 },
  resolvedRows: {
    marginTop: Spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: Colors.border,
    paddingTop: Spacing.sm,
    gap: 4,
  },
  resolvedRow: { flexDirection: 'row', alignItems: 'baseline', gap: Spacing.sm },
  resolvedRowLabel: { color: Colors.textMute, fontSize: 12, width: 84 },
  resolvedRowValue: { color: Colors.text, fontSize: 13, flex: 1 },
  resolvedNote: { color: Colors.textMute, fontSize: 12, marginTop: Spacing.md, lineHeight: 17 },
  resolvedActions: { flexDirection: 'row', gap: Spacing.sm, marginTop: Spacing.md },
  resolvedBtn: {
    minHeight: 44, paddingHorizontal: Spacing.lg, borderRadius: Radius.sm,
    borderWidth: 1, borderColor: Colors.border, backgroundColor: Colors.panel2,
    alignItems: 'center', justifyContent: 'center',
  },
  resolvedBtnText: { color: Colors.text, fontSize: 14, fontWeight: '700' },
  resolvedBtnGhost: {
    minHeight: 44, paddingHorizontal: Spacing.md, borderRadius: Radius.sm,
    alignItems: 'center', justifyContent: 'center',
  },
  resolvedBtnGhostText: { color: Colors.textMute, fontSize: 14, fontWeight: '600' },
  resolvedBtnPressed: { opacity: 0.85 },
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
