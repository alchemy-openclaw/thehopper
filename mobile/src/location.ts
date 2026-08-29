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
