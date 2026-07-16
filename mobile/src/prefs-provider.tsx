import type { ReactNode } from 'react';
import { PrefsContext } from './prefs-context';
import { usePrefs } from './prefs';

/**
 * Provides persistent user prefs (vocal range, favorites, etc.) to the app.
 * Backed by AsyncStorage via the usePrefs hook.
 */
export function PrefsProvider({ children }: { children: ReactNode }) {
  const prefs = usePrefs();
  return <PrefsContext.Provider value={prefs}>{children}</PrefsContext.Provider>;
}
