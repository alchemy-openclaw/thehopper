import { useEffect, useRef, useState } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import type { AppConfig, ChatMessage, Venue } from '../../src/types';
import { api, API_BASE } from '../../src/api';
import { useVenueContext } from '../../src/venue-context';
import {
  Banner,
  Button,
  Card,
  EmptyState,
  Loading,
} from '../../src/components';
import { Colors, Radius, Spacing, TAP_HEIGHT, Typography } from '../../src/theme';

export default function EventScreen() {
  const { selectedVenue } = useVenueContext();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [showPay, setShowPay] = useState(false);
  const [showTip, setShowTip] = useState(false);

  useEffect(() => {
    api.getConfig().then(setConfig).catch(() => setConfig(null));
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

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      {/* Venue header */}
      <Card>
        <Text style={styles.venueName}>{venue.name}</Text>
        <Text style={styles.venueCity}>{venue.city}</Text>
        <View style={styles.venueMeta}>
          {venue.karaoke_nights.map((n) => (
            <Text key={n} style={styles.metaText}>· {n}</Text>
          ))}
          <Text style={styles.metaText}>· 🕘 {venue.start_time}–{venue.end_time}</Text>
          {venue.kj_name && <Text style={styles.metaText}>· KJ: {venue.kj_name}</Text>}
        </View>
        {venue.vibe ? <Text style={styles.venueVibe}>{venue.vibe}</Text> : null}

        {/* Subtle action row */}
        <View style={styles.actionRow}>
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

        {!config?.stripe_configured && (
          <Text style={styles.testModeNote}>
            Test mode — no real charges will be made.
          </Text>
        )}
      </Card>

      {/* Chat */}
      <View style={styles.chatSection}>
        <Text style={styles.chatHeader}>💬 Venue Chat</Text>
        <ChatPanel venue={venue} />
      </View>

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
    </ScrollView>
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
  const [singer, setSinger] = useState('');
  const [song, setSong] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) {
      setSinger('');
      setSong('');
      setSubmitting(false);
      setError(null);
    }
  }, [visible]);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.createPaymentSession(
        venue.id,
        singer.trim() || 'Anonymous Singer',
        song.trim(),
      );
      let url = res.checkout_url;
      if (url.startsWith('/')) {
        url = `${API_BASE.replace(/\/api$/, '')}${url}`;
      }
      await WebBrowser.openBrowserAsync(url);
      onClose();
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
      await WebBrowser.openBrowserAsync(url);
      setSuccess(true);
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
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  content: { padding: Spacing.lg, paddingBottom: 100 },

  // Venue header card
  venueName: {
    ...Typography.title,
    color: Colors.text,
  },
  venueCity: {
    fontSize: 14,
    color: Colors.cyan,
    fontWeight: '600',
    marginTop: 2,
  },
  venueMeta: {
    marginTop: Spacing.md,
    gap: 4,
  },
  metaText: {
    fontSize: 13,
    color: Colors.textDim,
    fontWeight: '500',
  },
  venueVibe: {
    marginTop: Spacing.sm,
    fontSize: 14,
    color: Colors.textDim,
    lineHeight: 20,
    fontStyle: 'italic',
  },

  // Subtle action buttons
  actionRow: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginTop: Spacing.lg,
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

  // Chat section
  chatSection: {
    marginTop: Spacing.lg,
  },
  chatHeader: {
    ...Typography.heading,
    color: Colors.text,
    marginBottom: Spacing.sm,
  },
  chatPanel: {
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
    height: 320,
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
});
