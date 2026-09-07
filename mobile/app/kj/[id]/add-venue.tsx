/**
 * KJ Add Venue — lets a KJ add a venue to their profile.
 * Route: /kj/[id]/add-venue
 *
 * Backend canonicalizes: if the venue already exists (fuzzy name +
 * location match), the KJ is linked to it. If it's new, a submission
 * is created (pending admin approval) with the KJ pre-linked.
 */

import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  TextInput,
  Alert,
} from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { api } from '../../../src/api';
import { Button, Card, Banner, Loading, NightsRow } from '../../../src/components';
import { AddressLookup } from '../../../src/address-lookup';
import { Colors, Radius, Spacing, TAP_HEIGHT, Typography } from '../../../src/theme';

export default function KJAddVenueScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const kjId = parseInt(id, 10);

  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [city, setCity] = useState('');
  // State + coordinates come from a picked address-lookup result; this form
  // has no state field of its own, so a pick is the only way they get set.
  const [stateCode, setStateCode] = useState('');
  const [pickedCoords, setPickedCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [nights, setNights] = useState<string[]>([]);
  const [startTime, setStartTime] = useState('20:00');
  const [endTime, setEndTime] = useState('00:00');
  const [phone, setPhone] = useState('');
  const [website, setWebsite] = useState('');
  const [vibe, setVibe] = useState('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ status: string; message: string } | null>(null);

  const toggleNight = (day: string) => {
    setNights((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
    );
  };

  const handleSubmit = async () => {
    if (!name.trim() || !address.trim() || !city.trim()) {
      setError('Name, address, and city are required');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.kjAddVenue(kjId, {
        name: name.trim(),
        address: address.trim(),
        city: city.trim(),
        karaoke_nights: nights,
        start_time: startTime,
        end_time: endTime,
        phone: phone.trim() || undefined,
        website: website.trim() || undefined,
        vibe: vibe.trim() || undefined,
        state: stateCode || undefined,
        lat: pickedCoords?.lat,
        lng: pickedCoords?.lng,
      });
      setResult({ status: res.status, message: res.message });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add venue');
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    const isLinked = result.status === 'linked';
    const isDupe = result.status === 'duplicate';
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Card>
          <Text style={styles.resultIcon}>{isLinked ? '✓' : isDupe ? '!' : '+'}</Text>
          <Text style={styles.resultTitle}>
            {isLinked ? 'Venue linked' : isDupe ? 'Already exists' : 'Submitted'}
          </Text>
          <Text style={styles.resultBody}>{result.message}</Text>
          <Button
            label="back to profile"
            onPress={() => router.back()}
            variant="secondary"
          />
          {!isDupe && (
            <Button
              label="add another"
              onPress={() => {
                setResult(null);
                setName(''); setAddress(''); setCity('');
                setNights([]); setPhone(''); setWebsite(''); setVibe('');
              }}
              variant="ghost"
            />
          )}
        </Card>
      </ScrollView>
    );
  }

  if (submitting) return <Loading label="Adding venue..." />;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        {error && <Banner message={error} variant="warn" />}

        <Text style={styles.pageTitle}>add a venue</Text>
        <Text style={styles.pageSub}>
          add a venue you perform at. if it already exists in thehopper, we'll
          link you to it. if it's new, it'll go to admin review.
        </Text>

        <Card>
          <Text style={styles.label}>venue name *</Text>
          <TextInput
            style={styles.input}
            placeholder="e.g. Coconuts on the Beach"
            placeholderTextColor={Colors.textMute}
            value={name}
            onChangeText={setName}
          />

          <AddressLookup
            city={city}
            onPick={(s) => {
              setAddress(s.address);
              setCity(s.city);
              setStateCode(s.state ?? '');
              setPickedCoords({ lat: s.lat, lng: s.lng });
            }}
          />

          <Text style={styles.label}>address *</Text>
          <TextInput
            style={styles.input}
            placeholder="123 main st"
            placeholderTextColor={Colors.textMute}
            value={address}
            onChangeText={(t) => {
              setAddress(t);
              // Hand-edited after picking — the coordinates no longer match.
              setPickedCoords(null);
            }}
          />

          <Text style={styles.label}>city *</Text>
          <TextInput
            style={styles.input}
            placeholder="cocoa beach"
            placeholderTextColor={Colors.textMute}
            value={city}
            onChangeText={setCity}
          />

          <Text style={styles.label}>karaoke nights</Text>
          <NightsRow nights={nights} onToggle={toggleNight} />

          <View style={styles.timeRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.label}>start</Text>
              <TextInput
                style={styles.input}
                placeholder="20:00"
                placeholderTextColor={Colors.textMute}
                value={startTime}
                onChangeText={setStartTime}
              />
            </View>
            <View style={{ flex: 1, marginLeft: Spacing.sm }}>
              <Text style={styles.label}>end</Text>
              <TextInput
                style={styles.input}
                placeholder="00:00"
                placeholderTextColor={Colors.textMute}
                value={endTime}
                onChangeText={setEndTime}
              />
            </View>
          </View>

          <Text style={styles.label}>venue phone (optional)</Text>
          <TextInput
            style={styles.input}
            placeholder="(321) 555-0100"
            placeholderTextColor={Colors.textMute}
            value={phone}
            onChangeText={setPhone}
            keyboardType="phone-pad"
          />

          <Text style={styles.label}>website (optional)</Text>
          <TextInput
            style={styles.input}
            placeholder="https://..."
            placeholderTextColor={Colors.textMute}
            value={website}
            onChangeText={setWebsite}
            keyboardType="url"
            autoCapitalize="none"
          />

          <Text style={styles.label}>vibe (optional)</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="beach bar, divey, packed on weekends..."
            placeholderTextColor={Colors.textMute}
            value={vibe}
            onChangeText={setVibe}
            multiline
            numberOfLines={2}
          />
        </Card>

        <Button label="add venue" onPress={handleSubmit} />
        <View style={{ height: 40 }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  scroll: { flex: 1 },
  content: { padding: Spacing.lg, paddingBottom: 100 },
  pageTitle: { ...Typography.title, color: Colors.text, marginBottom: 4 },
  pageSub: { color: Colors.textDim, fontSize: 14, marginBottom: Spacing.lg, lineHeight: 20 },
  label: {
    fontSize: 13,
    fontWeight: '700',
    color: Colors.textMute,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: Spacing.md,
    marginBottom: 4,
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
  },
  textArea: { minHeight: 80, paddingVertical: 10 },
  timeRow: { flexDirection: 'row' },
  resultIcon: { fontSize: 48, textAlign: 'center', marginBottom: Spacing.sm },
  resultTitle: { ...Typography.title, color: Colors.text, textAlign: 'center', marginBottom: Spacing.sm },
  resultBody: { color: Colors.textDim, fontSize: 15, textAlign: 'center', marginBottom: Spacing.lg, lineHeight: 22 },
});
