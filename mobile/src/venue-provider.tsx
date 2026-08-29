import { useCallback, useEffect, useState, type ReactNode } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { VenueContext, type VenueState } from './venue-context';
import type { Venue } from './types';

const KEY = 'thehopper_selected_venue';

/**
 * Provides the currently selected venue to all tabs.
 * Persisted in AsyncStorage so the Event tab can show
 * the last-selected venue even after an app restart.
 */
export function VenueProvider({ children }: { children: ReactNode }) {
  const [selectedVenue, setSelectedVenue] = useState<Venue | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((raw) => {
        if (raw) {
          try {
            setSelectedVenue(JSON.parse(raw) as Venue);
          } catch {
            /* ignore malformed */
          }
        }
      })
      .catch(() => {});
  }, []);

  const selectVenue = useCallback((venue: Venue) => {
    setSelectedVenue(venue);
    AsyncStorage.setItem(KEY, JSON.stringify(venue)).catch(() => {});
  }, []);

  const clearVenue = useCallback(() => {
    setSelectedVenue(null);
    AsyncStorage.removeItem(KEY).catch(() => {});
  }, []);

  const state: VenueState = { selectedVenue, selectVenue, clearVenue };

  return <VenueContext.Provider value={state}>{children}</VenueContext.Provider>;
}
