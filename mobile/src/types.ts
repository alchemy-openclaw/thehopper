// Type definitions for TheHopper API — shared between mobile app and backend.

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

export interface ChatMessage {
  id: number;
  venue_id: number;
  nickname: string;
  message: string;
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

// --- New types for venue submission, KJ, phone verification, devices ---

export interface VenueSubmission {
  name: string;
  address: string;
  city: string;
  karaoke_nights: string[];
  start_time: string;
  end_time: string;
  kj_name?: string | null;
  phone?: string | null;
  website?: string | null;
  instagram?: string | null;
  vibe?: string | null;
  is_kj: boolean;
  submitter_phone?: string | null;
}

export interface VenueSubmissionResponse {
  id: number;
  status: string;
  message: string;
}

export interface KJ {
  id: number;
  name: string;
  phone: string;
  bio?: string | null;
  photo_url?: string | null;
  instagram?: string | null;
  website?: string | null;
  stripe_onboarding_status: string;
  verified: boolean;
  created_at: string;
}

export interface PhoneVerifyResponse {
  verified: boolean;
  token?: string | null;
}

export interface StripeOnboardResponse {
  onboarding_url: string;
  account_id: string;
}

export interface StripeStatusResponse {
  kj_id: number;
  onboarding_status: string;
  charges_enabled: boolean;
  payouts_enabled: boolean;
  missing_info?: string[];
}

export const DIFFICULTY_LABELS: Record<number, { label: string; emoji: string }> = {
  1: { label: 'Easy', emoji: '🟢' },
  2: { label: 'Easy-ish', emoji: '🟩' },
  3: { label: 'Moderate', emoji: '🟡' },
  4: { label: 'Challenging', emoji: '🟠' },
  5: { label: 'Killer', emoji: '🔴' },
};
