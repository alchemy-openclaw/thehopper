import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
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
import * as WebBrowser from 'expo-web-browser';
import * as LinkingExpo from 'expo-linking';
import type { AppConfig, ChatMessage, Venue } from '../../src/types';
import { api, API_BASE } from '../../src/api';
import { isEventActive } from '../../src/event-window';
import { useVenueContext } from '../../src/venue-context';
import { usePrefsContext } from '../../src/prefs-context';
import {
  Banner,
  Button,
  Card,
  EmptyState,
  Loading,
  MetaPill,
} from '../../src/components';
import { Colors, Radius, Spacing, TAP_HEIGHT, Typography } from '../../src/theme';

export default function EventScreen() {
  const { selectedVenue } = useVenueContext();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [showPay, setShowPay] = useState(false);
  const [showTip, setShowTip] = useState(false);
  const [showMessage, setShowMessage] = useState(false);
  const [showLineup, setShowLineup] = useState(false);

  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  // Handle deep link redirects from Stripe checkout (thehopper://payment-success|payment-cancelled)
  useEffect(() => {
    const handleDeepLink = (url: string | null) => {
      if (!url) return;
      let parsed: { path?: string; queryParams?: Record<string, string> };
      try {
        parsed = LinkingExpo.parse(url);
      } catch {
        return;
      }
      const path = parsed.path || '';
      const params = parsed.queryParams || {};
      if (path === 'payment-success') {
        WebBrowser.dismissBrowser();
        Alert.alert(
          'Payment Received',
          'Your premium slot request has been sent to the KJ. They\'ll confirm your position.',
        );
      } else if (path === 'payment-cancelled') {
        WebBrowser.dismissBrowser();
        Alert.alert('Payment Cancelled', 'No charge was made.');
      }
    };

    // Check if app was opened from a deep link
    Linking.getInitialURL().then(handleDeepLink);

    // Listen for deep links while app is open
    const sub = Linking.addEventListener('url', ({ url }) => handleDeepLink(url));
    return () => sub.remove();
  }, []);

  if (!selectedVenue) {
    return (
      <ScrollView
        style={styles.container}
        contentContainerStyle={styles.content}
      >
        <EmptyState
          icon="🎤"
          message="No venue selected yet. Go to the Find tab and tap a venue to see its event."
        />
      </ScrollView>
    );
  }

  const venue = selectedVenue;
  const eventActive = isEventActive(venue);

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 88 : 0}
    >
      {/* Venue header (compact — matches venue list style) */}
      <Card style={styles.headerCard}>
        <View style={styles.venueHeaderRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.venueName}>{venue.name}</Text>
            <Text style={styles.venueCity}>{venue.city}</Text>
          </View>
        </View>
        <View style={styles.venueMeta}>
          {venue.karaoke_nights.map((n) => (
            <MetaPill key={n} label={n} variant="nights" />
          ))}
          <MetaPill label={`🕘 ${venue.start_time}–${venue.end_time}`} />
          {venue.kj_name && <MetaPill label={`KJ: ${venue.kj_name}`} />}
        </View>
        {venue.vibe ? <Text style={styles.venueVibe}>{venue.vibe}</Text> : null}
        {!config?.stripe_configured && (
          <Text style={styles.testModeNote}>
            Test mode — no real charges will be made.
          </Text>
        )}
      </Card>

      {eventActive ? (
        <>
          {/* Chat fills the remaining space */}
          <View style={styles.chatSection}>
            <ChatPanel venue={venue} />
          </View>

          {/* Action buttons anchored at bottom */}
          <View style={styles.actionBar}>
            <Pressable
              onPress={() => setShowLineup(true)}
              style={({ pressed }) => [styles.subtleBtn, styles.subtleBtnLineup, pressed && styles.subtleBtnPressed]}
            >
              <Text style={styles.subtleBtnText}>
                🎤 Get In Line
              </Text>
            </Pressable>
            <Pressable
              onPress={() => setShowPay(true)}
              style={({ pressed }) => [styles.subtleBtn, pressed && styles.subtleBtnPressed]}
            >
              <Text style={styles.subtleBtnText}>
                ⏭️ Jump Queue · ${venue.price_jump_queue.toFixed(2)}
              </Text>
            </Pressable>
            <Pressable
              onPress={() => setShowTip(true)}
              style={({ pressed }) => [styles.subtleBtn, styles.subtleBtnTip, pressed && styles.subtleBtnPressed]}
            >
              <Text style={styles.subtleBtnText}>
                💰 Tip KJ
              </Text>
            </Pressable>
          </View>
        </>
      ) : (
        /* Outside event window: show Tip KJ and Message KJ */
        <View style={styles.offEventSection}>
          <Text style={styles.offEventText}>
            No live event right now. Karaoke nights: {venue.karaoke_nights.join(', ')}.
          </Text>
          <Pressable
            onPress={() => setShowTip(true)}
            style={({ pressed }) => [styles.subtleBtn, styles.subtleBtnTip, pressed && styles.subtleBtnPressed]}
          >
            <Text style={styles.subtleBtnText}>💰 Tip KJ</Text>
          </Pressable>
          <Pressable
            onPress={() => setShowMessage(true)}
            style={({ pressed }) => [styles.subtleBtn, pressed && styles.subtleBtnPressed]}
          >
            <Text style={styles.subtleBtnText}>✉️ Message KJ</Text>
          </Pressable>
        </View>
      )}

      {/* Modals */}
      <PaymentModal
        venue={venue}
        stripeConfigured={config?.stripe_configured ?? false}
        visible={showPay}
        onClose={() => setShowPay(false)}
      />
      <TipModal
        venue={venue}
        stripeConfigured={config?.stripe_configured ?? false}
        visible={showTip}
        onClose={() => setShowTip(false)}
      />
      <MessageKJModal
        venue={venue}
        visible={showMessage}
        onClose={() => setShowMessage(false)}
      />
      <GetInLineModal
        venue={venue}
        visible={showLineup}
        onClose={() => setShowLineup(false)}
      />
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------------------
// Chat panel — inline (not a modal) on the Event tab
// ---------------------------------------------------------------------------

