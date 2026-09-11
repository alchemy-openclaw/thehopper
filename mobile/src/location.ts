/**
 * Geolocation helper.
 *
 * Native implementation using expo-location.
 * On web, location.web.ts provides a navigator.geolocation fallback.
 * Metro resolves the .web extension automatically.
 */

import * as Location from 'expo-location';

/**
 * Request foreground location permission and return current coords.
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

/**
 * Coordinates when we already have permission — never a prompt.
 *
 * The distinction matters: getGeolocation() asks, which is right when someone
 * taps "Find karaoke near me" and wrong when they are halfway through typing a
 * venue name. This returns null rather than prompting, so callers can quietly
 * improve a result and quietly do without.
 *
 * getLastKnownPositionAsync is the OS's cached fix — instant, no GPS spin-up.
 * Good enough for biasing a search toward the right part of the world.
 */
export async function getGeolocationIfPermitted(): Promise<{ lat: number; lng: number } | null> {
  try {
    const { granted } = await Location.getForegroundPermissionsAsync();
    if (!granted) return null;
    const pos =
      (await Location.getLastKnownPositionAsync()) ??
      (await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Low }));
    if (!pos) return null;
    return { lat: pos.coords.latitude, lng: pos.coords.longitude };
  } catch {
    return null;
  }
}
