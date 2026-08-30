import { useEffect, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
  Alert,
} from 'react-native';
import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { getSessionToken, setSessionToken } from '../../src/session';
import { api, API_BASE } from '../../src/api';
import { useKJContext } from '../../src/kj-context';
import type { KJ } from '../../src/types';
import {
  Banner,
  Button,
  Card,
  Loading,
} from '../../src/components';
import { Colors, Radius, Spacing, TAP_HEIGHT, Typography } from '../../src/theme';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/**
 * Mirror of the backend's normalize_phone, used only to decide whether the KJ
 * actually changed their number. Comparing raw strings would treat
 * "(321) 555-0100" and "+13215550100" as different and demand a pointless
 * re-verification of the number already on file.
 */
function normalizePhone(phone: string): string {
  const digits = phone.replace(/\D/g, '');
  if (digits.length === 10) return `+1${digits}`;
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`;
  if (digits.startsWith('1') && digits.length > 11) return `+${digits}`;
  return digits ? `+${digits}` : phone;
}

export default function AddSpotScreen() {
  // Venue fields
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [city, setCity] = useState('');
  const [nights, setNights] = useState<string[]>([]);
  const [startTime, setStartTime] = useState('20:00');
  const [endTime, setEndTime] = useState('00:00');
  const [phone, setPhone] = useState('');
  const [website, setWebsite] = useState('');
  const [instagram, setInstagram] = useState('');
  const [vibe, setVibe] = useState('');

  // KJ fields
  const [isKJ, setIsKJ] = useState(false);
  const [kjName, setKJName] = useState('');
  const [submitterPhone, setSubmitterPhone] = useState('');
  const [kjBio, setKJBio] = useState(''); // kept for profile later, not in form
  const [kjInstagram, setKJInstagram] = useState('');
  const [kjWebsite, setKJWebsite] = useState('');

  // Phone verification
  const [phoneVerified, setPhoneVerified] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [code, setCode] = useState('');
  const [verifying, setVerifying] = useState(false);

  // Existing KJ profile (this device has already onboarded someone). When set,
  // the KJ block becomes an edit form rather than a verification flow.
  const [existingKJ, setExistingKJ] = useState<KJ | null>(null);
  const { kj: contextKJ, loading: kjLoading, setKJ: setContextKJ } = useKJContext();
  const [lookingUpKJ, setLookingUpKJ] = useState(true);
  const [sessionToken, setToken] = useState<string | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileNotice, setProfileNotice] = useState<string | null>(null);
  // Proof the KJ controls the number they are moving to. Required by the API
  // before an existing profile's phone can be changed.
  const [newPhoneToken, setNewPhoneToken] = useState<string | null>(null);

  // Submission
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [kjResult, setKJResult] = useState<KJ | null>(null);

  const scrollRef = useRef<ScrollView>(null);

  // Whether this device already belongs to an onboarded KJ comes from the
  // shared context — the provider resolves it once at startup, so this screen
  // does not repeat the lookup. Prefill the edit fields when it arrives.
  useEffect(() => {
    if (kjLoading) return;
    setLookingUpKJ(false);
    if (contextKJ) {
      setExistingKJ(contextKJ);
      setKJName(contextKJ.name);
      setSubmitterPhone(contextKJ.phone);
      setPhoneVerified(true);
    }
  }, [contextKJ, kjLoading]);

  // The session token authorises profile edits, so it is still read directly.
  useEffect(() => {
    getSessionToken().then(setToken).catch(() => setToken(null));
  }, []);

  const toggleNight = (day: string) => {
    setNights((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
    );
  };

  // True once the KJ has typed a number different from the one on file.
  const phoneChanged =
    existingKJ != null &&
    normalizePhone(submitterPhone) !== normalizePhone(existingKJ.phone);

  const handleSendNewPhoneCode = async () => {
    if (!submitterPhone.trim()) {
      setError('Enter the new phone number first');
      return;
    }
    setError(null);
    setProfileNotice(null);
    try {
      await api.sendPhoneCode(submitterPhone);
      setCodeSent(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send code');
    }
  };

  const handleVerifyNewPhone = async () => {
    if (!code.trim()) {
      setError('Enter the 6-digit code');
      return;
    }
    setError(null);
    setVerifying(true);
    try {
      const res = await api.verifyPhone(submitterPhone, code);
      if (res.verified && res.token) {
        setNewPhoneToken(res.token);
        setCodeSent(false);
        setCode('');
        setProfileNotice('New number verified — save to apply it.');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Verification failed. Try sending a new code.');
    } finally {
      setVerifying(false);
    }
  };

  const handleSaveProfile = async () => {
    if (!existingKJ || !sessionToken) return;
    if (!kjName.trim()) {
      setError('Stage name cannot be empty');
      return;
    }
    if (phoneChanged && !newPhoneToken) {
      setError('Verify the new number before saving');
      return;
    }
    setError(null);
    setProfileNotice(null);
    setSavingProfile(true);
    try {
      const updated = await api.updateKJProfile(existingKJ.id, sessionToken, {
        name: kjName.trim(),
        ...(phoneChanged
          ? { phone: submitterPhone.trim(), new_phone_token: newPhoneToken! }
          : {}),
      });
      setExistingKJ(updated);
      setContextKJ(updated); // keep the My KJ tab in step with the edit
      setKJName(updated.name);
      setSubmitterPhone(updated.phone);
      // Moving the number invalidates the old token server-side; the one that
      // proved the new number becomes this device's session.
      if (phoneChanged && newPhoneToken) {
        await setSessionToken(newPhoneToken);
        setToken(newPhoneToken);
      }
      setNewPhoneToken(null);
      setProfileNotice('Profile updated.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save your profile');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleSendCode = async () => {
    if (!submitterPhone.trim()) {
      setError('Enter your phone number first');
      return;
    }
    setError(null);
    try {
      await api.sendPhoneCode(submitterPhone);
      setCodeSent(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send code');
    }
  };

  const handleVerifyCode = async () => {
    if (!code.trim()) {
      setError('Enter the 6-digit code');
      return;
    }
    setError(null);
    setVerifying(true);
    try {
      const res = await api.verifyPhone(submitterPhone, code);
      if (res.verified && res.token) {
        await setSessionToken(res.token);
        setToken(res.token);
        setPhoneVerified(true);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Verification failed. Try sending a new code.');
    } finally {
      setVerifying(false);
    }
  };

  const handleResendCode = async () => {
    setError(null);
    setCode('');
    setCodeSent(false);
    await handleSendCode();
  };

  const handleSubmit = async () => {
    if (!name.trim() || !address.trim() || !city.trim()) {
      setError('Name, address, and city are required');
      return;
    }
    if (isKJ && !phoneVerified) {
      setError('Verify your phone number to continue as KJ');
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const res = await api.submitVenue({
        name: name.trim(),
        address: address.trim(),
        city: city.trim(),
        karaoke_nights: nights,
        start_time: startTime,
        end_time: endTime,
        // For a returning KJ use the values actually saved on the profile, not
        // whatever is currently typed — an unsaved phone edit has not been
        // verified, and must not ride along on the venue submission.
        kj_name: isKJ ? (existingKJ ? existingKJ.name : kjName.trim()) : undefined,
        phone: phone.trim() || undefined,
        website: website.trim() || undefined,
        instagram: instagram.trim() || undefined,
        vibe: vibe.trim() || undefined,
        is_kj: isKJ,
        submitter_phone: isKJ
          ? (existingKJ ? existingKJ.phone : submitterPhone.trim())
          : undefined,
      });
      setSuccess(res.message);

      // If KJ, register them. A returning KJ is already registered — sending
      // them through /kjs/register again would just re-upsert the row, and
      // pushing an already-connected KJ back into Stripe onboarding is wrong,
      // so only surface that step when they still need it.
      if (isKJ && existingKJ) {
        const connected =
          existingKJ.stripe_onboarding_status === 'active' ||
          existingKJ.stripe_onboarding_status === 'pending_verification';
        if (!connected) setKJResult(existingKJ);
      } else if (isKJ && phoneVerified) {
        try {
          const kj = await api.registerKJ({
            name: kjName.trim() || name.trim(),
            phone: submitterPhone.trim(),
            bio: kjBio.trim() || undefined,
            instagram: kjInstagram.trim() || undefined,
            website: kjWebsite.trim() || undefined,
          });
          setKJResult(kj);
          // Reveals the My KJ tab straight away — without this a brand new
          // host would have to restart the app to find their dashboard.
          setContextKJ(kj);
        } catch {
          // KJ registration failed but venue submission went through
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleStripeOnboard = async (email: string) => {
    if (!kjResult) return;
    try {
      const res = await api.kjStripeOnboard(kjResult.id, email);
      let url = res.onboarding_url;
      if (url.startsWith('/')) {
        url = `${API_BASE.replace(/\/api$/, '')}${url}`;
      }
      await WebBrowser.openBrowserAsync(url);
    } catch (e) {
      Alert.alert('Error', e instanceof Error ? e.message : 'Stripe onboarding failed');
    }
  };

  if (success && !kjResult) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Card>
          <Text style={styles.successIcon}>🎉</Text>
          <Text style={styles.successTitle}>Submission received!</Text>
          <Text style={styles.successBody}>{success}</Text>
          <Button label="Back to Venues" onPress={() => router.push('/(tabs)/index')} />
        </Card>
      </ScrollView>
    );
  }

  if (kjResult) {
    return (
      <KJOnboardingResult
        kj={kjResult}
        onStripeOnboard={handleStripeOnboard}
        // Land a new host on their own dashboard rather than the venue list —
        // that is where the pending singers list lives.
        onDone={() => router.push('/(tabs)/kj')}
      />
    );
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        ref={scrollRef}
        style={styles.container}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.pageTitle}>Add a Karaoke Spot</Text>
        <Text style={styles.pageSub}>
          Know a bar that does karaoke? Add it to TheHopper so singers can find it.
        </Text>

        {error && <Banner message={`⚠️ ${error}`} variant="warn" />}

        {/* Venue info */}
        <Text style={styles.sectionLabel}>Venue Info</Text>
        <Card>
          <Text style={styles.fieldLabel}>Venue name *</Text>
          <TextInput
            style={styles.input}
            placeholder="e.g. Coconuts on the Beach"
            placeholderTextColor={Colors.textMute}
            value={name}
            onChangeText={setName}
          />

          <Text style={styles.fieldLabel}>Address *</Text>
          <TextInput
            style={styles.input}
            placeholder="123 Main St, Cocoa Beach"
            placeholderTextColor={Colors.textMute}
            value={address}
            onChangeText={setAddress}
          />

          <Text style={styles.fieldLabel}>City *</Text>
          <TextInput
            style={styles.input}
            placeholder="Cocoa Beach"
            placeholderTextColor={Colors.textMute}
            value={city}
            onChangeText={setCity}
          />

          <Text style={styles.fieldLabel}>Karaoke nights</Text>
          <View style={styles.nightsRow}>
            {DAYS.map((day) => (
              <Pressable
                key={day}
                onPress={() => toggleNight(day)}
                style={({ pressed }) => [
                  styles.dayChip,
                  nights.includes(day) && styles.dayChipActive,
                  pressed && styles.dayChipPressed,
                ]}
              >
                <Text
                  style={[
                    styles.dayChipText,
                    nights.includes(day) && styles.dayChipTextActive,
                  ]}
                >
                  {day.slice(0, 3)}
                </Text>
              </Pressable>
            ))}
          </View>

          <View style={styles.timeRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.fieldLabel}>Start</Text>
              <TextInput
                style={styles.input}
                placeholder="20:00"
                placeholderTextColor={Colors.textMute}
                value={startTime}
                onChangeText={setStartTime}
              />
            </View>
            <View style={{ flex: 1, marginLeft: Spacing.sm }}>
              <Text style={styles.fieldLabel}>End</Text>
              <TextInput
                style={styles.input}
                placeholder="00:00"
                placeholderTextColor={Colors.textMute}
                value={endTime}
                onChangeText={setEndTime}
              />
            </View>
          </View>

          <Text style={styles.fieldLabel}>Venue Contact Phone (optional)</Text>
          <TextInput
            style={styles.input}
            placeholder="(321) 555-0100"
            placeholderTextColor={Colors.textMute}
            value={phone}
            onChangeText={setPhone}
            keyboardType="phone-pad"
          />

          <Text style={styles.fieldLabel}>Website (optional)</Text>
          <TextInput
            style={styles.input}
            placeholder="https://..."
            placeholderTextColor={Colors.textMute}
            value={website}
            onChangeText={setWebsite}
            keyboardType="url"
            autoCapitalize="none"
          />

          <Text style={styles.fieldLabel}>Instagram (optional)</Text>
          <TextInput
            style={styles.input}
            placeholder="@venue_handle"
            placeholderTextColor={Colors.textMute}
            value={instagram}
            onChangeText={setInstagram}
            autoCapitalize="none"
          />

          <Text style={styles.fieldLabel}>Vibe (optional)</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="Beach bar, divey, packed on weekends..."
            placeholderTextColor={Colors.textMute}
            value={vibe}
            onChangeText={setVibe}
            multiline
            numberOfLines={2}
          />
        </Card>

        {/* KJ toggle */}
        <Card style={styles.toggleCard}>
          <View style={styles.toggleRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.toggleTitle}>I'm the KJ</Text>
              <Text style={styles.toggleSub}>
                Onboard as a karaoke host, promote yourself, and get paid for premium slots.
              </Text>
            </View>
            <Switch
              value={isKJ}
              onValueChange={setIsKJ}
              trackColor={{ false: Colors.border, true: Colors.pink }}
              thumbColor={isKJ ? '#fff' : Colors.textMute}
            />
          </View>
        </Card>

        {/* KJ fields */}
        {isKJ && lookingUpKJ && <Loading label="Checking your KJ profile..." />}

        {/* Returning KJ — show what we have on file and let them edit it. */}
        {isKJ && !lookingUpKJ && existingKJ && (
          <View>
            <Text style={styles.sectionLabel}>Your KJ Profile</Text>
            <Card>
              <Text style={styles.profileHint}>
                You're already onboarded as a KJ. Update your details below.
              </Text>

              <Text style={styles.fieldLabel}>Your name / stage name</Text>
              <TextInput
                style={styles.input}
                placeholder="DJ Salty Mike"
                placeholderTextColor={Colors.textMute}
                value={kjName}
                onChangeText={(v) => {
                  setKJName(v);
                  setProfileNotice(null);
                }}
              />

              <Text style={styles.fieldLabel}>Your phone number</Text>
              <TextInput
                style={styles.input}
                placeholder="(321) 555-0100"
                placeholderTextColor={Colors.textMute}
                value={submitterPhone}
                onChangeText={(v) => {
                  setSubmitterPhone(v);
                  setProfileNotice(null);
                  // Any further edit invalidates a code already sent or a
                  // number already proved.
                  setNewPhoneToken(null);
                  setCodeSent(false);
                  setCode('');
                }}
                keyboardType="phone-pad"
              />

              {/* Changing the number re-keys the account, so prove the new one. */}
              {phoneChanged && !newPhoneToken && (
                <View style={styles.verifyBlock}>
                  {!codeSent ? (
                    <>
                      <Text style={styles.profileHint}>
                        Changing your number needs a quick text to confirm it's yours.
                      </Text>
                      <Button
                        label="Send code to new number"
                        onPress={handleSendNewPhoneCode}
                        variant="secondary"
                      />
                    </>
                  ) : (
                    <View>
                      <Text style={styles.fieldLabel}>Enter the code we sent you</Text>
                      <View style={styles.codeRow}>
                        <TextInput
                          style={[styles.input, { flex: 1 }]}
                          placeholder="123456"
                          placeholderTextColor={Colors.textMute}
                          value={code}
                          onChangeText={setCode}
                          keyboardType="number-pad"
                          maxLength={6}
                        />
                        <Button
                          label={verifying ? '...' : 'Verify'}
                          onPress={handleVerifyNewPhone}
                          variant="cyan"
                          style={styles.verifyBtn}
                        />
                      </View>
                      <Button
                        label="Resend code"
                        onPress={handleSendNewPhoneCode}
                        variant="secondary"
                        style={{ marginTop: 8 }}
                      />
                    </View>
                  )}
                </View>
              )}

              {profileNotice && <Banner message={profileNotice} variant="ok" />}

              <Button
                label={savingProfile ? 'Saving...' : 'Save changes'}
                onPress={handleSaveProfile}
                disabled={savingProfile || (phoneChanged && !newPhoneToken)}
                style={{ marginTop: Spacing.md }}
              />
            </Card>
          </View>
        )}

        {/* New KJ — the original verification flow. */}
        {isKJ && !lookingUpKJ && !existingKJ && (
          <View>
            <Text style={styles.sectionLabel}>KJ Onboarding</Text>
            <Card>
              <Text style={styles.fieldLabel}>Your name / stage name</Text>
              <TextInput
                style={styles.input}
                placeholder="DJ Salty Mike"
                placeholderTextColor={Colors.textMute}
                value={kjName}
                onChangeText={setKJName}
              />

              <Text style={styles.fieldLabel}>Your phone number</Text>
              <TextInput
                style={styles.input}
                placeholder="(321) 555-0100"
                placeholderTextColor={Colors.textMute}
                value={submitterPhone}
                onChangeText={setSubmitterPhone}
                keyboardType="phone-pad"
              />

              {/* Phone verification */}
              {!phoneVerified && (
                <View style={styles.verifyBlock}>
                  {!codeSent ? (
                    <Button
                      label="Send verification code"
                      onPress={handleSendCode}
                      variant="secondary"
                    />
                  ) : (
                    <View>
                      <Text style={styles.fieldLabel}>Enter the code we sent you</Text>
                      <View style={styles.codeRow}>
                        <TextInput
                          style={[styles.input, { flex: 1 }]}
                          placeholder="123456"
                          placeholderTextColor={Colors.textMute}
                          value={code}
                          onChangeText={setCode}
                          keyboardType="number-pad"
                          maxLength={6}
                        />
                        <Button
                          label={verifying ? '...' : 'Verify'}
                          onPress={handleVerifyCode}
                          variant="cyan"
                          style={styles.verifyBtn}
                        />
                      </View>
                      {error && (
                        <Button
                          label="Resend code"
                          onPress={handleResendCode}
                          variant="secondary"
                          style={{ marginTop: 8 }}
                        />
                      )}
                    </View>
                  )}
                </View>
              )}
              {phoneVerified && (
                <Banner message="Phone verified!" variant="ok" />
              )}
            </Card>
          </View>
        )}

        {submitting && <Loading label="Submitting..." />}

        <Button
          label={submitting ? 'Submitting...' : 'Submit Spot'}
          onPress={handleSubmit}
          disabled={submitting}
        />

        <View style={{ height: 40 }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

// --- KJ Onboarding Result (after venue submission) ---

function KJOnboardingResult({
  kj,
  onStripeOnboard,
  onDone,
}: {
  kj: KJ;
  onStripeOnboard: (email: string) => void;
  onDone: () => void;
}) {
  const [email, setEmail] = useState('');
  const [stripeStarted, setStripeStarted] = useState(false);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Card>
        <Text style={styles.successIcon}>🎤</Text>
        <Text style={styles.successTitle}>Welcome, {kj.name}!</Text>
        <Text style={styles.successBody}>
          Your spot is pending approval. In the meantime, set up Stripe to get paid for premium slots.
        </Text>

        <Text style={styles.fieldLabel}>Email for Stripe</Text>
        <TextInput
          style={styles.input}
          placeholder="you@example.com"
          placeholderTextColor={Colors.textMute}
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          autoCapitalize="none"
        />

        <Button
          label={stripeStarted ? 'Opening Stripe...' : 'Set up Stripe payments'}
          onPress={() => {
            if (!email.trim()) return;
            setStripeStarted(true);
            onStripeOnboard(email);
          }}
          disabled={stripeStarted || !email.trim()}
        />

        <View style={{ height: Spacing.md }} />

        <Button
          label="Skip for now"
          onPress={onDone}
          variant="ghost"
        />
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  content: { padding: Spacing.lg, paddingBottom: 100 },
  pageTitle: { ...Typography.title, color: Colors.text, marginBottom: 4 },
  pageSub: { color: Colors.textDim, fontSize: 14, marginBottom: Spacing.lg },
  sectionLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: Colors.textMute,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: Spacing.lg,
    marginBottom: Spacing.sm,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.textDim,
    marginTop: Spacing.sm,
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
  textArea: {
    minHeight: 80,
    paddingVertical: 10,
  },
  nightsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 4,
  },
  dayChip: {
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.bg2,
    borderRadius: Radius.pill,
    paddingHorizontal: 14,
    paddingVertical: 10,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dayChipActive: {
    backgroundColor: Colors.pink,
    borderColor: 'transparent',
  },
  dayChipPressed: { opacity: 0.85 },
  dayChipText: { color: Colors.textDim, fontSize: 14, fontWeight: '600' },
  dayChipTextActive: { color: '#fff', fontWeight: '700' },
  timeRow: { flexDirection: 'row' },
  toggleCard: { marginTop: Spacing.md },
  toggleRow: { flexDirection: 'row', alignItems: 'center', gap: Spacing.md },
  toggleTitle: { fontSize: 18, fontWeight: '800', color: Colors.text },
  toggleSub: { fontSize: 13, color: Colors.textDim, marginTop: 2 },
  profileHint: {
    color: Colors.textDim,
    fontSize: 13,
    lineHeight: 19,
    marginBottom: Spacing.sm,
  },
  verifyBlock: { marginTop: Spacing.sm },
  codeRow: { flexDirection: 'row', gap: Spacing.sm, alignItems: 'center' },
  verifyBtn: { minWidth: 100 },
  successIcon: { fontSize: 48, textAlign: 'center', marginBottom: Spacing.sm },
  successTitle: { ...Typography.title, color: Colors.text, textAlign: 'center', marginBottom: Spacing.sm },
  successBody: { color: Colors.textDim, fontSize: 15, textAlign: 'center', marginBottom: Spacing.lg, lineHeight: 22 },
});
