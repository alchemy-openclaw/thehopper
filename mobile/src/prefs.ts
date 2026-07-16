import { useCallback, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Location from 'expo-location';
import type { UserPrefs } from './types';
import { DEFAULT_PREFS } from './types';

const KEY = 'thehopper_prefs';

async function load(): Promise<UserPrefs> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_PREFS };
    const parsed = JSON.parse(raw) as Partial<UserPrefs>;
    return { ...DEFAULT_PREFS, ...parsed };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

async function save(prefs: UserPrefs): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* ignore quota errors */
  }
}

export type PrefsTuple = readonly [UserPrefs, (updater: (p: UserPrefs) => UserPrefs) => void];

/**
 * Persistent user preferences backed by AsyncStorage.
 * Mirrors the web app's usePrefs hook (localStorage → AsyncStorage).
 */
export function usePrefs(): PrefsTuple {
  const [prefs, setPrefs] = useState<UserPrefs>(DEFAULT_PREFS);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    load().then((p) => {
      setPrefs(p);
      setLoaded(true);
    });
  }, []);

  useEffect(() => {
    if (loaded) void save(prefs);
  }, [prefs, loaded]);

  const update = useCallback((updater: (p: UserPrefs) => UserPrefs) => {
    setPrefs((prev) => updater(prev));
  }, []);

  return [prefs, update] as const;
}

/**
 * Request foreground location permission and return current coords.
 * Mirrors the web app's getGeolocation() helper.
 */
export async function getGeolocation(): Promise<{ lat: number; lng: number }> {
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== 'granted') {
    throw new Error('Location permission denied. Enter a city or browse all venues.');
  }
  const pos = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.Balanced,
  });
  return { lat: pos.coords.latitude, lng: pos.coords.longitude };
}

/** Toggle a song id in the favorites array, returning a new prefs object. */
export function toggleFavorite(prefs: UserPrefs, songId: number): UserPrefs {
  const has = prefs.favorites.includes(songId);
  return {
    ...prefs,
    favorites: has
      ? prefs.favorites.filter((x) => x !== songId)
      : [...prefs.favorites, songId],
  };
}
