import { createContext, useContext } from 'react';
import type { Venue } from './types';

export type VenueState = {
  selectedVenue: Venue | null;
  selectVenue: (venue: Venue) => void;
  clearVenue: () => void;
};

export const VenueContext = createContext<VenueState | null>(null);

export function useVenueContext(): VenueState {
  const ctx = useContext(VenueContext);
  if (!ctx) {
    throw new Error('useVenueContext must be used within <VenueProvider>');
  }
  return ctx;
}

export { VenueProvider } from './venue-provider';
