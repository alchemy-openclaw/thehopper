import { createContext, useContext } from 'react';
import type { KJ } from './types';

export type KJState = {
  /** The KJ profile owned by this device, or null if the user is not a KJ. */
  kj: KJ | null;
  /** True until the first lookup settles — used to avoid flashing the KJ tab. */
  loading: boolean;
  /** Re-resolve after onboarding or a profile edit. */
  refresh: () => Promise<void>;
  /** Set directly when a screen already has fresh data (avoids a round trip). */
  setKJ: (kj: KJ | null) => void;
};

export const KJContext = createContext<KJState | null>(null);

export function useKJContext(): KJState {
  const ctx = useContext(KJContext);
  if (!ctx) {
    throw new Error('useKJContext must be used within <KJProvider>');
  }
  return ctx;
}

export { KJProvider } from './kj-provider';
