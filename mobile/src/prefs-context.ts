import { createContext, useContext } from 'react';
import type { PrefsTuple } from './prefs';

/**
 * Context that exposes the persistent user prefs tuple to all screens.
 * Provided by RootLayout via <PrefsProvider>.
 */
export const PrefsContext = createContext<PrefsTuple | null>(null);

export function usePrefsContext(): PrefsTuple {
  const ctx = useContext(PrefsContext);
  if (!ctx) {
    throw new Error('usePrefsContext must be used within <PrefsProvider>');
  }
  return ctx;
}

export { PrefsProvider } from './prefs-provider';
