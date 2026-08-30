/**
 * Money display.
 *
 * Prices in this app are whole US dollars — nothing charges cents, and showing
 * "$5.00" for a fixed $5 slot is just noise. Everything user-facing goes
 * through here so the format stays consistent.
 *
 * USD only for now; if other currencies are ever needed this is the one place
 * that has to learn about them.
 */

/** Round to whole dollars. Stored prices are floats, so guard the display. */
export function dollars(amount: number): number {
  return Math.max(0, Math.round(amount || 0));
}

/** Format as "$5". */
export function formatUsd(amount: number): string {
  return `$${dollars(amount)}`;
}
