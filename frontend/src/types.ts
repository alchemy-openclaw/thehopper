// Type definitions for TheHopper API

export interface Venue {
  id: number;
  name: string;
  address: string;
  city: string;
  lat: number;
  lng: number;
  karaoke_nights: string[];
  start_time: string;
  end_time: string;
  kj_name: string | null;
  phone: string | null;
  website: string | null;
  price_jump_queue: number;
  premium_slot_position: number;
  premium_slot_price: number;
  vibe: string | null;
  distance_miles: number | null;
}

export interface Song {
  id: number;
  title: string;
  artist: string;
  genre: string;
  year: number | null;
  difficulty: number; // 1..5
  range_fit: string[];
  notes: string | null;
}

export interface Suggestion {
  song: Song;
  score: number;
  reason: string;
}

export interface VocalRange {
  value: string;
  label: string;
  desc: string;
}

export interface AppConfig {
  stripe_publishable_key: string;
  stripe_configured: boolean;
}

export interface PaymentResponse {
  checkout_url: string;
  session_id: string;
}

export interface KJMessageResponse {
  id: number;
  venue_id: number;
  singer_name: string;
  message: string;
  song_request: string | null;
  created_at: string;
}

export interface UserPrefs {
  vocal_range: string;
  favorite_artists: string;
  favorite_genres: string;
  favorites: number[]; // song ids
}

export const DEFAULT_PREFS: UserPrefs = {
  vocal_range: '',
  favorite_artists: '',
  favorite_genres: '',
  favorites: [],
};

export const DIFFICULTY_LABELS: Record<number, { label: string; emoji: string }> = {
  1: { label: 'Easy', emoji: '🟢' },
  2: { label: 'Easy-ish', emoji: '🟩' },
  3: { label: 'Moderate', emoji: '🟡' },
  4: { label: 'Challenging', emoji: '🟠' },
  5: { label: 'Killer', emoji: '🔴' },
};

/** Human-readable ordinal for a slot position: 1 -> "1st", 2 -> "2nd", 3 -> "3rd". */
export function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}
