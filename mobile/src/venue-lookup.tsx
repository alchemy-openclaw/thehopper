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
import { StyleSheet, Text, View } from 'react-native';
import {
  Button as PaperButton,
  Icon,
  List,
  Surface,
  TextInput as PaperTextInput,
} from 'react-native-paper';
import { api } from './api';
import { getAnchorQuietly, type Coords } from './geo';
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
    <Surface style={styles.resolved} elevation={1}>
      <View style={styles.resolvedHead}>
        <Icon source="check-circle-outline" size={15} color={Colors.cyan} />
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
        <PaperButton mode="contained-tonal" icon="pencil-outline" onPress={onEdit} compact>
          Edit details
        </PaperButton>
        {onChangeVenue && (
          <PaperButton mode="text" onPress={onChangeVenue} compact textColor={Colors.textMute}>
            Not this place
          </PaperButton>
        )}
      </View>
    </Surface>
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

  // Never prompts. Uses a live fix when location is already permitted, so
  // someone who has allowed it gets nearby results on their very first search
  // rather than having to run a near-me search first to seed the cache; falls
  // back to a remembered fix, then to nothing.
  useEffect(() => {
    let alive = true;
    getAnchorQuietly().then((c) => {
      if (alive) setAnchor(c);
    });
    return () => {
      alive = false;
    };
  }, []);

  const search = async () => {
    if (name.trim().length < 2) {
      setNote('Enter the venue name first.');
      return;
    }
    // City is only needed when we have no idea where the user is. With an
    // anchor the name alone is enough, and the server biases to it.
    if (!city.trim() && !anchor) {
      setNote('Add a city — we need somewhere to search near.');
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
      <PaperTextInput
        mode="outlined"
        label="Venue name"
        placeholder="e.g. Coconuts on the Beach"
        value={name}
        onChangeText={onChangeName}
        autoCapitalize="words"
        dense
        style={styles.paperInput}
      />

      <PaperTextInput
        mode="outlined"
        label={anchor ? 'City (optional)' : 'City'}
        placeholder="e.g. Cocoa Beach"
        value={city}
        onChangeText={onChangeCity}
        onSubmitEditing={search}
        returnKeyType="search"
        autoCapitalize="words"
        dense
        style={styles.paperInput}
      />

      {/* `loading` gives Paper's own spinner in place of the label, so the
          button keeps its width and does not jump while a search runs. */}
      <PaperButton
        mode="contained"
        icon="map-search-outline"
        loading={searching}
        disabled={searching}
        onPress={search}
        contentStyle={styles.btnContent}
        style={styles.btn}
      >
        {searching ? 'Looking…' : 'Look up the address'}
      </PaperButton>

      {note ? <Text style={styles.note}>{note}</Text> : null}

      {results && results.length > 0 && (
        <View style={styles.results}>
          <Text style={styles.resultsHint}>
            {results.length === 1 ? 'Found this — tap to use it:' : 'Tap the right one to use it:'}
          </Text>
          {results.map((s) => (
            <List.Item
              key={`${s.lat},${s.lng},${s.label}`}
              onPress={() => accept(s)}
              title={s.name ?? s.address}
              titleStyle={styles.resultName}
              description={() => (
                <View>
                  <Text style={styles.resultAddr}>{s.label}</Text>
                  {extrasNote(s) ? (
                    <Text style={styles.resultExtras}>{extrasNote(s)}</Text>
                  ) : null}
                </View>
              )}
              right={() => (
                <View style={styles.resultAction}>
                  <Text style={styles.resultUse}>Use this</Text>
                  <Icon source="arrow-right-circle" size={18} color={Colors.cyan} />
                </View>
              )}
              style={styles.result}
            />
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
  wrap: { marginBottom: Spacing.xs },
  paperInput: { backgroundColor: Colors.bg2, marginBottom: Spacing.sm },
  btnContent: { height: TAP_HEIGHT },
  btn: {
    height: TAP_HEIGHT,
    marginTop: Spacing.md,
    borderRadius: Radius.sm,
    backgroundColor: Colors.purple,
    alignItems: 'center',
    justifyContent: 'center',
  },
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
  resultName: { color: Colors.text, fontSize: 15, fontWeight: '700' },
  resultAddr: { color: Colors.textDim, fontSize: 14, marginTop: 2 },
  resultsHint: {
    color: Colors.textDim,
    fontSize: 12,
    fontWeight: '600',
    paddingHorizontal: 14,
    paddingTop: 10,
    paddingBottom: 2,
  },
  resultAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    alignSelf: 'center',
    paddingLeft: Spacing.sm,
  },
  resultUse: {
    color: Colors.cyan,
    fontSize: 13,
    fontWeight: '800',
  },
  resultExtras: { color: Colors.cyan, fontSize: 12, marginTop: 4 },
});
