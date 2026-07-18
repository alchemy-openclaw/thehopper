/**
 * Web implementation of secure storage.
 * Uses localStorage (browsers have no keychain equivalent).
 * Metro resolves this .web.ts file automatically on web builds.
 */

export async function getItem(key: string): Promise<string | null> {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export async function setItem(key: string, value: string): Promise<void> {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage full or blocked — ignore
  }
}
