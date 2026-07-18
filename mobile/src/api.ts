import Constants from 'expo-constants';
import type {
  AppConfig,
  ChatMessage,
  KJ,
  PaymentResponse,
  PhoneVerifyResponse,
  Song,
  StripeOnboardResponse,
  StripeStatusResponse,
  Suggestion,
  Venue,
  VenueSubmission,
  VenueSubmissionResponse,
  VocalRange,
} from './types';

/**
 * API base URL.
 * - Reads EXPO_PUBLIC_API_URL from environment (.env or host env).
 * - Falls back to localhost for development.
 * - On a physical device, set EXPO_PUBLIC_API_URL to your computer's LAN IP.
 */
const API_BASE: string =
  (Constants.expoConfig?.extra?.EXPO_PUBLIC_API_URL as string | undefined) ||
  process.env.EXPO_PUBLIC_API_URL ||
  'http://localhost:8000/api';

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

function withQuery(base: string, params: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') sp.set(k, v);
  }
  const q = sp.toString();
  return q ? `${base}?${q}` : base;
}

export const api = {
  getConfig: () => jsonFetch<AppConfig>(`${API_BASE}/config`),

  getVenues: (lat?: number, lng?: number, city?: string) =>
    jsonFetch<Venue[]>(
      withQuery(`${API_BASE}/venues`, {
        lat: lat != null ? String(lat) : undefined,
        lng: lng != null ? String(lng) : undefined,
        city,
      }),
    ),

  getVenue: (id: number) => jsonFetch<Venue>(`${API_BASE}/venues/${id}`),

  getSongs: (search?: string, genre?: string, limit?: number) =>
    jsonFetch<Song[]>(
      withQuery(`${API_BASE}/songs`, {
        search,
        genre,
        limit: limit != null ? String(limit) : undefined,
      }),
    ),

  getRanges: () => jsonFetch<{ ranges: VocalRange[] }>(`${API_BASE}/songs/ranges`),

  getSuggestions: (
    vocal_range: string,
    favorite_artists: string[],
    favorite_genres: string[],
    limit = 12,
  ) =>
    jsonFetch<Suggestion[]>(`${API_BASE}/song-suggestions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vocal_range, favorite_artists, favorite_genres, limit }),
    }),

  createPaymentSession: (
    venue_id: number,
    singer_name: string,
    song_request: string,
  ) =>
    jsonFetch<PaymentResponse>(`${API_BASE}/create-payment-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ venue_id, singer_name, song_request }),
    }),

  getVenueChat: (venue_id: number, since?: number) =>
    jsonFetch<ChatMessage[]>(
      withQuery(`${API_BASE}/venues/${venue_id}/chat`, {
        since: since != null ? String(since) : undefined,
      }),
    ),

  postVenueChat: (venue_id: number, nickname: string, message: string) =>
    jsonFetch<ChatMessage>(`${API_BASE}/venues/${venue_id}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname, message }),
    }),

  // --- Venue submission (add a karaoke spot) ---

  submitVenue: (submission: VenueSubmission) =>
    jsonFetch<VenueSubmissionResponse>(`${API_BASE}/venues/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(submission),
    }),

  // --- Phone verification ---

  sendPhoneCode: (phone: string) =>
    jsonFetch<{ status: string; message: string }>(`${API_BASE}/phone/send-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone }),
    }),

  verifyPhone: (phone: string, code: string) =>
    jsonFetch<PhoneVerifyResponse>(`${API_BASE}/phone/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, code }),
    }),

  // --- KJ (Karaoke Jockey) ---

  registerKJ: (data: { name: string; phone: string; bio?: string; instagram?: string; website?: string }) =>
    jsonFetch<KJ>(`${API_BASE}/kjs/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  getKJ: (id: number) => jsonFetch<KJ>(`${API_BASE}/kjs/${id}`),

  listKJs: () => jsonFetch<KJ[]>(`${API_BASE}/kjs`),

  linkKJToVenue: (kj_id: number, venue_id: number) =>
    jsonFetch<{ status: string }>(`${API_BASE}/kjs/link-venue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kj_id, venue_id }),
    }),

  getKJVenues: (kj_id: number) => jsonFetch<Venue[]>(`${API_BASE}/kjs/${kj_id}/venues`),

  kjStripeOnboard: (kj_id: number, email: string, kyc?: {
    first_name?: string;
    last_name?: string;
    dob_day?: number;
    dob_month?: number;
    dob_year?: number;
    address_line1?: string;
    address_city?: string;
    address_state?: string;
    address_postal_code?: string;
    ssn_last_4?: string;
  }) => {
    let url = `${API_BASE}/kjs/${kj_id}/stripe-onboard?email=${encodeURIComponent(email)}`;
    if (kyc) {
      const params = new URLSearchParams();
      if (kyc.first_name) params.set('first_name', kyc.first_name);
      if (kyc.last_name) params.set('last_name', kyc.last_name);
      if (kyc.dob_day) params.set('dob_day', String(kyc.dob_day));
      if (kyc.dob_month) params.set('dob_month', String(kyc.dob_month));
      if (kyc.dob_year) params.set('dob_year', String(kyc.dob_year));
      if (kyc.address_line1) params.set('address_line1', kyc.address_line1);
      if (kyc.address_city) params.set('address_city', kyc.address_city);
      if (kyc.address_state) params.set('address_state', kyc.address_state);
      if (kyc.address_postal_code) params.set('address_postal_code', kyc.address_postal_code);
      if (kyc.ssn_last_4) params.set('ssn_last_4', kyc.ssn_last_4);
      const qs = params.toString();
      if (qs) url += `&${qs}`;
    }
    return jsonFetch<StripeOnboardResponse>(url, { method: 'POST' });
  },

  kjStripeStatus: (kj_id: number) =>
    jsonFetch<StripeStatusResponse>(`${API_BASE}/kjs/${kj_id}/stripe-status`),

  // --- Device registration (push tokens) ---

  registerDevice: (data: { push_token: string; platform?: string; phone?: string; kj_id?: number; venue_id?: number }) =>
    jsonFetch<{ status: string }>(`${API_BASE}/devices/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
};

export { API_BASE };
