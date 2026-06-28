import type {
  AppConfig,
  KJMessageResponse,
  PaymentResponse,
  Song,
  Suggestion,
  Venue,
  VocalRange,
} from './types';

const BASE = '/api';

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

export const api = {
  getConfig: () => jsonFetch<AppConfig>(`${BASE}/config`),

  getVenues: (lat?: number, lng?: number, city?: string) => {
    const params = new URLSearchParams();
    if (lat != null) params.set('lat', String(lat));
    if (lng != null) params.set('lng', String(lng));
    if (city) params.set('city', city);
    const q = params.toString();
    return jsonFetch<Venue[]>(`${BASE}/venues${q ? '?' + q : ''}`);
  },

  getVenue: (id: number) => jsonFetch<Venue>(`${BASE}/venues/${id}`),

  getSongs: (search?: string, genre?: string) => {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    if (genre) params.set('genre', genre);
    const q = params.toString();
    return jsonFetch<Song[]>(`${BASE}/songs${q ? '?' + q : ''}`);
  },

  getRanges: () => jsonFetch<{ ranges: VocalRange[] }>(`${BASE}/songs/ranges`),

  getSuggestions: (
    vocal_range: string,
    favorite_artists: string[],
    favorite_genres: string[],
    limit = 12,
  ) =>
    jsonFetch<Suggestion[]>(`${BASE}/song-suggestions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        vocal_range,
        favorite_artists,
        favorite_genres,
        limit,
      }),
    }),

  createPaymentSession: (
    venue_id: number,
    singer_name: string,
    song_request: string,
  ) =>
    jsonFetch<PaymentResponse>(`${BASE}/create-payment-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ venue_id, singer_name, song_request }),
    }),

  sendKJMessage: (
    venue_id: number,
    singer_name: string,
    message: string,
    song_request: string,
  ) =>
    jsonFetch<KJMessageResponse>(`${BASE}/venues/${venue_id}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        venue_id,
        singer_name,
        message,
        song_request,
      }),
    }),
};
