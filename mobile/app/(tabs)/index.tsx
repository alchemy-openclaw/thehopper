import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import type { AppConfig, Venue } from '../../src/types';
import { api } from '../../src/api';
import { getGeolocationCached, getLastKnownGeo } from '../../src/geo';
import { daysUntilNextEvent, eventDayLabel, hasEventSoon } from '../../src/event-window';
import { formatTime12h, formatTimeRange } from '../../src/format';
import { useVenueContext } from '../../src/venue-context';
import {
  Banner,
  Button,
  Card,
  EmptyState,
  Loading,
  MetaPill,
  NightsRow,
  SplitButton,
} from '../../src/components';
import {
  Dialog,
  Portal,
  RadioButton,
  TextInput as PaperTextInput,
} from 'react-native-paper';
import Animated from 'react-native-reanimated';
import { cardEntering } from '../../src/motion';
import { Colors, Radius, Spacing, TAP_HEIGHT, Typography } from '../../src/theme';

/** What's currently narrowing the venue list. `all` is the default display. */
type Filter =
  | { kind: 'all' }
  | { kind: 'near' }
  | { kind: 'city'; city: string };

/** Type this many characters of a city before the search runs on its own. */
const CITY_SEARCH_MIN_CHARS = 4;
/** Pause in typing that counts as "done typing", in ms.
 *
 * 600 rather than a rounder 300 or 500 because it is where the cost curve
 * flattens. Typing "San Francisco" fires one search at every speed from fast
 * to hunt-and-peck at 600ms; at 450ms a slow typer fires nine, one per
 * character, each a city the server may have to geocode. Raising it further
 * buys nothing and only adds lag. */
const CITY_SEARCH_DEBOUNCE_MS = 600;

/** Radius options for the near-me search, in miles. */
const RADIUS_OPTIONS = [10, 20, 30, 40, 50];
const DEFAULT_RADIUS_MILES = 20;

