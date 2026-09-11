/**
 * Motion tokens.
 *
 * Animations live here rather than at each call site for the same reason
 * colours do: a spring that is 0.8 stiffness in one place and 0.6 in another
 * reads as sloppiness, not variety. Everything below is tuned around one
 * idea — the app should feel quick and settled, never bouncy. Karaoke apps
 * are used one-handed in a dark bar; overshoot is noise.
 *
 * Reanimated respects the OS "reduce motion" setting by default (ReduceMotion
 * .System), so none of this needs a manual accessibility guard.
 */

import { FadeIn, FadeInDown, FadeOut, LinearTransition } from 'react-native-reanimated';

/** Slightly damped, no visible overshoot. Used for anything the finger drives. */
export const SPRING = { damping: 18, stiffness: 220, mass: 0.7 } as const;

/** A press should register instantly; anything slower feels laggy, not smooth. */
export const PRESS_SCALE = 0.97;

export const DURATION = {
  /** Colour and opacity changes that should be felt but not watched. */
  quick: 140,
  /** Content arriving or leaving. */
  enter: 240,
  /** Layout settling after a size change. */
  layout: 260,
} as const;

/**
 * Per-item delay for a list landing together.
 *
 * 35ms reads as one wave; much more and the last card feels like it is
 * lagging. Capped because a 40-venue city should not take two seconds to
 * finish arriving — after the eighth item the stagger has done its job.
 */
const STAGGER_MS = 35;
const STAGGER_MAX_INDEX = 8;

export function cardEntering(index: number) {
  return FadeInDown.duration(DURATION.enter).delay(
    Math.min(index, STAGGER_MAX_INDEX) * STAGGER_MS,
  );
}

/** Content swapping in place — the resolved venue card replacing the form. */
export const swapIn = FadeIn.duration(DURATION.enter);
export const swapOut = FadeOut.duration(DURATION.quick);

/** Containers that change height as content appears or disappears. */
export const settle = LinearTransition.duration(DURATION.layout);
