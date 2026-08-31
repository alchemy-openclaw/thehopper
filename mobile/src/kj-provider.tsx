import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { KJContext, type KJState } from './kj-context';
import { api } from './api';
import { getSessionToken } from './session';
import { updateDeviceMetadata } from './notifications';
import type { KJ } from './types';

/**
 * Resolves whether this device belongs to an onboarded KJ.
 *
 * Hosts need their dashboard — the pending singers list especially — reachable
 * in one tap during a live night, so this is looked up once at startup and
 * shared, rather than each screen asking independently.
 *
 * Not being a KJ is the common case and not an error: a 404 from /kjs/me just
 * means "singer", and a 401 means the stored token aged out. Both resolve to
 * null and leave the KJ surfaces hidden.
 */
export function KJProvider({ children }: { children: ReactNode }) {
  const [kj, setKJ] = useState<KJ | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const token = await getSessionToken();
    if (!token) {
      setKJ(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.getMyKJ(token);
      setKJ(me);
      // Bind this device's push token to the KJ. The backend fans out alerts
      // via `devices WHERE kj_id = ?`, so without this the token list is always
      // empty and KJ push silently never arrives — it only looked like it
      // worked because SMS was going out alongside it.
      updateDeviceMetadata({ kj_id: me.id, phone: me.phone }).catch(() => {});
    } catch {
      // 404 → not a KJ; 401 → expired token; anything else → offline. All of
      // them mean "no KJ surfaces", which beats showing a tab that errors.
      setKJ(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const state: KJState = { kj, loading, refresh, setKJ };

  return <KJContext.Provider value={state}>{children}</KJContext.Provider>;
}