export default function VenuesScreen() {
  const [venues, setVenues] = useState<Venue[]>([]);
  // Nothing loads until the singer searches — the unfiltered national list is
  // exactly what a scraper wants, so it is never the default view.
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [city, setCity] = useState('');
  const [filter, setFilter] = useState<Filter>({ kind: 'all' });
  const [config, setConfig] = useState<AppConfig | null>(null);
  // Default to what a singer can actually act on tonight. A venue whose next
  // night is Thursday is noise when you are deciding where to go now.
  const [soonOnly, setSoonOnly] = useState(true);
  const [radiusMiles, setRadiusMiles] = useState(DEFAULT_RADIUS_MILES);
  const [radiusOpen, setRadiusOpen] = useState(false);
  // Last GPS fix, kept so changing the radius re-runs the same search
  // without asking for location permission again.
  const [lastLocation, setLastLocation] = useState<{ lat: number; lng: number } | null>(null);
  const { selectVenue } = useVenueContext();

  const visibleVenues = useMemo(
    () => (soonOnly ? venues.filter((v) => hasEventSoon(v)) : venues),
    [venues, soonOnly],
  );
  // Venues hidden only because their night is not tonight or tomorrow. Counts
  // just those that actually run karaoke sometime — a venue with no schedule at
  // all is not "on another night", and saying so overstates what the escape
  // hatch would reveal.
  const otherNightCount = useMemo(
    () =>
      venues.filter((v) => !hasEventSoon(v) && daysUntilNextEvent(v) != null).length,
    [venues],
  );

  // Monotonic id for in-flight searches. Typing now starts requests on its
  // own, so two can be in the air at once — and a slow "San" landing after a
  // fast "San Francisco" would quietly replace the right results with stale
  // ones. Only the newest request is allowed to write state.
  const searchSeq = useRef(0);

  const loadVenues = async (lat?: number, lng?: number, cityFilter?: string, radius?: number) => {
    const seq = ++searchSeq.current;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getVenues(lat, lng, cityFilter, radius);
      if (seq !== searchSeq.current) return;
      setVenues(data);
    } catch (e) {
      if (seq !== searchSeq.current) return;
      setError(e instanceof Error ? e.message : 'Failed to load venues');
    } finally {
      // A superseded request must not clear the spinner the newer one owns.
      if (seq === searchSeq.current) setLoading(false);
    }
  };

  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  const handleLocate = async () => {
    setError(null);
    // The GPS fix is the slow half on a cold start, so the spinner has to
    // cover it too — loadVenues only flips `loading` once the fix is in, which
    // left the button looking inert for the couple of seconds that matter.
    setLoading(true);
    try {
      const { lat, lng } = await getGeolocationCached();
      setLastLocation({ lat, lng });
      setFilter({ kind: 'near' });
      setCity('');
      setRadiusOpen(false);
      await loadVenues(lat, lng, undefined, radiusMiles);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not get location');
    } finally {
      // loadVenues clears this itself on the happy path; this covers the throw.
      setLoading(false);
    }
  };

  /** Changing the radius re-runs the last near-me search — no new permission
      prompt, no re-sorting surprise. If there is no fix yet, locate first. */
  const handleRadiusChange = async (miles: number) => {
    setRadiusMiles(miles);
    setRadiusOpen(false);
    if (!lastLocation) {
      await handleLocate();
      return;
    }
    setFilter({ kind: 'near' });
    setCity('');
    await loadVenues(lastLocation.lat, lastLocation.lng, undefined, miles);
  };

  const runCitySearch = async (trimmed: string) => {
    setFilter({ kind: 'city', city: trimmed });
    // Send a remembered fix alongside the city. The city still decides which
    // venues come back; the coordinates only decide what "3.2 mi" on a card is
    // measured from. Read-only, so searching a city never triggers a location
    // prompt — without a stored fix the server just omits distances.
    const here = await getLastKnownGeo();
    loadVenues(here?.lat, here?.lng, trimmed);
  };

  /** Go button / keyboard submit. Runs whatever is typed, no minimum — an
      explicit tap is an instruction, not a guess about intent. */
  const handleCitySearch = async () => {
    const trimmed = city.trim();
    // An empty city box is a no-op now — there is no "show everything" view
    // to fall back to, by design.
    if (!trimmed) return;
    await runCitySearch(trimmed);
  };

  // Search as the city is typed, once there is enough of it to mean something.
  //
  // Four characters is the threshold because shorter prefixes are mostly
  // ambiguous ("san", "new") and every distinct string we send is a city the
  // server may have to geocode. The debounce matters for the same reason:
  // firing per keystroke would be the autocomplete pattern Nominatim's usage
  // policy forbids, so this waits for a pause in typing instead.
  useEffect(() => {
    const trimmed = city.trim();
    if (trimmed.length < CITY_SEARCH_MIN_CHARS) return;
    // Already showing this exact search (the Go button or a previous pause).
    if (filter.kind === 'city' && filter.city === trimmed) return;

    const timer = setTimeout(() => {
      void runCitySearch(trimmed);
    }, CITY_SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // runCitySearch is stable enough for this; re-running on `filter` would
    // retrigger the moment the search lands.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [city]);

  /** Leaving a city/near search returns to the landing state — an empty list,
      not the national dump. */
  const handleReset = () => {
    setCity('');
    setFilter({ kind: 'all' });
    setVenues([]);
    setError(null);
  };

  const handleSelectVenue = (venue: Venue) => {
    selectVenue(venue);
    router.push('/(tabs)/event');
  };

  const filterLabel =
    filter.kind === 'near'
      ? `Sorted by distance, within ${radiusMiles} mi of your location.`
      : filter.kind === 'city'
        ? `Showing venues in “${filter.city}”.`
        : null;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Card style={styles.searchCard}>
        {/* One control: the wide half runs the search, the mileage half opens
            the radius picker and carries the spinner while either is working
            (changing the radius re-runs the same search). */}
        <SplitButton
          label="Find karaoke near me"
          onPress={handleLocate}
          trailingLabel={`${radiusMiles} mi`}
          onPressTrailing={() => setRadiusOpen((o) => !o)}
          busy={loading}
          disabled={loading}
          trailingAccessibilityLabel={`Search radius: ${radiusMiles} miles. Tap to change.`}
        />
        {/* Paper's Dialog brings the scrim, the Android back-button dismiss and
            the a11y announcement the hand-rolled Modal never had. */}
        <Portal>
          <Dialog visible={radiusOpen} onDismiss={() => setRadiusOpen(false)}>
            <Dialog.Title style={styles.dialogTitle}>Show karaoke within</Dialog.Title>
            <Dialog.Content style={styles.dialogContent}>
              <RadioButton.Group
                value={String(radiusMiles)}
                onValueChange={(v) => handleRadiusChange(Number(v))}
              >
                {RADIUS_OPTIONS.map((m) => (
                  <RadioButton.Item
                    key={m}
                    label={`${m} miles`}
                    value={String(m)}
                    labelStyle={styles.dialogRowText}
                    style={styles.dialogRow}
                  />
                ))}
              </RadioButton.Group>
            </Dialog.Content>
          </Dialog>
        </Portal>
        <View style={styles.cityRow}>
          <PaperTextInput
            mode="outlined"
            label="Search by city"
            value={city}
            onChangeText={setCity}
            onSubmitEditing={handleCitySearch}
            returnKeyType="search"
            autoCapitalize="words"
            dense
            style={styles.cityInput}
            left={<PaperTextInput.Icon icon="magnify" />}
            right={
              city ? <PaperTextInput.Icon icon="close" onPress={handleReset} /> : undefined
            }
          />
          <Button
            label="Go"
            variant="secondary"
            onPress={handleCitySearch}
            style={styles.goBtn}
          />
        </View>
        {filterLabel && <Text style={styles.filterText}>{filterLabel}</Text>}

        {/* When karaoke is on. Defaults to the actionable window; the escape
            hatch matters because plenty of venues only run one night a week. */}
        <View style={styles.whenRow}>
          <Pressable
            onPress={() => setSoonOnly(true)}
            style={({ pressed }) => [
              styles.whenChip,
              soonOnly && styles.whenChipActive,
              pressed && styles.whenChipPressed,
            ]}
          >
            <Text style={[styles.whenChipText, soonOnly && styles.whenChipTextActive]}>
              Tonight & tomorrow
            </Text>
          </Pressable>
          <Pressable
            onPress={() => setSoonOnly(false)}
            style={({ pressed }) => [
              styles.whenChip,
              !soonOnly && styles.whenChipActive,
              pressed && styles.whenChipPressed,
            ]}
          >
            <Text style={[styles.whenChipText, !soonOnly && styles.whenChipTextActive]}>
              Any night
            </Text>
          </Pressable>
        </View>
      </Card>

      {error && <Banner message={`⚠️ ${error}`} variant="warn" />}

      {loading ? (
        <Loading label="Finding karaoke…" />
      ) : filter.kind === 'all' ? (
        // Landing state: nothing searched yet. Never an unfiltered national
        // list — that view is a scrape giveaway and useless to a singer.
        <EmptyState
          icon="🎤"
          message="Tap “Find karaoke near me”, or search by city, to see what's on."
        />
      ) : visibleVenues.length === 0 ? (
        <View>
          <EmptyState
            icon="🗺️"
            message={
              // Distinguish "nothing here" from "nothing tonight" — otherwise
              // the filter reads as no venues existing at all.
              otherNightCount > 0
                ? `No karaoke tonight or tomorrow${
                    filter.kind === 'city' ? ` in “${filter.city}”` : ''
                  }. ${otherNightCount} ${otherNightCount === 1 ? 'venue runs' : 'venues run'} on other nights.`
                : filter.kind === 'city'
                  ? `No venues in “${filter.city}” yet.`
                  : 'No venues found.'
            }
          />
          {otherNightCount > 0 && (
            <Button label="Show any night" onPress={() => setSoonOnly(false)} />
          )}
          <Button label="← Back" onPress={handleReset} />
        </View>
      ) : (
        visibleVenues.map((v, i) => (
          // The index drives the stagger, so results land as one wave instead
          // of the whole list snapping in at once. Keyed by venue id so a
          // re-search animates the new set rather than reusing positions.
          <Animated.View key={v.id} entering={cardEntering(i)}>
            <VenueCard
              venue={v}
              onSelect={() => handleSelectVenue(v)}
              stripeConfigured={config?.stripe_configured ?? false}
            />
          </Animated.View>
        ))
      )}
    </ScrollView>
  );
}

function VenueCard({
  venue,
  onSelect,
  stripeConfigured,
}: {
  venue: Venue;
  onSelect: () => void;
  stripeConfigured: boolean;
}) {
  const nextNight = eventDayLabel(venue);

  const openMaps = () => {
    const q = encodeURIComponent(`${venue.name}, ${venue.address}, ${venue.city}`);
    const url = Platform.select({
      // Apple Maps app handles its own scheme on iOS; web users get Google Maps.
      ios: `maps://app?daddr=${q}`,
      default: `https://maps.google.com/?daddr=${q}`,
    });
    if (url) Linking.openURL(url).catch(() => {});
  };

  // Subtitle: street + number from the address's first line, then the city —
  // "67 Wentworth Pl, San Francisco". Avoids "San Francisco, San Francisco"
  // when the street line already is the city, and falls back cleanly when
  // either part is missing (scraped rows are uneven).
  const street = venue.address.split(',')[0].trim();
  const cityName = venue.city.trim();
  const addressLine =
    street && cityName && street.toLowerCase() !== cityName.toLowerCase()
      ? `${street}, ${cityName}`
      : street || cityName;

  return (
    <Card>
      <View style={styles.venueHeader}>
        <View style={{ flex: 1 }}>
          <Text style={styles.venueName}>{venue.name}</Text>
          <Text style={styles.venueCity}>{addressLine}</Text>
          {venue.phone ? (
            <Text style={styles.venuePhone}>{venue.phone}</Text>
          ) : null}
        </View>
        <View style={styles.headerChips}>
          {venue.distance_miles != null && (
            <View style={styles.venueDist}>
              <Text style={styles.venueDistText}>{venue.distance_miles} mi</Text>
            </View>
          )}
          <Pressable
            onPress={openMaps}
            style={({ pressed }) => [styles.venueDist, styles.mapChip, pressed && { opacity: 0.85 }]}
            accessibilityLabel={`Open ${venue.name} in maps`}
          >
            <Ionicons name="location" size={13} color={Colors.cyan} />
            <Text style={styles.venueDistText}> Map</Text>
          </Pressable>
        </View>
      </View>

      {/* Says when the next night is, so the list reads the same whether or not
          the tonight/tomorrow filter is on. */}
      {nextNight && (
        <Text
          style={[
            styles.nextNight,
            nextNight === 'Tonight' && styles.nextNightSoon,
          ]}
        >
          {nextNight === 'Tonight' || nextNight === 'Tomorrow'
            ? `${nextNight} · ${formatTime12h(venue.start_time)}`
            : `Next: ${nextNight} · ${formatTime12h(venue.start_time)}`}
        </Text>
      )}

      <NightsRow nights={venue.karaoke_nights} />

      <View style={styles.venueMeta}>
        <MetaPill label={formatTimeRange(venue.start_time, venue.end_time)} />
        {venue.kj_name && <MetaPill label={`KJ: ${venue.kj_name}`} />}
      </View>

      {venue.vibe ? <Text style={styles.venueVibe}>{venue.vibe}</Text> : null}

      <View style={styles.venueActions}>
        <Button
          label="View Event →"
          onPress={onSelect}
          variant="secondary"
        />
      </View>

      <View style={styles.venueFooter}>
        {!stripeConfigured && (
          <Text style={[styles.venueFooterText, { color: Colors.yellow }]}>
            · test mode (no real charge)
          </Text>
        )}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  content: { padding: Spacing.lg, paddingBottom: 100 },
  searchCard: { marginBottom: Spacing.md },
  cityRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginTop: Spacing.md,
    alignItems: 'flex-start',
  },
  cityInput: {
    flex: 1,
    backgroundColor: Colors.bg2,
  },
  dialogTitle: { color: Colors.text, fontSize: 17, fontWeight: '700' },
  dialogContent: { paddingHorizontal: 0, paddingBottom: 0 },
  dialogRow: { paddingVertical: 2 },
  dialogRowText: { color: Colors.text, fontSize: 16 },
  goBtn: {
    paddingHorizontal: 18,
  },
  filterText: {
    fontSize: 13,
    color: Colors.textDim,
    lineHeight: 18,
    marginTop: Spacing.md,
  },
  whenRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginTop: Spacing.md,
  },
  whenChip: {
    flex: 1,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.bg2,
    borderRadius: Radius.pill,
    paddingHorizontal: Spacing.md,
  },
  whenChipActive: {
    backgroundColor: Colors.pink,
    borderColor: 'transparent',
  },
  whenChipPressed: { opacity: 0.85 },
  whenChipText: { color: Colors.textDim, fontSize: 13, fontWeight: '600' },
  whenChipTextActive: { color: '#fff', fontWeight: '700' },
  nextNight: {
    marginTop: 6,
    fontSize: 13,
    fontWeight: '600',
    color: Colors.textDim,
  },
  nextNightSoon: { color: Colors.pink },
  venueHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  venueName: {
    ...Typography.heading,
    color: Colors.text,
    lineHeight: 23,
  },
  venueCity: {
    fontSize: 13,
    color: Colors.cyan,
    fontWeight: '600',
    marginTop: 2,
  },
  venuePhone: {
    fontSize: 12,
    color: Colors.textMute,
    marginTop: 4,
  },
  headerChips: {
    alignItems: 'flex-end',
    gap: 6,
  },
  mapChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  venueDist: {
    backgroundColor: 'rgba(95, 184, 168, 0.12)',
    borderColor: 'rgba(95, 184, 168, 0.3)',
    borderWidth: 1,
    borderRadius: Radius.pill,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  venueDistText: {
    color: Colors.cyan,
    fontSize: 13,
    fontWeight: '700',
  },
  venueMeta: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 10,
  },
  venueVibe: {
    marginTop: 10,
    fontSize: 14,
    color: Colors.textDim,
    lineHeight: 20,
  },
  venueActions: {
    marginTop: 14,
  },
  venueFooter: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 10,
    gap: 12,
  },
  venueFooterText: {
    fontSize: 12,
    color: Colors.textMute,
  },
});
