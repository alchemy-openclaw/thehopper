/**
 * Web stub for push notifications.
 * Metro resolves this .web.ts file automatically on web builds.
 * Browsers don't support Expo push tokens, so all functions are no-ops.
 */

export async function registerForPushNotifications(): Promise<string | null> {
  return null;
}

export async function updateDeviceMetadata(_data: {
  phone?: string;
  kj_id?: number;
  venue_id?: number;
}): Promise<void> {
  // no-op on web
}

export async function getStoredPushToken(): Promise<string | null> {
  return null;
}
