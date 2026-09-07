/**
 * Canonical weekday list for karaoke nights.
 *
 * Storage and the event-window maths use full day names ("Monday"); the UI
 * only ever has room for a two-letter tag, so the abbreviation lives here
 * rather than being re-sliced at each call site. Monday-first matches the
 * order the Add Show / Add Venue forms have always used.
 */

export const DAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const;

export type DayName = (typeof DAYS)[number];

/**
 * "Monday" → "Mo". Two letters is what lets all seven fit on one row on a
 * narrow phone; three ("Mon"/"Tue") wraps to a second line.
 */
export function dayAbbrev(day: string): string {
  return day.slice(0, 2);
}
