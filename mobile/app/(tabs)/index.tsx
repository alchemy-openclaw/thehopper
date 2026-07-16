import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { router } from 'expo-router';
import type { AppConfig, Venue } from '../../src/types';
import { api } from '../../src/api';
import { getGeolocation } from '../../src/prefs';
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

export default function VenuesScreen() {
  const [venues, setVenues] = useState<Venue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [city, setCity] = useState('');
  const [hasLocation, setHasLocation] = useState(false);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const { selectVenue } = useVenueContext();

  const loadVenues = async (lat?: number, lng?: number, cityFilter?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getVenues(lat, lng, cityFilter);
      setVenues(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load venues');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadVenues();
    api.getConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  const handleLocate = async () => {
    setError(null);
    try {
      const { lat, lng } = await getGeolocation();
      setHasLocation(true);
      setCity('');
      await loadVenues(lat, lng);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not get location');
    }
  };

  const handleCitySearch = () => {
    setHasLocation(false);
    loadVenues(undefined, undefined, city.trim() || undefined);
  };

  const handleSelectVenue = (venue: Venue) => {
    selectVenue(venue);
    router.push('/(tabs)/event');
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Card style={styles.searchCard}>
        <Button label="📍 Find karaoke near me" onPress={handleLocate} disabled={loading} />
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
        {hasLocation && (
          <Banner message="Sorted by distance from your location." variant="info" />
        )}
      </Card>

      {error && <Banner message={`⚠️ ${error}`} variant="warn" />}

      {loading ? (
        <Loading label="Finding karaoke…" />
      ) : venues.length === 0 ? (
        <EmptyState icon="🗺️" message="No venues found. Try another city." />
      ) : (
        venues.map((v) => (
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
  return (
    <Card>
      <View style={styles.venueHeader}>
        <View style={{ flex: 1 }}>
          <Text style={styles.venueName}>{venue.name}</Text>
          <Text style={styles.venueCity}>{venue.city}</Text>
        </View>
        {venue.distance_miles != null && (
          <View style={styles.venueDist}>
            <Text style={styles.venueDistText}>{venue.distance_miles} mi</Text>
          </View>
        )}
      </View>

      <View style={styles.venueMeta}>
        {venue.karaoke_nights.map((n) => (
          <MetaPill key={n} label={n} variant="nights" />
        ))}
        <MetaPill label={`🕘 ${venue.start_time}–${venue.end_time}`} />
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
        {venue.phone ? <Text style={styles.venueFooterText}>📞 {venue.phone}</Text> : null}
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
