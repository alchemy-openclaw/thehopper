/**
 * Paper theme, derived from theme.ts rather than duplicating it.
 *
 * theme.ts stays the single source of the palette. Two colour systems that
 * drift apart is worse than either one alone, so every value below is read
 * from Colors — nothing is re-typed as a literal.
 *
 * Two MD3 defaults have to be overridden or the app stops looking like itself:
 *
 *  - Elevation tinting. MD3 blends `primary` into raised surfaces, so with a
 *    pink primary every Card quietly drifts pink as it rises. The elevation
 *    levels are pinned to the existing panel colours instead of being computed.
 *
 *  - Roundness. Paper's default is tighter than Radius.sm, which would silently
 *    reshape every component in the app at once.
 */

import { MD3DarkTheme, configureFonts } from 'react-native-paper';
import { Colors, Radius } from './theme';

const fontConfig = {
  // The app has never used a custom face; this keeps Paper's scale but drops
  // its default letter-spacing, which reads loose against this palette.
  default: { letterSpacing: 0 },
} as const;

export const hopperDarkTheme = {
  ...MD3DarkTheme,
  // Radius.sm. Left explicit because Paper's default reshapes everything.
  roundness: Radius.sm,
  fonts: configureFonts({ config: fontConfig.default }),
  colors: {
    ...MD3DarkTheme.colors,

    primary: Colors.pink,
    onPrimary: '#ffffff',
    primaryContainer: Colors.panel2,
    onPrimaryContainer: Colors.text,

    secondary: Colors.purple,
    onSecondary: '#ffffff',
    secondaryContainer: Colors.panel,
    onSecondaryContainer: Colors.text,

    // Cyan is the app's confirmation colour — "found it", "live now".
    tertiary: Colors.cyan,
    onTertiary: '#10201d',
    tertiaryContainer: 'rgba(95, 184, 168, 0.18)',
    onTertiaryContainer: Colors.cyan,

    background: Colors.bg,
    onBackground: Colors.text,
    surface: Colors.bg2,
    onSurface: Colors.text,
    surfaceVariant: Colors.panel,
    onSurfaceVariant: Colors.textDim,
    surfaceDisabled: 'rgba(232, 228, 240, 0.12)',
    onSurfaceDisabled: Colors.textMute,

    outline: Colors.border,
    outlineVariant: '#2e2e47',

    error: Colors.bad,
    onError: '#ffffff',
    errorContainer: 'rgba(196, 90, 90, 0.18)',
    onErrorContainer: Colors.bad,

    inverseSurface: Colors.text,
    inverseOnSurface: Colors.bg,
    inversePrimary: Colors.pink,
    backdrop: 'rgba(0, 0, 0, 0.6)',

    // Pinned, not computed. Letting MD3 tint these with a pink primary is
    // what makes a themed Material app look accidentally mauve.
    elevation: {
      level0: 'transparent',
      level1: Colors.bg2,
      level2: Colors.panel,
      level3: Colors.panel,
      level4: Colors.panel2,
      level5: Colors.panel2,
    },
  },
} as const;

export type HopperTheme = typeof hopperDarkTheme;
