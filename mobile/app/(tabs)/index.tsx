import { useEffect, useMemo, useState } from 'react';
import {
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { router } from 'expo-router';
import type { AppConfig, Venue } from '../../src/types';
import { api } from '../../src/api';
import { getGeolocation } from '../../src/prefs';
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
} from '../../src/components';
import { Colors, Radius, Spacing, TAP_HEIGHT, Typography } from '../../src/theme';

/** What's currently narrowing the venue list. `all` is the default display. */
type Filter =
  | { kind: 'all' }
  | { kind: 'near' }
  | { kind: 'city'; city: string };

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

  const loadVenues = async (lat?: number, lng?: number, cityFilter?: string, radius?: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getVenues(lat, lng, cityFilter, radius);
      setVenues(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load venues');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  const handleLocate = async () => {
    setError(null);
    try {
      const { lat, lng } = await getGeolocation();
      setLastLocation({ lat, lng });
      setFilter({ kind: 'near' });
      setCity('');
      setRadiusOpen(false);
      await loadVenues(lat, lng, undefined, radiusMiles);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not get location');
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

  const handleCitySearch = () => {
    const trimmed = city.trim();
    // An empty city box is a no-op now — there is no "show everything" view
    // to fall back to, by design.
    if (!trimmed) return;
    setFilter({ kind: 'city', city: trimmed });
    loadVenues(undefined, undefined, trimmed);
  };

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
        <View style={styles.findRow}>
          <View style={{ flex: 1 }}>
            <Button label="Find karaoke near me" onPress={handleLocate} disabled={loading} />
          </View>
          <Pressable
            onPress={() => setRadiusOpen((o) => !o)}
            style={({ pressed }) => [
              styles.radiusBtn,
              pressed && styles.whenChipPressed,
            ]}
            accessibilityLabel={`Search radius: ${radiusMiles} miles. Tap to change.`}
          >
            <Text style={styles.radiusBtnText}>{radiusMiles} mi</Text>
            <Text style={styles.radiusBtnCaret}> ▾</Text>
          </Pressable>
        </View>
        {radiusOpen && (
          <Modal
            transparent
            visible={radiusOpen}
            animationType="fade"
            onRequestClose={() => setRadiusOpen(false)}
          >
            {/* Full-screen scrim; tap outside the card to dismiss. */}
            <Pressable style={styles.modalScrim} onPress={() => setRadiusOpen(false)}>
              <Pressable style={styles.modalCard} onPress={() => {}}>
                <Text style={styles.modalTitle}>Show karaoke within</Text>
                {RADIUS_OPTIONS.map((m) => (
                  <Pressable
                    key={m}
                    onPress={() => handleRadiusChange(m)}
                    style={({ pressed }) => [
                      styles.modalRow,
                      pressed && styles.whenChipPressed,
                    ]}
                  >
                    <Text
                      style={[
                        styles.modalRowText,
                        m === radiusMiles && styles.modalRowTextActive,
                      ]}
                    >
                      {m} miles
                    </Text>
                    {m === radiusMiles && <Text style={styles.modalCheck}>✓</Text>}
                  </Pressable>
                ))}
              </Pressable>
            </Pressable>
          </Modal>
        )}
        <View style={styles.cityRow}>
          <TextInput
            style={styles.input}
            placeholder="or search by city…"
            placeholderTextColor={Colors.textMute}
            value={city}
            onChangeText={setCity}
            onSubmitEditing={handleCitySearch}
            returnKeyType="search"
          />
          <Button
            label="Go"
            variant="secondary"
            onPress={handleCitySearch}
            style={styles.goBtn}
          />
        </View>
        {filterLabel && (
          <View style={styles.filterRow}>
            <Text style={styles.filterText}>{filterLabel}</Text>
            <Button
              label="Clear search"
              variant="secondary"
              onPress={handleReset}
              style={styles.clearBtn}
            />
          </View>
        )}

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
        visibleVenues.map((v) => (
          <VenueCard
            key={v.id}
            venue={v}
            onSelect={() => handleSelectVenue(v)}
            stripeConfigured={config?.stripe_configured ?? false}
          />
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
            <Text style={styles.venuePhone}>📞 {venue.phone}</Text>
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
            style={({ pressed }) => [styles.venueDist, pressed && { opacity: 0.85 }]}
            accessibilityLabel={`Open ${venue.name} in maps`}
          >
            <Text style={styles.venueDistText}>📍 Map</Text>
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

      <View style={styles.venueMeta}>
        {venue.karaoke_nights.map((n) => (
          <MetaPill key={n} label={n} variant="nights" />
        ))}
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
  findRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  radiusBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    minHeight: TAP_HEIGHT,
    minWidth: 96,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.bg2,
    borderRadius: Radius.sm,
  },
  radiusBtnText: {
    color: Colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  radiusBtnCaret: {
    color: Colors.textMute,
    fontSize: 12,
  },
  modalScrim: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.lg,
  },
  modalCard: {
    width: '100%',
    maxWidth: 320,
    backgroundColor: Colors.bg2,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.md,
    padding: Spacing.md,
  },
  modalTitle: {
    fontSize: 13,
    color: Colors.textDim,
    marginBottom: 6,
  },
  modalRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 48,
    paddingHorizontal: 8,
    borderRadius: Radius.sm,
  },
  modalRowText: { color: Colors.textDim, fontSize: 16, fontWeight: '600' },
  modalRowTextActive: { color: Colors.text, fontWeight: '700' },
  modalCheck: { color: Colors.pink, fontSize: 16, fontWeight: '700' },
  cityRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginTop: Spacing.md,
  },
  input: {
    flex: 1,
    minHeight: TAP_HEIGHT,
    backgroundColor: Colors.bg2,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.sm,
    paddingHorizontal: 14,
    color: Colors.text,
    fontSize: 16,
  },
  goBtn: {
    paddingHorizontal: 18,
  },
  filterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.md,
  },
  filterText: {
    flex: 1,
    fontSize: 13,
    color: Colors.textDim,
    lineHeight: 18,
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
  clearBtn: {
    paddingHorizontal: 14,
  },
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
