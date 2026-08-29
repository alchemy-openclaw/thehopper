/**
 * Stripe Onboarding Form — collects KYC prefill data and a business name,
 * then kicks off Stripe Connect onboarding via the backend.
 * Route: /kj/[id]/onboard
 */

import { useState, useEffect } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
  TextInput,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { api } from '../../../src/api';
import type { KJ } from '../../../src/types';
import { Button, Card, Banner, Loading } from '../../../src/components';
import { Colors, Spacing, Typography } from '../../../src/theme';

export default function StripeOnboardScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const kjId = parseInt(id, 10);

  const [kj, setKJ] = useState<KJ | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form fields
  const [email, setEmail] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [kjWebsite, setKjWebsite] = useState('');
  const [kjCity, setKjCity] = useState('');
  const [dob, setDob] = useState(''); // MM/DD/YYYY
  const [address, setAddress] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [zip, setZip] = useState('');
  const [ssn4, setSsn4] = useState('');

  useEffect(() => {
    if (!kjId) return;
    api.getKJ(kjId)
      .then((data) => {
        setKJ(data);
        setBusinessName(data.business_name || data.name || '');
        setKjWebsite(data.website || '');
        setKjCity(data.city || '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load KJ'))
      .finally(() => setLoading(false));
  }, [kjId]);

  const handleSubmit = async () => {
    if (!email.trim()) {
      setError('Email is required');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      // If the KJ provided a website, update their profile first
      // so the backend uses it as business_profile.url
      if (kjWebsite.trim() && kjWebsite.trim() !== kj?.website) {
        await api.registerKJ({
          name: kj?.name || '',
          phone: kj?.phone || '',
          website: kjWebsite.trim(),
          business_name: businessName.trim() || undefined,
          city: kjCity.trim() || undefined,
        });
      }

      // Parse DOB if provided
      let dob_day: number | undefined;
      let dob_month: number | undefined;
      let dob_year: number | undefined;
      if (dob.trim()) {
        const parts = dob.split('/').map((s) => parseInt(s.trim(), 10));
        if (parts.length === 3 && parts.every((n) => !isNaN(n))) {
          dob_month = parts[0];
          dob_day = parts[1];
          dob_year = parts[2];
        }
      }

      const res = await api.kjStripeOnboard(kjId, email.trim(), {
        business_name: businessName.trim() || undefined,
        dob_day,
        dob_month,
        dob_year,
        address_line1: address.trim() || undefined,
        address_city: city.trim() || undefined,
        address_state: state.trim() || undefined,
        address_postal_code: zip.trim() || undefined,
        ssn_last_4: ssn4.trim() || undefined,
      });

      let url = res.onboarding_url;
      if (url.startsWith('/')) {
        url = `https://thehopper.alchemycreativelounge.com${url}`;
      }
      await WebBrowser.openBrowserAsync(url);
      router.back();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Stripe onboarding failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <Loading label="Loading..." />;

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

        <Card>
          <Text style={styles.sectionTitle}>stripe setup</Text>
          <Text style={styles.helper}>
            we'll create a simple business page for stripe verification (or use
            your existing website if you have one), then send you to stripe to
            finish onboarding. fill in what you can — anything you skip, stripe
            will ask for directly.
          </Text>
        </Card>

        <Card>
          <Text style={styles.label}>email *</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            placeholder="you@example.com"
            placeholderTextColor={Colors.textMute}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
          />

          <Text style={styles.label}>business name</Text>
          <TextInput
            style={styles.input}
            value={businessName}
            onChangeText={setBusinessName}
            placeholder="e.g. mike's karaoke nights"
            placeholderTextColor={Colors.textMute}
          />
          <Text style={styles.hint}>
            this becomes the name on your public business page and stripe
            account. defaults to your name if left blank.
          </Text>

          <Text style={styles.label}>your website</Text>
          <TextInput
            style={styles.input}
            value={kjWebsite}
            onChangeText={setKjWebsite}
            placeholder="https://mikeskaraoke.com"
            placeholderTextColor={Colors.textMute}
            keyboardType="url"
            autoCapitalize="none"
          />
          {kjWebsite.trim() ? (
            <Text style={styles.hint}>
              stripe will verify your business through this site. make sure it
              shows your name and what you do.
            </Text>
          ) : (
            <Text style={styles.hintImportant}>
              if you have your own website, enter it here. stripe requires a
              public business page to verify your account. if you don't have
              one, we'll generate one for you at karaokespot.us — but your own
              site is better if you have it.
            </Text>
          )}

          <Text style={styles.label}>home city</Text>
          <TextInput
            style={styles.input}
            value={kjCity}
            onChangeText={setKjCity}
            placeholder="e.g. cocoa beach"
            placeholderTextColor={Colors.textMute}
          />
          <Text style={styles.hint}>
            shown on your public site as "centered in {kjCity || 'your city'}, fl".
          </Text>
        </Card>

        <Card>
          <Text style={styles.sectionTitle}>identity (optional)</Text>
          <Text style={styles.helper}>
            prefilling these speeds up stripe's form. you can skip them and
            fill everything on stripe's hosted page instead.
          </Text>

          <Text style={styles.label}>date of birth</Text>
          <TextInput
            style={styles.input}
            value={dob}
            onChangeText={setDob}
            placeholder="MM/DD/YYYY"
            placeholderTextColor={Colors.textMute}
            keyboardType="numeric"
          />

          <Text style={styles.label}>street address</Text>
          <TextInput
            style={styles.input}
            value={address}
            onChangeText={setAddress}
            placeholder="123 main st"
            placeholderTextColor={Colors.textMute}
          />

          <View style={styles.row}>
            <View style={styles.flex2}>
              <Text style={styles.label}>city</Text>
              <TextInput
                style={styles.input}
                value={city}
                onChangeText={setCity}
                placeholder="melbourne"
                placeholderTextColor={Colors.textMute}
              />
            </View>
            <View style={styles.flex1}>
              <Text style={styles.label}>state</Text>
              <TextInput
                style={styles.input}
                value={state}
                onChangeText={setState}
                placeholder="FL"
                placeholderTextColor={Colors.textMute}
                maxLength={2}
                autoCapitalize="characters"
              />
            </View>
          </View>

          <Text style={styles.label}>zip code</Text>
          <TextInput
            style={styles.input}
            value={zip}
            onChangeText={setZip}
            placeholder="32901"
            placeholderTextColor={Colors.textMute}
            keyboardType="numeric"
            maxLength={10}
          />

          <Text style={styles.label}>last 4 of ssn</Text>
          <TextInput
            style={styles.input}
            value={ssn4}
            onChangeText={setSsn4}
            placeholder="1234"
            placeholderTextColor={Colors.textMute}
            keyboardType="numeric"
            maxLength={4}
            secureTextEntry
          />
        </Card>

        <Button label={submitting ? 'Opening stripe...' : 'continue to stripe'} onPress={handleSubmit} disabled={submitting} />

        <View style={{ height: 40 }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  scroll: { flex: 1 },
  content: { padding: Spacing.lg, paddingBottom: 100 },
  sectionTitle: {
    ...Typography.heading,
    color: Colors.text,
    marginBottom: Spacing.sm,
  },
  helper: {
    color: Colors.textDim,
    fontSize: 14,
    lineHeight: 20,
  },
  label: {
    fontSize: 13,
    fontWeight: '700',
    color: Colors.textMute,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: Spacing.md,
    marginBottom: 4,
  },
  hint: {
    color: Colors.textMute,
    fontSize: 12,
    lineHeight: 16,
    marginTop: 4,
  },
  hintImportant: {
    color: Colors.yellow,
    fontSize: 12,
    lineHeight: 16,
    marginTop: 4,
    fontWeight: '600',
  },
  input: {
    backgroundColor: Colors.bg2,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
    color: Colors.text,
    fontSize: 16,
    minHeight: 48,
  },
  row: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  flex2: { flex: 2 },
  flex1: { flex: 1 },
});
