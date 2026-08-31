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

  if (runsOn(venue.karaoke_nights, today)) {
    // Underway tonight.
    if (crossesMidnight ? nowMin >= startMin : nowMin >= startMin && nowMin <= endMin) {
      return 0;
    }
    // Starting later tonight, within the lead window.
    const until = startMin - nowMin;
    if (until > 0 && until <= LINEUP_LEAD_MINUTES) return until;
  }

  // Tail of a night that began yesterday and ran past midnight.
  if (runsOn(venue.karaoke_nights, yesterday) && crossesMidnight && nowMin <= endMin) {
    return 0;
  }

  // Starts just after midnight, and we are within the lead window before it.
  if (runsOn(venue.karaoke_nights, tomorrow)) {
    const until = MINUTES_PER_DAY - nowMin + startMin;
    if (until > 0 && until <= LINEUP_LEAD_MINUTES) return until;
  }

  return null;
}

/**
 * Whole days until this venue's next karaoke night: 0 = tonight, 1 = tomorrow,
 * up to 6. Null if it has no karaoke nights at all.
 *
 * A night already finished today does not count as "tonight" — at 2am Sunday
 * nobody wants Saturday's 8pm slot presented as upcoming. Events running past
 * midnight still count as tonight until they actually end.
 */
export function daysUntilNextEvent(
  venue: VenueTimes,
  now: Date = new Date(),
): number | null {
  if (!venue.karaoke_nights || venue.karaoke_nights.length === 0) return null;

  const nowMin = now.getHours() * 60 + now.getMinutes();
  const startMin = timeToMinutes(venue.start_time);
  const endMin = timeToMinutes(venue.end_time);
  const crossesMidnight = endMin <= startMin;

  // Still inside a night that began yesterday and ran past midnight.
  const yesterday = dayName(new Date(now.getTime() - MINUTES_PER_DAY * 60 * 1000));
  if (runsOn(venue.karaoke_nights, yesterday) && crossesMidnight && nowMin <= endMin) {
    return 0;
  }

  // Scan through d = 7 so a venue running a single night a week still resolves
  // to next week once tonight's event is over — stopping at 6 leaves a
  // Monday-only venue with no next night between Mon 23:00 and midnight.
  for (let d = 0; d <= 7; d++) {
    const day = dayName(new Date(now.getTime() + d * MINUTES_PER_DAY * 60 * 1000));
    if (!runsOn(venue.karaoke_nights, day)) continue;
    // Today only counts if tonight's event has not already wrapped up. An
    // event crossing midnight has not ended while it is still today.
    if (d === 0 && !crossesMidnight && nowMin > endMin) continue;
    return d;
  }
  return null;
}

/** "Tonight" / "Tomorrow" / weekday name, or null if there is no next night. */
export function eventDayLabel(
  venue: VenueTimes,
  now: Date = new Date(),
): string | null {
  const d = daysUntilNextEvent(venue, now);
  if (d == null) return null;
  if (d === 0) return 'Tonight';
  if (d === 1) return 'Tomorrow';
  return dayName(new Date(now.getTime() + d * MINUTES_PER_DAY * 60 * 1000));
}

/** True when the venue has a night on tonight or tomorrow. */
export function hasEventSoon(venue: VenueTimes, now: Date = new Date()): boolean {
  const d = daysUntilNextEvent(venue, now);
  return d != null && d <= 1;
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
 * Does this venue run on the given weekday?
 *
 * Compares case-insensitively and ignores surrounding whitespace: real data
 * arrives as "Saturday, Sunday, Thursday", which splits into " Sunday" with a
 * leading space and would never match a bare day name.
 */
function runsOn(nights: string[], day: string): boolean {
  const target = day.toLowerCase();
  return nights.some((n) => n.trim().toLowerCase() === target);
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
  if (runsOn(venue.karaoke_nights, todayName)) {
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
  if (runsOn(venue.karaoke_nights, yesterdayName)) {
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
