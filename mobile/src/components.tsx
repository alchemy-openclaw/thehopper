import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { ReactNode } from 'react';
import { Colors, Radius, Shadows, Spacing, TAP_HEIGHT, Typography } from './theme';
import { DAYS, dayAbbrev } from './days';
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

// ---------- SplitButton ----------

/**
 * One button, two jobs: a wide primary action and a narrow trailing segment
 * that opens a picker for a setting that action depends on.
 *
 * React Native has no primitive for this, and the community segmented-control
 * package is a different thing entirely — it picks one value out of several,
 * where here each half does its own job. So: two Pressables sharing one
 * outline with a hairline divider.
 *
 * `busy` puts the spinner in the trailing segment rather than over the label.
 * The wide segment keeps its wording while a search runs, which reads better
 * than a button whose text vanishes; the cost is that the current value is
 * briefly hidden, and that segment is where both paths spend their wait —
 * changing the setting re-runs the action too.
 */
export function SplitButton({
  label,
  onPress,
  trailingLabel,
  onPressTrailing,
  busy = false,
  disabled = false,
  trailingAccessibilityLabel,
}: {
  label: string;
  onPress?: () => void;
  trailingLabel: string;
  onPressTrailing?: () => void;
  busy?: boolean;
  disabled?: boolean;
  trailingAccessibilityLabel?: string;
}) {
  return (
    <View style={[styles.split, disabled && styles.btnDisabled]}>
      <Pressable
        onPress={onPress}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel={label}
        style={({ pressed }) => [styles.splitMain, pressed && styles.btnPressed]}
      >
        <Text style={styles.btnText} numberOfLines={1}>
          {label}
        </Text>
      </Pressable>

      <View style={styles.splitDivider} />

      <Pressable
        onPress={onPressTrailing}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel={trailingAccessibilityLabel ?? trailingLabel}
        style={({ pressed }) => [styles.splitTrailing, pressed && styles.btnPressed]}
      >
        {busy ? (
          <ActivityIndicator color="#fff" size="small" />
        ) : (
          <>
            <Text style={styles.splitTrailingText} numberOfLines={1}>
              {trailingLabel}
            </Text>
            <Text style={styles.splitCaret}> ▾</Text>
          </>
        )}
      </Pressable>
    </View>
  );
}

// ---------- Card ----------

export function Card({ children, style }: { children: ReactNode; style?: object }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

// ---------- MetaPill ----------

export function MetaPill({ label }: { label: string }) {
  return <View style={styles.pill}><Text style={styles.pillText}>{label}</Text></View>;
}

// ---------- NightsRow ----------

/**
 * The full week as seven two-letter chips, with the venue's karaoke nights
 * lit up. One component for both jobs: read-only on the event list/detail
 * cards, and tappable on the Add Show / Add Venue forms.
 *
 * Showing all seven (rather than only the active nights) is what keeps it to
 * a single row at a predictable width — the strip never reflows as venues
 * gain or lose nights, and an empty night reads as "not this one" instead of
 * simply being absent.
 */
export function NightsRow({
  nights,
  onToggle,
  style,
}: {
  nights: readonly string[];
  onToggle?: (day: string) => void;
  style?: object;
}) {
  const interactive = !!onToggle;
  return (
    <View style={[styles.nightsRow, style]}>
      {DAYS.map((day) => {
        const on = nights.includes(day);
        return (
          <Pressable
            key={day}
            onPress={onToggle ? () => onToggle(day) : undefined}
            disabled={!interactive}
            accessibilityRole={interactive ? 'checkbox' : undefined}
            accessibilityState={interactive ? { checked: on } : undefined}
            accessibilityLabel={day}
            style={({ pressed }) => [
              styles.dayChip,
              interactive && styles.dayChipTappable,
              on && styles.dayChipOn,
              pressed && interactive && styles.dayChipPressed,
            ]}
          >
            <Text style={[styles.dayChipText, on && styles.dayChipTextOn]}>
              {dayAbbrev(day)}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
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
  split: {
    flexDirection: 'row',
    alignItems: 'stretch',
    minHeight: TAP_HEIGHT,
    borderRadius: Radius.sm,
    // Fill and shadow live on the container so the two segments read as one
    // control rather than two buttons that happen to touch.
    backgroundColor: Colors.pink,
    overflow: 'hidden',
    shadowColor: Colors.pink,
    shadowOpacity: 0.35,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  splitMain: {
    flex: 1,
    paddingHorizontal: Spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  splitDivider: {
    width: StyleSheet.hairlineWidth,
    backgroundColor: 'rgba(255, 255, 255, 0.35)',
    marginVertical: Spacing.sm,
  },
  splitTrailing: {
    minWidth: 84,
    flexDirection: 'row',
    paddingHorizontal: Spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
    // A touch darker so the segment is findable without breaking the single
    // filled shape.
    backgroundColor: 'rgba(0, 0, 0, 0.16)',
  },
  splitTrailingText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  splitCaret: { color: 'rgba(255, 255, 255, 0.75)', fontSize: 12 },
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
  pillText: {
    color: Colors.textDim,
    fontSize: 12,
    fontWeight: '600',
  },
  nightsRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
    gap: 4,
    marginTop: 6,
  },
  dayChip: {
    // flex:1 over a fixed width is what guarantees the seven chips share the
    // row evenly on any screen instead of wrapping on a narrow one.
    flex: 1,
    borderWidth: 1,
    borderColor: Colors.border,
    backgroundColor: Colors.bg2,
    borderRadius: Radius.sm,
    paddingVertical: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Only the form variant needs a 44pt target; the list cards stay compact.
  dayChipTappable: {
    minHeight: 44,
    paddingVertical: 10,
  },
  dayChipOn: {
    backgroundColor: 'rgba(196, 86, 141, 0.22)',
    borderColor: Colors.pink,
  },
  dayChipPressed: { opacity: 0.85 },
  dayChipText: { color: Colors.textMute, fontSize: 13, fontWeight: '600' },
  dayChipTextOn: { color: Colors.text, fontWeight: '800' },
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
