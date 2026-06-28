import { useEffect, useState } from 'react';
import type { UserPrefs } from './types';
import { DEFAULT_PREFS } from './types';

const KEY = 'thehopper_prefs';

function load(): UserPrefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_PREFS };
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_PREFS, ...parsed };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

function save(prefs: UserPrefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* ignore quota errors */
  }
}

export function usePrefs() {
  const [prefs, setPrefs] = useState<UserPrefs>(() => load());

  useEffect(() => {
    save(prefs);
  }, [prefs]);

  return [prefs, setPrefs] as const;
}

/** Ask the browser for geolocation; resolves with {lat, lng} or rejects. */
export function getGeolocation(): Promise<{ lat: number; lng: number }> {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error('Geolocation not supported by this browser.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      (err) => {
        const messages: Record<number, string> = {
          1: 'Location permission denied. Enter a city or browse all venues.',
          2: 'Location unavailable. Try again or browse all venues.',
          3: 'Location request timed out.',
        };
        reject(new Error(messages[err.code] || err.message));
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
    );
  });
}
