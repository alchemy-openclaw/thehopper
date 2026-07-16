/**
 * Push notification setup using expo-notifications.
 *
 * On first launch, requests permission and registers the push token
 * with the backend. The token is stored in SecureStore for re-use
 * across app launches.
 */

import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { api } from './api';

const TOKEN_KEY = 'thehopper_push_token';

// Configure how notifications appear when the app is in the foreground
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export async function registerForPushNotifications(): Promise<string | null> {
  // Already registered?
  const existing = await SecureStore.getItemAsync(TOKEN_KEY);
  if (existing) return existing;

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== 'granted') {
    return null;
  }

  const token = (await Notifications.getExpoPushTokenAsync()).data;

  // Save locally
  await SecureStore.setItemAsync(TOKEN_KEY, token);

  // Register with backend
  try {
    await api.registerDevice({
      push_token: token,
      platform: Platform.OS,
    });
  } catch {
    // Backend might not be reachable yet — token is saved locally for retry
  }

  return token;
}

/** Re-register the device token with additional metadata (phone, kj_id, etc.) */
export async function updateDeviceMetadata(data: {
  phone?: string;
  kj_id?: number;
  venue_id?: number;
}): Promise<void> {
  const token = await SecureStore.getItemAsync(TOKEN_KEY);
  if (!token) return;
  try {
    await api.registerDevice({
      push_token: token,
      platform: Platform.OS,
      ...data,
    });
  } catch {
    // silent
  }
}

export async function getStoredPushToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}
