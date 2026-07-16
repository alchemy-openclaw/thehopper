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
import { getGeolocation } from '../../src/prefs';
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
  const [payVenue, setPayVenue] = useState<Venue | null>(null);
  const [chatVenue, setChatVenue] = useState<Venue | null>(null);

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

  const handlePay = async (venue: Venue, singerName: string, songRequest: string) => {
    try {
      const res = await api.createPaymentSession(
        venue.id,
        singerName || 'Anonymous Singer',
        songRequest,
      );
      // Open Stripe Checkout (or test-mode URL) in an in-app browser.
      // For relative test URLs, prepend the API base origin.
      let url = res.checkout_url;
      if (url.startsWith('/')) {
        url = `http://localhost:8000${url}`;
      }
      await WebBrowser.openBrowserAsync(url);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Payment session could not be created',
      );
    }
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
            onPay={() => setPayVenue(v)}
            onChat={() => setChatVenue(v)}
            stripeConfigured={config?.stripe_configured ?? false}
          />
        ))
      )}

      <PaymentModal
        venue={payVenue}
        stripeConfigured={config?.stripe_configured ?? false}
        onClose={() => setPayVenue(null)}
        onConfirm={handlePay}
      />

      <ChatModal
        venue={chatVenue}
        onClose={() => setChatVenue(null)}
      />
    </ScrollView>
  );
}

function VenueCard({
  venue,
  onPay,
  onChat,
  stripeConfigured,
}: {
  venue: Venue;
  onPay: () => void;
  onChat: () => void;
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
          label={`⏭️ Jump Queue · $${venue.price_jump_queue.toFixed(2)}`}
          onPress={onPay}
        />
      </View>
      <View style={styles.venueActions}>
        <Button
          label="💬 Venue chat"
          onPress={onChat}
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

function PaymentModal({
  venue,
  stripeConfigured,
  onClose,
  onConfirm,
}: {
  venue: Venue | null;
  stripeConfigured: boolean;
  onClose: () => void;
  onConfirm: (venue: Venue, singerName: string, songRequest: string) => void;
}) {
  const [singer, setSinger] = useState('');
  const [song, setSong] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!venue) return;
    setSubmitting(true);
    await onConfirm(venue, singer, song);
    setSubmitting(false);
    onClose();
  };

  if (!venue) return null;

  return (
    <Modal visible={!!venue} transparent animationType="fade" onRequestClose={onClose}>
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

function ChatModal({
  venue,
  onClose,
}: {
  venue: Venue | null;
  onClose: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [nickname, setNickname] = useState('');
  const [draft, setDraft] = useState('');
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const scrollRef = useRef<ScrollView>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!venue) return;
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
    if (!venue) return;
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

  if (!venue) return null;

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
    <Modal visible={!!venue} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.chatBackdrop} onPress={onClose}>
        <Pressable style={styles.chatModal} onPress={(e) => e.stopPropagation()}>
          <Pressable style={styles.modalClose} onPress={onClose} hitSlop={12}>
            <Text style={styles.modalCloseText}>×</Text>
          </Pressable>
          <View style={styles.chatTitleRow}>
            <Text style={styles.modalTitle}>💬 {venue.name} chat</Text>
            <Text style={[styles.chatStatus, { color: connected ? Colors.ok : Colors.textMute }]}>
              {connected ? '●' : '○'}
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
        </Pressable>
      </Pressable>
    </Modal>
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
    fontSize: 18,
    fontWeight: '800',
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
    backgroundColor: 'rgba(0, 245, 212, 0.12)',
    borderColor: 'rgba(0, 245, 212, 0.3)',
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
  // Modal
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
  // Chat modal
  chatBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  chatModal: {
    backgroundColor: Colors.panel,
    borderTopLeftRadius: Radius.md,
    borderTopRightRadius: Radius.md,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.xl,
    maxHeight: '85%',
  },
  chatTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  chatStatus: {
    fontSize: 12,
  },
  chatMessages: {
    height: 300,
    marginTop: Spacing.md,
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
});
