import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { ReactNode } from 'react';
import { Colors, Radius, Shadows, Spacing, TAP_HEIGHT, Typography } from './theme';
import type { Song } from './types';
import { DIFFICULTY_LABELS } from './types';

// ---------- Button ----------

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'cyan';

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  style,
}: {
  label: string;
  onPress?: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  style?: object;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.btn,
        styles[variant],
        pressed && styles.btnPressed,
        disabled && styles.btnDisabled,
        style,
      ]}
    >
      <Text style={styles.btnText}>{label}</Text>
    </Pressable>
  );
}

// ---------- Card ----------

export function Card({ children, style }: { children: ReactNode; style?: object }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

// ---------- MetaPill ----------

export function MetaPill({
  label,
  variant = 'default',
}: {
  label: string;
  variant?: 'default' | 'nights';
}) {
  return <View style={[styles.pill, variant === 'nights' && styles.pillNights]}><Text style={styles.pillText}>{label}</Text></View>;
}

// ---------- Banner ----------

export function Banner({
  message,
  variant = 'info',
}: {
  message: string;
  variant?: 'info' | 'warn' | 'ok';
}) {
  return (
    <View style={[styles.banner, styles[`banner_${variant}`]]}>
      <Text style={styles.bannerText}>{message}</Text>
    </View>
  );
}

// ---------- Loading ----------

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <View style={styles.loading}>
      <ActivityIndicator size="large" color={Colors.pink} />
      <Text style={styles.loadingText}>{label}</Text>
    </View>
  );
}

// ---------- EmptyState ----------

export function EmptyState({ icon, message }: { icon: string; message: string }) {
  return (
    <View style={styles.empty}>
      <Text style={styles.emptyIcon}>{icon}</Text>
      <Text style={styles.emptyText}>{message}</Text>
    </View>
  );
}

// ---------- SectionTitle ----------

export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

// ---------- Chip ----------

export function Chip({
  label,
  active,
  onPress,
}: {
  label: string;
  active?: boolean;
  onPress?: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.chip,
        active && styles.chipActive,
        pressed && styles.chipPressed,
      ]}
    >
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  );
}

// ---------- DifficultyBadge ----------

export function DifficultyBadge({ level }: { level: number }) {
  const info = DIFFICULTY_LABELS[level] ?? { label: '?', emoji: '⚪' };
  return <MetaPill label={`${info.emoji} ${info.label}`} />;
}

// ---------- RangeChips ----------

export function RangeChips({ ranges }: { ranges: string[] }) {
  return (
    <View style={styles.rangeWrap}>
      {ranges.map((r) => (
        <MetaPill key={r} label={r} />
      ))}
    </View>
  );
}

// ---------- SongCard ----------

export function SongCard({
  song,
  score,
  reason,
  isFavorite,
  onToggleFavorite,
}: {
  song: Song;
  score?: number;
  reason?: string;
  isFavorite?: boolean;
  onToggleFavorite?: () => void;
}) {
  return (
    <Card style={styles.song}>
      <View style={styles.songTop}>
        <View style={{ flex: 1 }}>
          <Text style={styles.songTitle}>{song.title}</Text>
          <Text style={styles.songArtist}>{song.artist}</Text>
        </View>
        {score != null && (
          <View style={styles.songScore}>
            <Text style={styles.songScoreText}>{Math.round(score)}%</Text>
          </View>
        )}
        {onToggleFavorite && (
          <Pressable
            onPress={onToggleFavorite}
            hitSlop={12}
            style={styles.starBtn}
            accessibilityLabel={isFavorite ? 'Remove from favorites' : 'Add to favorites'}
          >
            <Text style={styles.starText}>{isFavorite ? '⭐' : '☆'}</Text>
          </Pressable>
        )}
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.songMeta}>
        <MetaPill label={song.genre} />
        {song.year != null && <MetaPill label={String(song.year)} />}
        <DifficultyBadge level={song.difficulty} />
        {song.range_fit.map((r) => (
          <MetaPill key={r} label={r} />
        ))}
      </ScrollView>

      {reason ? <Text style={styles.songReason}>{reason}</Text> : null}
      {song.notes ? <Text style={styles.songNotes}>{song.notes}</Text> : null}
    </Card>
  );
}

