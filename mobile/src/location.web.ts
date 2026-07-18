/**
 * Web geolocation helper.
 * Uses the browser's navigator.geolocation API.
 * Metro resolves this .web.ts file automatically on web builds.
 */

export async function getGeolocation(): Promise<{ lat: number; lng: number }> {
  return new Promise((resolve, reject) => {
    if (!navigator?.geolocation) {
      reject(new Error('Geolocation not supported in this browser. Enter a city or browse all venues.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      (err) => {
        const msg =
          err.code === err.PERMISSION_DENIED
            ? 'Location permission denied. Enter a city or browse all venues.'
            : 'Could not get your location. Enter a city or browse all venues.';
        reject(new Error(msg));
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    );
  });
}
