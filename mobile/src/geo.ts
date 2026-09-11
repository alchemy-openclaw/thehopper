/**
 * Location with a remembered last position.
 *
 * getGeolocation() (see location.ts / location.web.ts) always prompts and
 * always waits on the GPS. The address lookup needs neither: it only wants a
 * rough anchor to bias results toward, and asking for the location permission
 * because someone started typing a street name is the wrong trade. So every
 * successful fix is cached here, and the lookup reads the cache silently.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { getGeolocation, getGeolocationIfPermitted } from './location';

export type Coords = { lat: number; lng: number };

const KEY = 'karaokespot_last_geo';

/** Persist a fix. Never throws — a failed write only costs us the anchor. */
export async function rememberGeo(coords: Coords): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(coords));
  } catch {
    /* ignore */
  }
}

/** The most recent fix from any earlier search, or null if there has been none. */
export async function getLastKnownGeo(): Promise<Coords | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Coords>;
    if (typeof parsed.lat === 'number' && typeof parsed.lng === 'number') {
      return { lat: parsed.lat, lng: parsed.lng };
    }
  } catch {
    /* fall through */
  }
  return null;
}

/**
 * The best anchor available without ever prompting.
 *
 * Prefers a live fix when permission is already granted — someone who has
 * allowed location should get results near where they actually are, even on
 * their first search, without having had to run a near-me search first to
 * seed the cache. Falls back to the remembered fix, then to nothing, and the
 * server anchors on its own default from there.
 */
export async function getAnchorQuietly(): Promise<Coords | null> {
  const live = await getGeolocationIfPermitted();
  if (live) {
    void rememberGeo(live);
    return live;
  }
  return getLastKnownGeo();
}

/**
 * getGeolocation(), caching the result for later anchoring. Use this in place
 * of the raw helper anywhere the user has actively asked for their location.
 */
export async function getGeolocationCached(): Promise<Coords> {
  const coords = await getGeolocation();
  void rememberGeo(coords);
  return coords;
}
