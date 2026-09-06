import Constants from 'expo-constants';
import type {
  AppConfig,
  ChatMessage,
  KJ,
  LineupEntry,
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
 * - Reads EXPO_PUBLIC_API_URL from environment (.env or host env) first, so a
 *   developer can point at a test backend without editing app.json. The
 *   production backend runs live Stripe keys, so this override is the only
 *   thing standing between a local run and a real card charge.
 * - Falls back to app.json `extra` (the value baked into EAS builds).
 * - Falls back to localhost for development.
 * - On a physical device, set EXPO_PUBLIC_API_URL to your computer's LAN IP.
 */
const API_BASE: string =
  process.env.EXPO_PUBLIC_API_URL ||
  (Constants.expoConfig?.extra?.EXPO_PUBLIC_API_URL as string | undefined) ||
  'http://localhost:8000/api';

/**
 * An HTTP error carrying its status code.
 *
 * Callers need the code, not just the message: a 404 from /kjs/me means "not a
 * KJ yet" (a normal state) while a 401 means "re-verify", and the two lead to
 * completely different UI.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

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
    throw new ApiError(res.status, detail);
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

  getVenues: (lat?: number, lng?: number, city?: string, radiusMiles?: number) =>
    jsonFetch<Venue[]>(
      withQuery(`${API_BASE}/venues`, {
        lat: lat != null ? String(lat) : undefined,
        lng: lng != null ? String(lng) : undefined,
        city,
        radius_miles: radiusMiles != null ? String(radiusMiles) : undefined,
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

  /**
   * Resolve specific songs by id. Favourites live on the device as bare ids and
   * the catalog is far too large to fetch and filter locally, so they have to
   * be looked up directly.
   */
  getSongsByIds: (ids: number[]) =>
    ids.length === 0
      ? Promise.resolve([] as Song[])
      : jsonFetch<Song[]>(`${API_BASE}/songs/by-ids?ids=${ids.join(',')}`),

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

  /**
   * Start a Stripe Checkout session.
   *
   * Premium-slot pricing is server-derived — the client cannot set it. A tip is
   * the one case where the payer picks the amount, so pass kind: 'tip' with a
   * whole-dollar tip_amount_usd; the server bounds-checks it.
   */
  createPaymentSession: (
    venue_id: number,
    singer_name: string,
    song_request: string,
    options?: { kind?: 'premium_slot' | 'tip'; tip_amount_usd?: number },
  ) =>
    jsonFetch<PaymentResponse>(`${API_BASE}/create-payment-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        venue_id,
        singer_name,
        song_request,
        kind: options?.kind ?? 'premium_slot',
        ...(options?.tip_amount_usd != null
          ? { tip_amount_usd: options.tip_amount_usd }
          : {}),
      }),
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

  sendKJMessage: (venue_id: number, singer_name: string, message: string, song_request?: string, singer_phone?: string) =>
    jsonFetch<{ id: number; venue_id: number; status: string }>(`${API_BASE}/venues/${venue_id}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ singer_name, message, song_request, singer_phone }),
    }),

  savePatronProfile: (name: string, phone: string) =>
    jsonFetch<{ id: number; name: string | null; phone: string }>(`${API_BASE}/patrons/profile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, phone }),
    }),

  // --- Venue photos ---

  /**
   * Upload a venue photo. Anyone may add one while the venue has none;
   * replacing an existing photo requires the venue's KJ session token.
   *
   * Sent as multipart rather than base64 to avoid inflating a phone photo by a
   * third on the way up.
   */
  uploadVenueImage: (venue_id: number, uri: string, session_token?: string) => {
    const name = uri.split('/').pop() || 'photo.jpg';
    const ext = name.split('.').pop()?.toLowerCase();
    const type = ext === 'png' ? 'image/png' : 'image/jpeg';
    const form = new FormData();
    // React Native's FormData takes this {uri,name,type} shape, which is not
    // the DOM File the TS lib types describe.
    form.append('file', { uri, name, type } as unknown as Blob);
    return jsonFetch<Venue>(`${API_BASE}/venues/${venue_id}/image`, {
      method: 'POST',
      // Content-Type is deliberately unset: fetch must add the multipart
      // boundary itself, and setting it manually breaks the upload.
      headers: session_token ? { 'X-Session-Token': session_token } : undefined,
      body: form,
    });
  },

  /** Remove a venue photo. KJ only. */
  deleteVenueImage: (venue_id: number, session_token: string) =>
    jsonFetch<Venue>(`${API_BASE}/venues/${venue_id}/image`, {
      method: 'DELETE',
      headers: { 'X-Session-Token': session_token },
    }),

  /** Absolute URL for a stored media path. */
  mediaUrl: (path: string) =>
    path.startsWith('http') ? path : `${API_BASE.replace(/\/api$/, '')}${path}`,

  // --- Lineup (pending singers) ---

  /** Put a singer on a venue's pending list. */
  joinLineup: (
    venue_id: number,
    data: {
      singer_name: string;
      singer_phone?: string;
      song_request?: string;
      push_token?: string;
    },
  ) =>
    jsonFetch<LineupEntry>(`${API_BASE}/venues/${venue_id}/lineup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  /** KJ-only: singers still waiting at this venue. */
  getLineup: (venue_id: number, session_token: string) =>
    jsonFetch<LineupEntry[]>(`${API_BASE}/venues/${venue_id}/lineup`, {
      headers: { 'X-Session-Token': session_token },
    }),

  /** KJ-only: send the singer a time-sensitive "you're up soon" alert. */
  notifyLineupSinger: (entry_id: number, session_token: string) =>
    jsonFetch<LineupEntry>(`${API_BASE}/lineup/${entry_id}/notify`, {
      method: 'POST',
      headers: { 'X-Session-Token': session_token },
    }),

  /** KJ-only: clear a singer off the pending list. */
  completeLineupEntry: (entry_id: number, session_token: string) =>
    jsonFetch<LineupEntry>(`${API_BASE}/lineup/${entry_id}/done`, {
      method: 'POST',
      headers: { 'X-Session-Token': session_token },
    }),

  // --- Venue submission (add a karaoke spot) ---

  /**
   * Resolve the device's GPS position to candidate venues + an address hint
   * for the Add Show "At Current Location" flow.
   */
  nearbyLookup: (lat: number, lng: number) =>
    jsonFetch<{
      matched_venues: Venue[];
      nearby_venues: Venue[];
      address_hint: string | null;
    }>(
      withQuery(`${API_BASE}/venues/nearby-lookup`, {
        lat: String(lat),
        lng: String(lng),
      }),
    ),

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

  registerKJ: (data: { name: string; phone: string; bio?: string; instagram?: string; website?: string; business_name?: string; city?: string }) =>
    jsonFetch<KJ>(`${API_BASE}/kjs/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  /**
   * The KJ profile belonging to the caller's verified number.
   * Throws with status 404 when the number has never onboarded as a KJ, and
   * 401 when the token is missing/expired — callers must distinguish the two.
   */
  getMyKJ: (session_token: string) =>
    jsonFetch<KJ>(`${API_BASE}/kjs/me`, {
      headers: { 'X-Session-Token': session_token },
    }),

  /**
   * Edit stage name and/or phone. Moving the number additionally requires
   * `new_phone_token` — a token from verifying the *new* number.
   */
  updateKJProfile: (
    kj_id: number,
    session_token: string,
    data: { name?: string; phone?: string; new_phone_token?: string },
  ) =>
    jsonFetch<KJ>(`${API_BASE}/kjs/${kj_id}/profile`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Token': session_token,
      },
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

  /** Update one or more KJ preferences. Omitted fields are left unchanged. */
  updateKJSettings: (
    kj_id: number,
    settings: {
      song_request_required?: boolean;
      notify_push?: boolean;
      notify_sms?: boolean;
      available_for_hire?: boolean;
      hire_note?: string;
    },
  ) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(settings)) {
      if (v != null) params.set(k, String(v));
    }
    return jsonFetch<KJ>(`${API_BASE}/kjs/${kj_id}/settings?${params.toString()}`, {
      method: 'PATCH',
    });
  },

  kjStripeOnboard: (kj_id: number, email: string, kyc?: {
    business_name?: string;
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
      if (kyc.business_name) params.set('business_name', kyc.business_name);
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

  kjAddVenue: (kj_id: number, data: {
    name: string;
    address: string;
    city: string;
    karaoke_nights?: string[];
    start_time?: string;
    end_time?: string;
    phone?: string;
    website?: string;
    instagram?: string;
    vibe?: string;
  }) =>
    jsonFetch<{ status: string; venue_id?: number; submission_id?: number; message: string }>(
      `${API_BASE}/kjs/${kj_id}/venues`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      },
    ),

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
