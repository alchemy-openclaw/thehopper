// Toned-down nightlife design system for TheHopper.
// Muted dark palette -- still dark, less neon.

export const Colors = {
  bg: '#1a1a2e',
  bg2: '#22223a',
  panel: '#262640',
  panel2: '#2d2d4a',
  border: '#3a3a55',
  pink: '#c4568d',
  purple: '#7b6ca6',
  cyan: '#5fb8a8',
  yellow: '#d4c372',
  text: '#e8e4f0',
  textDim: '#a09ab8',
  textMute: '#6a6585',
  ok: '#5fb8a8',
  bad: '#c45a5a',
} as const;

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
} as const;

export const Radius = {
  sm: 10,
  md: 16,
  pill: 999,
} as const;

// Minimum touch target height (iOS HIG / Material: 44pt)
export const TAP_HEIGHT = 52;

export const Typography = {
  title: { fontSize: 26, fontWeight: '700' as const, letterSpacing: -0.5 },
  heading: { fontSize: 18, fontWeight: '700' as const },
  body: { fontSize: 16, fontWeight: '400' as const },
  small: { fontSize: 13, fontWeight: '600' as const },
  caption: { fontSize: 12, fontWeight: '500' as const },
} as const;

export const Shadows = {
  neon: {
    shadowColor: Colors.pink,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
    elevation: 4,
  },
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 16,
    elevation: 3,
  },
  cyan: {
    shadowColor: Colors.cyan,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 3,
  },
} as const;
