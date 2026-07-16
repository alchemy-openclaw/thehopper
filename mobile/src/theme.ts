// Neon nightlife design system for TheHopper.
// Colors mirror the web app's CSS variables.

export const Colors = {
  bg: '#0d0221',
  bg2: '#190a3b',
  panel: '#1a0b3a',
  panel2: '#250e57',
  border: '#3a1e6e',
  pink: '#ff2d95',
  purple: '#9d4edd',
  cyan: '#00f5d4',
  yellow: '#f9f871',
  text: '#f5e9ff',
  textDim: '#b9a7d9',
  textMute: '#7a6a99',
  ok: '#2ee59d',
  bad: '#ff4757',
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
  title: { fontSize: 26, fontWeight: '800' as const, letterSpacing: -0.5 },
  heading: { fontSize: 18, fontWeight: '800' as const },
  body: { fontSize: 16, fontWeight: '400' as const },
  small: { fontSize: 13, fontWeight: '600' as const },
  caption: { fontSize: 12, fontWeight: '500' as const },
} as const;

export const Shadows = {
  neon: {
    shadowColor: Colors.pink,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.45,
    shadowRadius: 24,
    elevation: 8,
  },
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.45,
    shadowRadius: 32,
    elevation: 6,
  },
  cyan: {
    shadowColor: Colors.cyan,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.35,
    shadowRadius: 16,
    elevation: 6,
  },
} as const;
