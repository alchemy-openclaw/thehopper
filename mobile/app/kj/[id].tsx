/**
 * KJ Profile screen — shows a KJ's info, their venues, and Stripe status.
 * Route: /kj/[id]
 */

import { useCallback, useEffect, useState } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
  Alert,
  Linking,
  Pressable,
} from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { api } from '../../src/api';
import { getSessionToken } from '../../src/session';
import { pickLineupVenue } from '../../src/event-window';
import type { KJ, LineupEntry, Venue, StripeStatusResponse } from '../../src/types';
import {
  Banner,
  Button,
  Card,
  Loading,
  MetaPill,
  EmptyState,
} from '../../src/components';
import { Colors, Spacing, Typography } from '../../src/theme';

/**
 * Renders the KJ dashboard. Normally driven by the /kj/[id] route, but the
 * "My KJ" tab renders this same component with an explicit id so hosts get the
 * dashboard inside the tab bar rather than being bounced out to a stack screen.
 */
export default function KJProfileScreen({ kjIdOverride }: { kjIdOverride?: number } = {}) {
  const { id } = useLocalSearchParams<{ id: string }>();
  const kjId = kjIdOverride ?? parseInt(id, 10);

  const [kj, setKJ] = useState<KJ | null>(null);
  const [venues, setVenues] = useState<Venue[]>([]);
  const [stripeStatus, setStripeStatus] = useState<StripeStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [songRequired, setSongRequired] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);

  // Pending singers for whichever venue is on right now, or starting within the
  // hour. Simultaneous locations are a later problem — picking by the clock is
  // right in practice and avoids a venue switcher for now.
  const [lineup, setLineup] = useState<LineupEntry[]>([]);
  const [lineupVenue, setLineupVenue] = useState<Venue | null>(null);
  const [lineupLoading, setLineupLoading] = useState(false);
  const [lineupError, setLineupError] = useState<string | null>(null);
  const [busyEntry, setBusyEntry] = useState<number | null>(null);

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
        setSongRequired(kjData.song_request_required ?? false);
        setLineupVenue(pickLineupVenue(venuesData));
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load KJ'))
      .finally(() => setLoading(false));
  }, [kjId]);

  const refreshLineup = useCallback(async () => {
    if (!lineupVenue) return;
    const token = await getSessionToken();
    if (!token) {
      setLineupError('Verify your phone number to see your lineup.');
      return;
    }
    setLineupLoading(true);
    setLineupError(null);
    try {
      setLineup(await api.getLineup(lineupVenue.id, token));
    } catch (e) {
      setLineupError(e instanceof Error ? e.message : 'Could not load the lineup');
    } finally {
      setLineupLoading(false);
    }
  }, [lineupVenue]);

  useEffect(() => {
    refreshLineup();
  }, [refreshLineup]);

  const handleNotify = async (entry: LineupEntry) => {
    const token = await getSessionToken();
    if (!token) return;
    setBusyEntry(entry.id);
    setLineupError(null);
    try {
      const updated = await api.notifyLineupSinger(entry.id, token);
      setLineup((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
      Alert.alert('Singer notified', `${entry.singer_name} has been told they're up soon.`);
    } catch (e) {
      setLineupError(e instanceof Error ? e.message : 'Could not notify that singer');
    } finally {
      setBusyEntry(null);
    }
  };

  const handleDone = async (entry: LineupEntry) => {
    const token = await getSessionToken();
    if (!token) return;
    setBusyEntry(entry.id);
    try {
      await api.completeLineupEntry(entry.id, token);
      setLineup((prev) => prev.filter((e) => e.id !== entry.id));
    } catch (e) {
      setLineupError(e instanceof Error ? e.message : 'Could not update that singer');
    } finally {
      setBusyEntry(null);
    }
  };

  const handleStripeOnboard = async () => {
    if (!kj) return;
    // Navigate to the onboarding form screen
    router.push(`/kj/${kjId}/onboard`);
  };

  const handleViewDashboard = async () => {
    if (!kj) return;
    // For existing accounts, the backend generates a fresh link regardless
    // of the email param (it's only used when creating a new account).
    try {
      const res = await api.kjStripeOnboard(kjId, 'existing@account');
      let url = res.onboarding_url;
      if (url.startsWith('/')) {
        url = `https://thehopper.alchemycreativelounge.com${url}`;
      }
      await WebBrowser.openBrowserAsync(url);
    } catch (e) {
      Alert.alert('Error', e instanceof Error ? e.message : 'Failed to open Stripe');
    }
  };

  const toggleSongRequired = async () => {
    const newVal = !songRequired;
    setSongRequired(newVal);
    setSavingSettings(true);
    try {
      const updated = await api.updateKJSettings(kjId, newVal);
      setKJ(updated);
    } catch (e) {
      setSongRequired(!newVal); // revert on failure
      Alert.alert('Error', e instanceof Error ? e.message : 'Could not update settings');
    } finally {
      setSavingSettings(false);
    }
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

      {/* Pending singers. Not an ordered queue — the KJ runs the rotation
          themselves; this just shows who is waiting and lets them call
          someone up. */}
      {venues.length > 0 && (
        <Card>
          <View style={styles.lineupHeader}>
            <Text style={styles.sectionTitle}>Pending Singers</Text>
            {lineupVenue && (
              <Pressable onPress={refreshLineup} hitSlop={10}>
                <Text style={styles.refreshLink}>
                  {lineupLoading ? 'Refreshing…' : 'Refresh'}
                </Text>
              </Pressable>
            )}
          </View>

          {!lineupVenue ? (
            // Say so plainly rather than hiding the card — a host opening the
            // app mid-afternoon should not be left wondering where it went.
            <Text style={styles.lineupEmpty}>
              No night running right now. Your lineup appears here when one of
              your venues starts, from an hour beforehand.
            </Text>
          ) : (
            <>
          <Text style={styles.lineupVenueName}>{lineupVenue.name}</Text>

          {lineupError && <Banner message={`⚠️ ${lineupError}`} variant="warn" />}

          {lineup.length === 0 && !lineupLoading && !lineupError ? (
            <Text style={styles.lineupEmpty}>
              Nobody is waiting right now. Singers appear here when they tap
              Get In Line at your venue.
            </Text>
          ) : (
            lineup.map((entry) => (
              <View key={entry.id} style={styles.lineupRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.lineupName}>
                    {entry.singer_name}
                    {entry.status === 'notified' ? ' · called up' : ''}
                  </Text>
                  {entry.song_request ? (
                    <Text style={styles.lineupSong}>🎵 {entry.song_request}</Text>
                  ) : null}
                  {!entry.can_notify && (
                    <Text style={styles.lineupNoContact}>
                      No phone or notifications — call them over in person.
                    </Text>
                  )}
                </View>
                <View style={styles.lineupActions}>
                  <Button
                    label={
                      busyEntry === entry.id
                        ? '…'
                        : entry.status === 'notified'
                          ? 'Notify again'
                          : "They're up"
                    }
                    onPress={() => handleNotify(entry)}
                    disabled={busyEntry === entry.id || !entry.can_notify}
                    variant="cyan"
                  />
                  <Pressable onPress={() => handleDone(entry)} hitSlop={8}>
                    <Text style={styles.lineupDone}>Done</Text>
                  </Pressable>
                </View>
              </View>
            ))
          )}
            </>
          )}
        </Card>
      )}

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
          onPress={stripeReady ? handleViewDashboard : handleStripeOnboard}
          variant={stripeReady ? 'secondary' : 'primary'}
        />
      </Card>

      {/* Preferences */}
      <Card>
        <Text style={styles.sectionTitle}>Preferences</Text>
        <Pressable
          onPress={toggleSongRequired}
          disabled={savingSettings}
          style={styles.toggleRow}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.toggleLabel}>Require song request</Text>
            <Text style={styles.toggleDesc}>
              {songRequired
                ? 'Singers must enter a song when getting in line.'
                : 'Singers can get in line without picking a song.'}
            </Text>
          </View>
          <View style={[styles.toggleSwitch, songRequired && styles.toggleSwitchOn]}>
            <View style={[styles.toggleKnob, songRequired && styles.toggleKnobOn]} />
          </View>
        </Pressable>
      </Card>

      {/* Venues */}
      <View style={styles.sectionHeader}>
        <Text style={styles.sectionLabel}>Venues</Text>
        <Pressable onPress={() => router.push(`/kj/${kjId}/add-venue`)}>
          <Text style={styles.addLink}>+ add</Text>
        </Pressable>
      </View>
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
  lineupHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  refreshLink: { color: Colors.cyan, fontSize: 14, fontWeight: '600' },
  lineupVenueName: { color: Colors.textDim, fontSize: 13, marginBottom: Spacing.sm },
  lineupEmpty: { color: Colors.textDim, fontSize: 14, lineHeight: 20 },
  lineupRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.sm,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
  },
  lineupName: { color: Colors.text, fontSize: 15, fontWeight: '700' },
  lineupSong: { color: Colors.textDim, fontSize: 13, marginTop: 2 },
  lineupNoContact: { color: Colors.textMute, fontSize: 12, marginTop: 2 },
  lineupActions: { alignItems: 'flex-end', gap: 4 },
  lineupDone: { color: Colors.textMute, fontSize: 13, paddingVertical: 4 },
  sectionLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: Colors.textMute,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: Spacing.lg,
    marginBottom: Spacing.sm,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  addLink: {
    color: Colors.cyan,
    fontSize: 14,
    fontWeight: '700',
    marginTop: Spacing.lg,
    marginBottom: Spacing.sm,
  },
  noStripe: { color: Colors.textMute, fontSize: 14, marginBottom: Spacing.sm },
  venueName: { fontSize: 18, fontWeight: '700', color: Colors.text },
  venueCity: { fontSize: 14, color: Colors.pink, fontWeight: '600', marginTop: 2 },
  venueMeta: { flexDirection: 'row', flexWrap: 'wrap', marginTop: Spacing.sm },
  venueVibe: { color: Colors.textDim, fontSize: 13, marginTop: Spacing.sm, fontStyle: 'italic' },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    paddingVertical: Spacing.sm,
  },
  toggleLabel: {
    fontSize: 15,
    fontWeight: '600',
    color: Colors.text,
  },
  toggleDesc: {
    fontSize: 13,
    color: Colors.textMute,
    marginTop: 2,
  },
  toggleSwitch: {
    width: 44,
    height: 26,
    borderRadius: 13,
    backgroundColor: Colors.bg2,
    borderWidth: 1,
    borderColor: Colors.border,
    justifyContent: 'center',
    padding: 2,
  },
  toggleSwitchOn: {
    backgroundColor: Colors.cyan,
    borderColor: 'transparent',
  },
  toggleKnob: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: Colors.textMute,
    alignSelf: 'flex-start',
  },
  toggleKnobOn: {
    backgroundColor: '#fff',
    alignSelf: 'flex-end',
  },
});
