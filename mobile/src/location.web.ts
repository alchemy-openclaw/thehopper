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

/**
 * Coordinates when the browser has already granted permission — never prompts.
 *
 * Permissions.query tells us the state without triggering the browser's own
 * prompt, which getCurrentPosition would. Browsers that lack the Permissions
 * API report nothing, and we decline rather than risk an unexpected prompt.
 */
export async function getGeolocationIfPermitted(): Promise<{ lat: number; lng: number } | null> {
  try {
    if (!navigator?.geolocation || !navigator?.permissions?.query) return null;
    const status = await navigator.permissions.query({ name: 'geolocation' as PermissionName });
    if (status.state !== 'granted') return null;
    return await new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        () => resolve(null),
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
      );
    });
  } catch {
    return null;
  }
}
