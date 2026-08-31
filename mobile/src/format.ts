/**
 * Display formatting for venue times.
 *
 * Times are stored as 24h "HH:MM" strings — that is what the KJ types and what
 * the event-window maths needs — but US venue listings read as "9 PM", so the
 * conversion happens at the display layer only. Nothing here should be fed back
 * into storage.
 */

/** "20:00" → "8 PM", "20:30" → "8:30 PM". Returns the input if unparseable. */
export function formatTime12h(time: string): string {
  if (!time) return '';
  const parts = time.trim().split(':');
  const h = Number(parts[0]);
  const m = parts.length > 1 ? Number(parts[1]) : 0;
  if (!Number.isFinite(h) || !Number.isFinite(m)) return time;

  const suffix = h >= 12 && h < 24 ? 'PM' : 'AM';
  // 0 → 12 AM, 12 → 12 PM, 13 → 1 PM.
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  // Drop ":00" — "8 PM" reads better than "8:00 PM" on a crowded card.
  return m === 0 ? `${hour12} ${suffix}` : `${hour12}:${String(m).padStart(2, '0')} ${suffix}`;
}

/** "20:00","01:00" → "8 PM – 1 AM". */
export function formatTimeRange(start: string, end: string): string {
  const s = formatTime12h(start);
  const e = formatTime12h(end);
  if (!s && !e) return '';
  if (!e) return s;
  if (!s) return e;
  return `${s} – ${e}`;
}
