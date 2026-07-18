/**
 * Platform-agnostic secure storage.
 *
 * - Native: expo-secure-store (keychain/keystore encrypted)
 * - Web: localStorage (unencrypted, but the only option in a browser)
 *
 * This module picks the right implementation at build time:
 * Metro resolves secure-storage.web.ts for web builds automatically.
 */

export async function getItem(key: string): Promise<string | null> {
  const SecureStore = require('expo-secure-store');
  return SecureStore.getItemAsync(key);
}

export async function setItem(key: string, value: string): Promise<void> {
  const SecureStore = require('expo-secure-store');
  await SecureStore.setItemAsync(key, value);
}
