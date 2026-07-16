/**
 * KJ Profile screen — shows a KJ's info, their venues, and Stripe status.
 * Route: /kj/[id]
 */

import { useEffect, useState } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
  Alert,
  Linking,
} from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { api } from '../../src/api';
import type { KJ, Venue, StripeStatusResponse } from '../../src/types';
import {
  Banner,
  Button,
  Card,
  Loading,
  MetaPill,
  EmptyState,
} from '../../src/components';
import { Colors, Spacing, Typography } from '../../src/theme';

export default function KJProfileScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const kjId = parseInt(id, 10);

  const [kj, setKJ] = useState<KJ | null>(null);
  const [venues, setVenues] = useState<Venue[]>([]);
  const [stripeStatus, setStripeStatus] = useState<StripeStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!kjId) return;
    Promise.all([
      api.getKJ(kjId),
      api.getKJVenues(kjId),
      api.kjStripeStatus(kjId).catch(() => null),
    ])
      .then(([kjData, venuesData, stripeData]) => {
        setKJ(kjData);
        setVenues(venuesData);
        setStripeStatus(stripeData);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load KJ'))
      .finally(() => setLoading(false));
  }, [kjId]);

  const handleStripeOnboard = async () => {
    if (!kj) return;
    Alert.prompt(
      'Stripe Onboarding',
      'Enter your email for Stripe:',
      async (email) => {
        if (!email) return;
        try {
          const res = await api.kjStripeOnboard(kjId, email);
          let url = res.onboarding_url;
          if (url.startsWith('/')) {
            url = `http://localhost:8000${url}`;
          }
          await WebBrowser.openBrowserAsync(url);
        } catch (e) {
          Alert.alert('Error', e instanceof Error ? e.message : 'Stripe onboarding failed');
        }
      },
    );
  };

  if (loading) return <Loading label="Loading KJ profile..." />;

  if (error || !kj) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        {error && <Banner message={error} variant="warn" />}
        <EmptyState icon="🎤" message="KJ not found" />
      </ScrollView>
    );
  }

  const stripeReady = stripeStatus?.onboarding_status === 'active';

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <Card>
        <View style={styles.header}>
          <Text style={styles.kjName}>{kj.name}</Text>
          {kj.verified && <MetaPill label="✓ Verified" />}
        </View>
        {kj.bio ? <Text style={styles.kjBio}>{kj.bio}</Text> : null}

        <View style={styles.links}>
          {kj.instagram && (
            <MetaPill label={`📷 ${kj.instagram}`} />
          )}
          {kj.website && (
            <Text
              style={styles.linkText}
              onPress={() => Linking.openURL(kj.website!)}
            >
              {kj.website}
            </Text>
          )}
        </View>
      </Card>

      {/* Stripe status */}
      <Card>
        <Text style={styles.sectionTitle}>Payments</Text>
        {stripeReady ? (
          <Banner message="✓ Stripe active — you're ready to receive payments!" variant="ok" />
        ) : stripeStatus?.onboarding_status === 'pending_verification' ? (
          <Banner message="⏳ Stripe verification in progress..." variant="info" />
        ) : stripeStatus?.onboarding_status === 'needs_onboarding' ? (
          <Banner message="⚠️ Complete your Stripe onboarding to get paid." variant="warn" />
        ) : (
          <Text style={styles.noStripe}>Not set up yet</Text>
        )}

        <Button
          label={stripeReady ? 'View Stripe Dashboard' : 'Set up payments'}
          onPress={handleStripeOnboard}
          variant={stripeReady ? 'secondary' : 'primary'}
        />
      </Card>

      {/* Venues */}
      <Text style={styles.sectionLabel}>Venues</Text>
      {venues.length === 0 ? (
        <EmptyState icon="📍" message="No venues linked yet" />
      ) : (
        venues.map((v) => (
          <Card key={v.id}>
            <Text style={styles.venueName}>{v.name}</Text>
            <Text style={styles.venueCity}>{v.city}</Text>
            <View style={styles.venueMeta}>
              {v.karaoke_nights.map((n) => (
                <MetaPill key={n} label={n} variant="nights" />
              ))}
              <MetaPill label={`🕘 ${v.start_time}–${v.end_time}`} />
            </View>
            {v.vibe ? <Text style={styles.venueVibe}>{v.vibe}</Text> : null}
          </Card>
        ))
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  content: { padding: Spacing.lg, paddingBottom: 100 },
  header: { flexDirection: 'row', alignItems: 'center', gap: Spacing.sm, marginBottom: Spacing.sm },
  kjName: { ...Typography.title, color: Colors.text },
  kjBio: { color: Colors.textDim, fontSize: 15, lineHeight: 22, marginBottom: Spacing.sm },
  links: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  linkText: { color: Colors.cyan, fontSize: 14, fontWeight: '600' },
  sectionTitle: { ...Typography.heading, color: Colors.text, marginBottom: Spacing.sm },
  sectionLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: Colors.textMute,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: Spacing.lg,
    marginBottom: Spacing.sm,
  },
  noStripe: { color: Colors.textMute, fontSize: 14, marginBottom: Spacing.sm },
  venueName: { fontSize: 18, fontWeight: '700', color: Colors.text },
  venueCity: { fontSize: 14, color: Colors.pink, fontWeight: '600', marginTop: 2 },
  venueMeta: { flexDirection: 'row', flexWrap: 'wrap', marginTop: Spacing.sm },
  venueVibe: { color: Colors.textDim, fontSize: 13, marginTop: Spacing.sm, fontStyle: 'italic' },
});