// ---------- Styles ----------

const styles = StyleSheet.create({
  btn: {
    minHeight: TAP_HEIGHT,
    borderRadius: Radius.sm,
    paddingHorizontal: Spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primary: {
    backgroundColor: Colors.pink,
    shadowColor: Colors.pink,
    shadowOpacity: 0.35,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  secondary: {
    backgroundColor: Colors.panel2,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  ghost: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cyan: {
    backgroundColor: Colors.cyan,
    shadowColor: Colors.cyan,
    shadowOpacity: 0.35,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  btnPressed: {
    opacity: 0.85,
    transform: [{ scale: 0.98 }],
  },
  btnDisabled: {
    opacity: 0.5,
  },
  btnText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 15,
  },
  card: {
    backgroundColor: Colors.panel,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.md,
    padding: Spacing.lg,
    marginBottom: Spacing.md,
    ...Shadows.card,
  },
  pill: {
    backgroundColor: Colors.bg2,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 5,
    marginRight: 6,
    marginTop: 6,
  },
  pillNights: {
    backgroundColor: 'rgba(249, 248, 113, 0.08)',
    borderColor: 'rgba(249, 248, 113, 0.35)',
  },
  pillText: {
    color: Colors.textDim,
    fontSize: 12,
    fontWeight: '600',
  },
  banner: {
    borderRadius: Radius.sm,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 12,
    borderWidth: 1,
  },
  banner_info: {
    backgroundColor: 'rgba(0, 245, 212, 0.1)',
    borderColor: 'rgba(0, 245, 212, 0.35)',
  },
  banner_warn: {
    backgroundColor: 'rgba(255, 71, 87, 0.1)',
    borderColor: 'rgba(255, 71, 87, 0.35)',
  },
  banner_ok: {
    backgroundColor: 'rgba(46, 229, 157, 0.1)',
    borderColor: 'rgba(46, 229, 157, 0.35)',
  },
  bannerText: {
    color: Colors.text,
    fontSize: 14,
    fontWeight: '600',
  },
  loading: {
    padding: Spacing.xxl,
    alignItems: 'center',
    gap: Spacing.md,
  },
  loadingText: {
    color: Colors.textDim,
    ...Typography.body,
  },
  empty: {
    padding: Spacing.xxl * 2,
    alignItems: 'center',
    gap: Spacing.md,
  },
  emptyIcon: {
    fontSize: 48,
  },
  emptyText: {
    color: Colors.textDim,
    textAlign: 'center',
    ...Typography.body,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: Colors.textMute,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginTop: Spacing.xl,
    marginBottom: Spacing.sm,
  },
  chip: {
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.bg2,
    borderRadius: Radius.pill,
    paddingHorizontal: 16,
    paddingVertical: 10,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
    marginBottom: 8,
  },
  chipActive: {
    backgroundColor: Colors.pink,
    borderColor: 'transparent',
    shadowColor: Colors.pink,
    shadowOpacity: 0.45,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 0 },
    elevation: 4,
  },
  chipPressed: {
    opacity: 0.85,
  },
  chipText: {
    color: Colors.textDim,
    fontSize: 14,
    fontWeight: '600',
  },
  chipTextActive: {
    color: '#fff',
  },
  rangeWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 6,
  },
  song: {
    paddingVertical: 14,
  },
  songTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 10,
  },
  songTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.text,
    lineHeight: 21,
    flexShrink: 1,
  },
  songArtist: {
    fontSize: 13,
    color: Colors.pink,
    fontWeight: '600',
    marginTop: 2,
  },
  songScore: {
    backgroundColor: Colors.cyan,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  songScoreText: {
    color: '#02101a',
    fontSize: 13,
    fontWeight: '800',
  },
  songMeta: {
    flexDirection: 'row',
    marginTop: 8,
  },
  songReason: {
    marginTop: 8,
    fontSize: 13,
    color: Colors.cyan,
    fontWeight: '500',
  },
  songNotes: {
    marginTop: 8,
    fontSize: 12,
    color: Colors.textMute,
    fontStyle: 'italic',
    lineHeight: 18,
  },
  starBtn: {
    padding: 4,
  },
  starText: {
    fontSize: 24,
  },
});
