/**
 * Phone session token storage.
 *
 * The token is minted by POST /phone/verify and proves the holder controls a
 * particular phone number. It is what lets a returning KJ land on their own
 * profile without verifying again, and what authorises edits to it.
 */
import { getItem, setItem } from './secure-storage';

const SESSION_TOKEN_KEY = 'thehopper_session_token';

export function getSessionToken(): Promise<string | null> {
  return getItem(SESSION_TOKEN_KEY).catch(() => null);
}

export async function setSessionToken(token: string): Promise<void> {
  try {
    await setItem(SESSION_TOKEN_KEY, token);
  } catch {
    // A failed write only costs the user a re-verify next launch.
  }
}