function ChatPanel({ venue }: { venue: Venue }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [nickname, setNickname] = useState('');
  const [draft, setDraft] = useState('');
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const scrollRef = useRef<ScrollView>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setMessages([]);

    // Load history via REST
    api.getVenueChat(venue.id).then((msgs) => {
      if (cancelled) return;
      setMessages(msgs);
      setLoading(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 50);
    }).catch(() => {
      if (cancelled) return;
      setLoading(false);
    });

    // Open WebSocket for live messages
    // Derive WS URL from API_BASE (http→ws, https→wss)
    const wsBase = API_BASE.replace(/^http/, 'ws').replace(/\/api$/, '');
    const wsUrl = `${wsBase}/api/venues/${venue.id}/ws`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (cancelled) return;
      setConnected(true);
    };

    ws.onmessage = (event) => {
      if (cancelled) return;
      try {
        const data = JSON.parse(event.data as string);
        if (data.type === 'error') return;
        setMessages((prev) => [...prev, data]);
        setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 50);
      } catch {
        // ignore malformed
      }
    };

    ws.onerror = () => {
      if (cancelled) return;
      setConnected(false);
    };

    ws.onclose = () => {
      if (cancelled) return;
      setConnected(false);
    };

    return () => {
      cancelled = true;
      ws.close();
      wsRef.current = null;
    };
  }, [venue]);

  const send = () => {
    const nick = nickname.trim() || 'Anonymous';
    const msg = draft.trim();
    if (!msg) return;

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ nickname: nick, message: msg }));
      setDraft('');
    } else {
      // Fallback: REST POST
      api.postVenueChat(venue.id, nick, msg)
        .then((resp) => {
          setMessages((prev) => [...prev, resp]);
          setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 50);
          setDraft('');
        })
        .catch(() => {});
    }
  };

  const formatTime = (iso: string) => {
    try {
      const d = new Date(iso + 'Z');
      return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  const nickColor = (name: string) => {
    const colors = [Colors.pink, Colors.cyan, Colors.yellow, Colors.ok, Colors.purple];
    let h = 0;
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    return colors[h % colors.length];
  };

  return (
    <View style={styles.chatPanel}>
      <View style={styles.chatTitleRow}>
        <Text style={styles.chatConnStatus}>
          {connected ? '● connected' : '○ disconnected'}
        </Text>
      </View>

      <ScrollView
        ref={scrollRef}
        style={styles.chatMessages}
        contentContainerStyle={styles.chatMessagesContent}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
      >
        {loading ? (
          <Loading label="Loading messages…" />
        ) : messages.length === 0 ? (
          <Text style={styles.chatEmpty}>No messages yet. Say hi! 👋</Text>
        ) : (
          messages.map((m) => (
            <View key={m.id} style={styles.chatMsg}>
              <View style={styles.chatMsgHeader}>
                <Text style={[styles.chatNick, { color: nickColor(m.nickname) }]}>
                  {m.nickname}
                </Text>
                <Text style={styles.chatTime}>{formatTime(m.created_at)}</Text>
              </View>
              <Text style={styles.chatBody}>{m.message}</Text>
            </View>
          ))
        )}
      </ScrollView>

      <View style={styles.chatInputRow}>
        <TextInput
          style={styles.chatNickInput}
          placeholder="nickname"
          placeholderTextColor={Colors.textMute}
          value={nickname}
          onChangeText={setNickname}
          maxLength={60}
        />
        <TextInput
          style={styles.chatMsgInput}
          placeholder="Say something…"
          placeholderTextColor={Colors.textMute}
          value={draft}
          onChangeText={setDraft}
          maxLength={500}
          onSubmitEditing={send}
        />
        <Button
          label="Send"
          onPress={send}
          variant="cyan"
          disabled={!draft.trim()}
          style={styles.chatSendBtn}
        />
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Jump Queue modal
// ---------------------------------------------------------------------------

function PaymentModal({
  venue,
  stripeConfigured,
  visible,
  onClose,
}: {
  venue: Venue;
  stripeConfigured: boolean;
  visible: boolean;
  onClose: () => void;
}) {
  const [prefs, updatePrefs] = usePrefsContext();
  const [singer, setSinger] = useState('');
  const [song, setSong] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (visible) {
      setSinger(prefs.singer_name || '');
      setSong('');
      setSubmitting(false);
      setError(null);
    }
  }, [visible]);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const nameVal = singer.trim() || 'Anonymous Singer';
      const res = await api.createPaymentSession(
        venue.id,
        nameVal,
        song.trim(),
      );
      // Save singer name to prefs
      updatePrefs((p) => ({ ...p, singer_name: nameVal !== 'Anonymous Singer' ? nameVal : p.singer_name }));
      let url = res.checkout_url;
      if (url.startsWith('/')) {
        url = `${API_BASE.replace(/\/api$/, '')}${url}`;
      }
      const result = await WebBrowser.openAuthSessionAsync(url);
      onClose();
      console.log('[Payment] openAuthSession result:', JSON.stringify(result));
      if (result.type === 'success' && result.url) {
        const parsed = LinkingExpo.parse(result.url);
        if (parsed.path === 'payment-success') {
          Alert.alert(
            'Payment Received',
            'Your premium slot request has been sent to the KJ. They\'ll confirm your position.',
          );
        } else if (parsed.path === 'payment-cancelled') {
          Alert.alert('Payment Cancelled', 'No charge was made.');
        } else {
          Alert.alert(
            'Checkout Complete',
            'Your premium slot request has been sent to the KJ.',
          );
        }
      } else if (result.type === 'success') {
        Alert.alert(
          'Checkout Closed',
          'If you completed payment, your premium slot request has been sent to the KJ.',
        );
      } else if (result.type === 'cancel') {
        Alert.alert('Payment Cancelled', 'No charge was made.');
      } else {
        Alert.alert(
          'Checkout Closed',
          'If you completed payment, your premium slot request has been sent to the KJ.',
        );
      }
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Payment session could not be created',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.modalBackdrop} onPress={onClose}>
        <Pressable style={styles.modal} onPress={(e) => e.stopPropagation()}>
          <Pressable style={styles.modalClose} onPress={onClose} hitSlop={12}>
            <Text style={styles.modalCloseText}>×</Text>
          </Pressable>
          <Text style={styles.modalTitle}>⏭️ Jump the Queue</Text>
          <Text style={styles.modalSub}>
            {venue.name} · KJ: {venue.kj_name || 'TBA'}
          </Text>
          <View style={styles.priceDisplay}>
            <Text style={styles.priceAmount}>${venue.price_jump_queue.toFixed(2)}</Text>
            <Text style={styles.priceLabel}> to sing next</Text>
          </View>

          {!stripeConfigured && (
            <Banner
              message="⚠️ Stripe not configured — you'll be redirected to a test success page."
              variant="info"
            />
          )}

          <Text style={styles.fieldLabel}>Your name (optional)</Text>
          <TextInput
            style={styles.input}
            placeholder="Anonymous Singer"
            placeholderTextColor={Colors.textMute}
            value={singer}
            onChangeText={setSinger}
            maxLength={60}
          />

          <Text style={styles.fieldLabel}>Song request (optional)</Text>
          <TextInput
            style={styles.input}
            placeholder="e.g. Don't Stop Believin' — Journey"
            placeholderTextColor={Colors.textMute}
            value={song}
            onChangeText={setSong}
            maxLength={120}
          />

          {error && <Banner message={`⚠️ ${error}`} variant="warn" />}

          <Button
            label={
              submitting
                ? 'Creating checkout…'
                : `Pay $${venue.price_jump_queue.toFixed(2)} & jump queue`
            }
            onPress={submit}
            disabled={submitting}
          />
        </Pressable>
      </Pressable>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Tip KJ modal
// ---------------------------------------------------------------------------

const TIP_PRESETS = [3, 5, 10, 20];

function TipModal({
  venue,
  stripeConfigured,
  visible,
  onClose,
}: {
  venue: Venue;
  stripeConfigured: boolean;
  visible: boolean;
  onClose: () => void;
}) {
  const [tipAmount, setTipAmount] = useState(5);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!visible) {
      setTipAmount(5);
      setSubmitting(false);
      setError(null);
      setSuccess(false);
    }
  }, [visible]);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      // Placeholder: use createPaymentSession with the tip amount in the song_request field.
      // The backend can interpret this as a tip (venue_id + amount).
      const res = await api.createPaymentSession(
        venue.id,
        'Tipper',
        `TIP:$${tipAmount.toFixed(2)}`,
      );
      let url = res.checkout_url;
      if (url.startsWith('/')) {
        url = `${API_BASE.replace(/\/api$/, '')}${url}`;
      }
      const result = await WebBrowser.openAuthSessionAsync(url);
      setSuccess(true);
      if (result.type === 'success' && result.url) {
        const parsed = LinkingExpo.parse(result.url);
        if (parsed.path === 'payment-success') {
          Alert.alert(
            'Tip Received',
            'Thank you for supporting the KJ!',
          );
        } else if (parsed.path === 'payment-cancelled') {
          Alert.alert('Tip Cancelled', 'No charge was made.');
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create tip session');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.modalBackdrop} onPress={onClose}>
        <Pressable style={styles.modal} onPress={(e) => e.stopPropagation()}>
          <Pressable style={styles.modalClose} onPress={onClose} hitSlop={12}>
            <Text style={styles.modalCloseText}>×</Text>
          </Pressable>
          <Text style={styles.modalTitle}>💰 Tip the KJ</Text>
          <Text style={styles.modalSub}>
            {venue.kj_name ? `Show some love to ${venue.kj_name}` : `Show some love to the KJ at ${venue.name}`}
          </Text>

          {!stripeConfigured && (
            <Banner
              message="⚠️ Stripe not configured — you'll be redirected to a test success page."
              variant="info"
            />
          )}

          <Text style={styles.fieldLabel}>Tip amount</Text>
          <View style={styles.tipPresets}>
            {TIP_PRESETS.map((amt) => (
              <Pressable
                key={amt}
                onPress={() => setTipAmount(amt)}
                style={({ pressed }) => [
                  styles.tipPreset,
                  tipAmount === amt && styles.tipPresetActive,
                  pressed && styles.tipPresetPressed,
                ]}
              >
                <Text
                  style={[
                    styles.tipPresetText,
                    tipAmount === amt && styles.tipPresetTextActive,
                  ]}
                >
                  ${amt}
                </Text>
              </Pressable>
            ))}
          </View>

          <Text style={styles.fieldLabel}>Custom amount</Text>
          <TextInput
            style={styles.input}
            placeholder="Enter $ amount"
            placeholderTextColor={Colors.textMute}
            value={tipAmount > 0 ? String(tipAmount) : ''}
            onChangeText={(v) => {
              const n = parseFloat(v);
              setTipAmount(isNaN(n) || n < 0 ? 0 : n);
            }}
            keyboardType="decimal-pad"
          />

          {error && <Banner message={`⚠️ ${error}`} variant="warn" />}
          {success && (
            <Banner message="Tip checkout opened! Thanks for supporting your KJ." variant="ok" />
          )}

          <Button
            label={submitting ? 'Creating checkout…' : `Tip $${tipAmount.toFixed(2)}`}
            onPress={submit}
            disabled={submitting || tipAmount <= 0}
          />
        </Pressable>
      </Pressable>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Message KJ Modal
// ---------------------------------------------------------------------------

function MessageKJModal({
  venue,
  visible,
  onClose,
}: {
  venue: Venue;
  visible: boolean;
  onClose: () => void;
}) {
  const [prefs, updatePrefs] = usePrefsContext();
  const [singer, setSinger] = useState('');
  const [phone, setPhone] = useState('');
  const [message, setMessage] = useState('');
  const [song, setSong] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (visible) {
      setSinger(prefs.singer_name || '');
      setPhone(prefs.singer_phone || '');
      setMessage('');
      setSong('');
      setSubmitting(false);
      setError(null);
      setSent(false);
    }
  }, [visible]);

  const submit = async () => {
    if (!message.trim()) {
      setError('Please enter a message');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const nameVal = singer.trim() || 'Anonymous Singer';
      const phoneVal = phone.trim();
      await api.sendKJMessage(
        venue.id,
        nameVal,
        message.trim(),
        song.trim() || undefined,
        phoneVal || undefined,
      );
      // Save to prefs so next time the fields are pre-filled
      updatePrefs((p) => ({ ...p, singer_name: nameVal !== 'Anonymous Singer' ? nameVal : p.singer_name, singer_phone: phoneVal || p.singer_phone }));
      setSent(true);
      setTimeout(onClose, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send message');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.modalBackdrop} onPress={onClose}>
        <Pressable style={styles.modal} onPress={(e) => e.stopPropagation()}>
          <Pressable style={styles.modalClose} onPress={onClose} hitSlop={12}>
            <Text style={styles.modalCloseText}>×</Text>
          </Pressable>
          <Text style={styles.modalTitle}>✉️ Message {venue.kj_name || 'the KJ'}</Text>
          <Text style={styles.modalSub}>{venue.name}</Text>

          {sent ? (
            <Text style={styles.successText}>Message sent! The KJ will see it soon.</Text>
          ) : (
            <>
              <Text style={styles.fieldLabel}>Your name (optional)</Text>
              <TextInput
                style={styles.input}
                placeholder="Anonymous Singer"
                placeholderTextColor={Colors.textMute}
                value={singer}
                onChangeText={setSinger}
                maxLength={60}
              />

              <Text style={styles.fieldLabel}>Your phone (optional — lets the KJ reply)</Text>
              <TextInput
                style={styles.input}
                placeholder="(321) 555-0123"
                placeholderTextColor={Colors.textMute}
                value={phone}
                onChangeText={setPhone}
                maxLength={20}
                keyboardType="phone-pad"
              />

              <Text style={styles.fieldLabel}>Song request (optional)</Text>
              <TextInput
                style={styles.input}
                placeholder="e.g. Don't Stop Believin'"
                placeholderTextColor={Colors.textMute}
                value={song}
                onChangeText={setSong}
                maxLength={200}
              />

              <Text style={styles.fieldLabel}>Message</Text>
              <TextInput
                style={[styles.input, { minHeight: 80 }]}
                placeholder="Leave a message for the KJ..."
                placeholderTextColor={Colors.textMute}
                value={message}
                onChangeText={setMessage}
                maxLength={500}
                multiline
                textAlignVertical="top"
              />

              {error ? <Text style={styles.errorText}>{error}</Text> : null}

              <Pressable
                onPress={submit}
                disabled={submitting}
                style={({ pressed }) => [
                  styles.submitBtn,
                  submitting && styles.submitBtnDisabled,
                  pressed && !submitting && styles.submitBtnPressed,
                ]}
              >
                <Text style={styles.submitBtnText}>
                  {submitting ? 'Sending...' : 'Send Message'}
                </Text>
              </Pressable>
            </>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}


// ---------------------------------------------------------------------------
// Get In Line Modal — sends a queue request message to the KJ
// ---------------------------------------------------------------------------

function GetInLineModal({
  venue,
  visible,
  onClose,
}: {
  venue: Venue;
  visible: boolean;
  onClose: () => void;
}) {
  const [prefs, updatePrefs] = usePrefsContext();
  const [singer, setSinger] = useState('');
  const [phone, setPhone] = useState('');
  const [song, setSong] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (visible) {
      setSinger(prefs.singer_name || '');
      setPhone(prefs.singer_phone || '');
      setSong('');
      setSubmitting(false);
      setError(null);
      setSent(false);
    }
  }, [visible]);

  const submit = async () => {
    if (venue.song_request_required && !song.trim()) {
      setError('This KJ requires a song request');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const nameVal = singer.trim() || 'Anonymous Singer';
      const phoneVal = phone.trim();
      await api.sendKJMessage(
        venue.id,
        nameVal,
        `QUEUE: I'd like to sing!`,
        song.trim(),
        phoneVal || undefined,
      );
      updatePrefs((p) => ({ ...p, singer_name: nameVal !== 'Anonymous Singer' ? nameVal : p.singer_name, singer_phone: phoneVal || p.singer_phone }));
      setSent(true);
      setTimeout(onClose, 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send request');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.modalBackdrop} onPress={onClose}>
        <Pressable style={styles.modal} onPress={(e) => e.stopPropagation()}>
          <Pressable style={styles.modalClose} onPress={onClose} hitSlop={12}>
            <Text style={styles.modalCloseText}>×</Text>
          </Pressable>
          <Text style={styles.modalTitle}>🎤 Get In Line</Text>
          <Text style={styles.modalSub}>{venue.name} · KJ: {venue.kj_name || 'TBA'}</Text>

          {sent ? (
            <Text style={styles.successText}>
              Request sent! {venue.kj_name || 'The KJ'} will see your song and fit you into the rotation.
            </Text>
          ) : (
            <>
              <Text style={styles.fieldLabel}>Your name (optional)</Text>
              <TextInput
                style={styles.input}
                placeholder="Anonymous Singer"
                placeholderTextColor={Colors.textMute}
                value={singer}
                onChangeText={setSinger}
                maxLength={60}
              />

              <Text style={styles.fieldLabel}>Your phone (optional — lets the KJ reply)</Text>
              <TextInput
                style={styles.input}
                placeholder="(321) 555-0123"
                placeholderTextColor={Colors.textMute}
                value={phone}
                onChangeText={setPhone}
                maxLength={20}
                keyboardType="phone-pad"
              />

              <Text style={styles.fieldLabel}>
                Song request {venue.song_request_required ? '' : '(optional)'}
              </Text>
              <TextInput
                style={styles.input}
                placeholder="e.g. Don't Stop Believin' — Journey"
                placeholderTextColor={Colors.textMute}
                value={song}
                onChangeText={setSong}
                maxLength={200}
              />

              {error ? <Text style={styles.errorText}>{error}</Text> : null}

              <Pressable
                onPress={submit}
                disabled={submitting}
                style={({ pressed }) => [
                  styles.submitBtn,
                  submitting && styles.submitBtnDisabled,
                  pressed && !submitting && styles.submitBtnPressed,
                ]}
              >
                <Text style={styles.submitBtnText}>
                  {submitting ? 'Sending...' : 'Send to KJ'}
                </Text>
              </Pressable>
            </>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}


// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  content: { padding: Spacing.lg, paddingBottom: 100 },

  // Venue header card (compact, matches venue list)
  headerCard: {
    marginBottom: 0,
  },
  venueHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 12,
  },
  venueName: {
    ...Typography.title,
    color: Colors.text,
  },
  venueCity: {
    fontSize: 13,
    color: Colors.cyan,
    fontWeight: '600',
    marginTop: 2,
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
    fontStyle: 'italic',
  },

  // Action bar anchored at bottom
  actionBar: {
    flexDirection: 'row',
    gap: Spacing.sm,
    padding: Spacing.lg,
    paddingBottom: Spacing.lg + 8,
    backgroundColor: Colors.bg,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
  },
  subtleBtn: {
    flex: 1,
    minHeight: 44,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.bg2,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.md,
  },
  subtleBtnTip: {
    borderColor: 'rgba(212, 195, 114, 0.3)',
    backgroundColor: 'rgba(212, 195, 114, 0.08)',
  },
  subtleBtnLineup: {
    borderColor: 'rgba(95, 184, 168, 0.4)',
    backgroundColor: 'rgba(95, 184, 168, 0.08)',
  },
  subtleBtnPressed: {
    opacity: 0.7,
  },
  subtleBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.text,
  },
  testModeNote: {
    marginTop: Spacing.sm,
    fontSize: 12,
    color: Colors.textMute,
  },

  // Chat section — fills remaining space between header and action bar
  chatSection: {
    flex: 1,
    padding: Spacing.lg,
    paddingBottom: 0,
  },
  chatPanel: {
    flex: 1,
    backgroundColor: Colors.panel,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.lg,
  },
  chatTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: Spacing.sm,
  },
  chatConnStatus: {
    fontSize: 12,
    color: Colors.textMute,
    fontWeight: '600',
  },
  chatMessages: {
    flex: 1,
  },
  chatMessagesContent: {
    gap: Spacing.md,
  },
  chatEmpty: {
    textAlign: 'center',
    color: Colors.textMute,
    paddingVertical: 40,
    fontSize: 14,
  },
  chatMsg: {
    backgroundColor: Colors.bg2,
    borderRadius: Radius.sm,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.md,
  },
  chatMsgHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: 4,
  },
  chatNick: {
    fontSize: 13,
    fontWeight: '700',
  },
  chatTime: {
    fontSize: 11,
    color: Colors.textMute,
  },
  chatBody: {
    fontSize: 14,
    color: Colors.text,
    lineHeight: 20,
  },
  chatInputRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginTop: Spacing.md,
    alignItems: 'center',
  },
  chatNickInput: {
    width: 100,
    minHeight: TAP_HEIGHT,
    backgroundColor: Colors.bg2,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.sm,
    paddingHorizontal: 12,
    color: Colors.text,
    fontSize: 14,
  },
  chatMsgInput: {
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
  chatSendBtn: {
    paddingHorizontal: 18,
  },

  // Modals
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    padding: Spacing.lg,
  },
  modal: {
    backgroundColor: Colors.panel,
    borderRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.xl,
  },
  modalClose: {
    position: 'absolute',
    top: 8,
    right: 12,
    zIndex: 1,
  },
  modalCloseText: {
    fontSize: 28,
    color: Colors.textDim,
  },
  modalTitle: {
    ...Typography.heading,
    color: Colors.text,
    marginBottom: 4,
  },
  modalSub: {
    fontSize: 14,
    color: Colors.textDim,
    marginBottom: Spacing.md,
  },
  priceDisplay: {
    flexDirection: 'row',
    alignItems: 'baseline',
    marginBottom: Spacing.md,
  },
  priceAmount: {
    fontSize: 32,
    fontWeight: '900',
    color: Colors.pink,
  },
  priceLabel: {
    fontSize: 14,
    color: Colors.textMute,
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.textDim,
    marginBottom: 6,
    marginTop: Spacing.sm,
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
    marginBottom: Spacing.md,
  },

  // Tip presets
  tipPresets: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  tipPreset: {
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.bg2,
    borderRadius: Radius.pill,
    paddingHorizontal: 18,
    paddingVertical: 10,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tipPresetActive: {
    backgroundColor: Colors.yellow,
    borderColor: 'transparent',
  },
  tipPresetPressed: {
    opacity: 0.85,
  },
  tipPresetText: {
    color: Colors.textDim,
    fontSize: 16,
    fontWeight: '700',
  },
  tipPresetTextActive: {
    color: '#1a1a2e',
  },

  // Off-event section
  offEventSection: {
    flex: 1,
    padding: Spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.md,
  },
  offEventText: {
    color: Colors.textDim,
    fontSize: 15,
    textAlign: 'center',
    marginBottom: Spacing.sm,
  },

  // Message KJ modal
  successText: {
    color: Colors.cyan,
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'center',
    paddingVertical: Spacing.lg,
  },
  errorText: {
    color: Colors.pink,
    fontSize: 13,
    marginBottom: Spacing.sm,
  },
  submitBtn: {
    backgroundColor: Colors.pink,
    borderRadius: Radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    minHeight: 48,
    justifyContent: 'center',
    marginTop: Spacing.xs,
  },
  submitBtnDisabled: {
    opacity: 0.5,
  },
  submitBtnPressed: {
    opacity: 0.85,
  },
  submitBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
});
