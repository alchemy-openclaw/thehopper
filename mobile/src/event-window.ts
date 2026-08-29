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
