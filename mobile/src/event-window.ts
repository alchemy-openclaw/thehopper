/**
 * Event window helpers.
 *
 * "Active event window" = from start_time on a karaoke night until
 * end_time + 4 hours (the tip window). Events can cross midnight
 * (e.g. 8pm-1am + 4hr tip window = 5am cutoff).
 */

const DAY_NAMES = [
  'Sunday', 'Monday', 'Tuesday', 'Wednesday',
  'Thursday', 'Friday', 'Saturday',
] as const;

/** Parse "HH:MM" 24h string into minutes since midnight. */
function timeToMinutes(t: string): number {
  const [h, m] = t.split(':').map(Number);
  return h * 60 + m;
}

const MINUTES_PER_DAY = 24 * 60;

/** How far ahead of the start time a KJ should see that night's lineup. */
export const LINEUP_LEAD_MINUTES = 60;

type VenueTimes = {
  karaoke_nights: string[];
  start_time: string;
  end_time: string;
};

/**
 * Minutes until this venue's event starts, or 0 if it is already underway.
 * Returns null when the venue has nothing running and nothing starting within
 * LINEUP_LEAD_MINUTES.
 *
 * Deliberately *excludes* the post-event tip window that isEventActive allows:
 * a KJ has no lineup to run three hours after the mic goes off, and showing a
 * stale one invites them to page singers who have gone home.
 */
export function lineupWindowOffset(
  venue: VenueTimes,
  now: Date = new Date(),
): number | null {
  const nowMin = now.getHours() * 60 + now.getMinutes();
  const startMin = timeToMinutes(venue.start_time);
  const endMin = timeToMinutes(venue.end_time);
  const crossesMidnight = endMin <= startMin;

  const today = dayName(now);
  const yesterday = dayName(new Date(now.getTime() - MINUTES_PER_DAY * 60 * 1000));
  const tomorrow = dayName(new Date(now.getTime() + MINUTES_PER_DAY * 60 * 1000));

  if (venue.karaoke_nights.includes(today)) {
    // Underway tonight.
    if (crossesMidnight ? nowMin >= startMin : nowMin >= startMin && nowMin <= endMin) {
      return 0;
    }
    // Starting later tonight, within the lead window.
    const until = startMin - nowMin;
    if (until > 0 && until <= LINEUP_LEAD_MINUTES) return until;
  }

  // Tail of a night that began yesterday and ran past midnight.
  if (venue.karaoke_nights.includes(yesterday) && crossesMidnight && nowMin <= endMin) {
    return 0;
  }

  // Starts just after midnight, and we are within the lead window before it.
  if (venue.karaoke_nights.includes(tomorrow)) {
    const until = MINUTES_PER_DAY - nowMin + startMin;
    if (until > 0 && until <= LINEUP_LEAD_MINUTES) return until;
  }

  return null;
}

/**
 * Pick the venue a KJ is most likely hosting right now: one whose night is
 * underway, else the one starting soonest within the lead window.
 *
 * A KJ with several venues works them one night at a time, so choosing by the
 * clock is both correct in practice and avoids a venue switcher for now.
 */
export function pickLineupVenue<T extends VenueTimes>(
  venues: T[],
  now: Date = new Date(),
): T | null {
  let best: { venue: T; offset: number } | null = null;
  for (const venue of venues) {
    const offset = lineupWindowOffset(venue, now);
    if (offset == null) continue;
    if (!best || offset < best.offset) best = { venue, offset };
  }
  return best ? best.venue : null;
}

/** Get the day name for a Date, accounting for timezone. */
function dayName(d: Date): string {
  return DAY_NAMES[d.getDay()];
}

/**
 * Returns true if the given venue is currently within its active event window
 * (start_time through end_time + 4 hours) on a karaoke night.
 */
export function isEventActive(venue: {
  karaoke_nights: string[];
  start_time: string;
  end_time: string;
}): boolean {
  const now = new Date();
  const todayName = dayName(now);
  const yesterdayName = dayName(new Date(now.getTime() - 24 * 60 * 60 * 1000));

  const nowMin = now.getHours() * 60 + now.getMinutes();
  const TIP_WINDOW_HOURS = 4;

  // Check if today is a karaoke night
  if (venue.karaoke_nights.includes(todayName)) {
    const startMin = timeToMinutes(venue.start_time);
    const endMin = timeToMinutes(venue.end_time);
    const tipCutoff = endMin + TIP_WINDOW_HOURS * 60;

    if (endMin > startMin) {
      // Same-day event (e.g. 8pm-11pm)
      if (nowMin >= startMin && nowMin <= tipCutoff) return true;
    } else {
      // Crosses midnight (e.g. 8pm-1am)
      // Active from start until midnight, plus the after-midnight portion
      if (nowMin >= startMin) return true; // before midnight
      // After midnight: check if within tip window
      const afterMidnightCutoff = (tipCutoff) % (24 * 60);
      if (nowMin <= afterMidnightCutoff) return true;
    }
  }

  // Check if yesterday was a karaoke night (for cross-midnight events)
  if (venue.karaoke_nights.includes(yesterdayName)) {
    const startMin = timeToMinutes(venue.start_time);
    const endMin = timeToMinutes(venue.end_time);

    // Only relevant if the event crosses midnight
    if (endMin <= startMin) {
      const tipCutoff = endMin + TIP_WINDOW_HOURS * 60;
      const afterMidnightCutoff = tipCutoff % (24 * 60);
      if (nowMin <= afterMidnightCutoff) return true;
    }
  }

  return false;
}
