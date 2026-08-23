import type {
  Agent,
  AdminStats,
  AuthResponse,
  Escrow,
  Listing,
  ListingSearchResult,
  QuotePreview,
  Transaction,
  User,
  UserRole,
} from "../types";

// --- API base URL ---------------------------------------------------------
// In dev, Vite's proxy (see vite.config.ts) forwards /api, /market, /health
// to localhost:8000, so a relative path works fine there.
// In production the frontend is usually deployed on a different origin than
// the backend (e.g. this app on Vercel/Netlify, backend on Render), so
// relative paths would hit the wrong host. VITE_API_BASE_URL lets the build
// point at the real backend; it defaults to the deployed Render backend so
// the app works out of the box even without a .env file.
const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ||
  "https://apimarket-mp7s.onrender.com";

class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed with ${status}`,
    );
    this.status = status;
    this.body = body;
  }
}

// --- Auth token plumbing -------------------------------------------------
// The token lives here so every request carries it; AuthContext keeps this
// in sync with React state + localStorage, and registers a handler so a
// 401 anywhere logs the user out centrally.
const TOKEN_KEY = "ppq_token";
let authToken: string | null = localStorage.getItem(TOKEN_KEY);
let onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}
export function getAuthToken() {
  return authToken;
}
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;

  // In dev, keep hitting relative paths so Vite's proxy handles them.
  // In a production build, prefix with the real backend origin.
  const url = import.meta.env.DEV ? path : `${API_BASE_URL}${path}`;

  const res = await fetch(url, { ...options, headers });

  // Central 401 handling: session expired or invalid -> log out.
  if (res.status === 401) {
    if (onUnauthorized) onUnauthorized();
    const body = await res.json().catch(() => ({ detail: "Not authenticated" }));
    throw new ApiError(401, body);
  }

  if (res.status === 204) return undefined as T;

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json() : await res.text();
  if (!res.ok && res.status !== 402) {
    throw new ApiError(res.status, body);
  }
  return body as T;
}

export const api = {
  health: () =>
    request<{ status: string; network: string; escrow_wallet: string }>("/health"),

  // --- Auth ---
  signup: (payload: { name: string; email: string; password: string; role: UserRole }) =>
    request<AuthResponse>("/api/auth/signup", { method: "POST", body: JSON.stringify(payload) }),
  login: (payload: { email: string; password: string }) =>
    request<AuthResponse>("/api/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  logout: () => request<{ detail: string }>("/api/auth/logout", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),

  // --- Admin ---
  adminStats: () => request<AdminStats>("/api/admin/stats"),
  adminListUsers: (role?: UserRole) =>
    request<User[]>(`/api/admin/users${role ? `?role=${role}` : ""}`),
  adminSetUserRole: (userId: string, role: UserRole) =>
    request<User>(`/api/admin/users/${userId}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    }),
  adminSetUserStatus: (userId: string, isActive: boolean) =>
    request<User>(`/api/admin/users/${userId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    }),

  // --- Agents (user-owned) ---
  listAgents: () => request<Agent[]>("/api/agents"),
  createAgent: (payload: {
    name: string;
    wallet_address: string;
    policy: {
      max_transaction_amount: string;
      daily_limit: string;
      min_provider_reputation: number;
      restrict_to_allowed_listings: boolean;
    };
  }) => request<Agent>("/api/agents", { method: "POST", body: JSON.stringify(payload) }),
  setAgentPaused: (agentId: string, paused: boolean) =>
    request<Agent>(`/api/agents/${agentId}/pause`, {
      method: "PATCH",
      body: JSON.stringify({ paused }),
    }),

  // --- Listings (publisher-owned) ---
  listListings: (includeInactive = false) =>
    request<Listing[]>(`/api/listings${includeInactive ? "?include_inactive=true" : ""}`),
  createListing: (payload: {
    name: string;
    description?: string;
    category: string;
    path: string;
    upstream_url: string;
    price_microalgos: number;
    pay_to_address: string;
    asa_id?: number | null;
  }) => request<Listing>("/api/listings", { method: "POST", body: JSON.stringify(payload) }),
  deactivateListing: (listingId: string) =>
    request<void>(`/api/listings/${listingId}`, { method: "DELETE" }),

  // --- Marketplace search (any authenticated user) ---
  searchMarketplace: (params: { q?: string; category?: string; min_reputation?: number }) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.category) qs.set("category", params.category);
    if (params.min_reputation) qs.set("min_reputation", String(params.min_reputation));
    return request<ListingSearchResult[]>(`/market/search?${qs.toString()}`);
  },

  previewQuote: (path: string, apiKey: string) =>
    request<QuotePreview>(`/market/${path}/call`, { headers: { "X-Agent-Key": apiKey } }),

  // --- Transactions (role-scoped server-side) ---
  listTransactions: (params?: { agent_id?: string; status_filter?: string }) => {
    const qs = new URLSearchParams();
    if (params?.agent_id) qs.set("agent_id", params.agent_id);
    if (params?.status_filter) qs.set("status_filter", params.status_filter);
    return request<Transaction[]>(`/api/transactions?${qs.toString()}`);
  },

  // --- Escrow (admin only) ---
  listEscrows: (statusFilter?: string) =>
    request<Escrow[]>(`/api/escrow${statusFilter ? `?status_filter=${statusFilter}` : ""}`),
  releaseEscrow: (escrowId: string, notes?: string) =>
    request<Escrow>(`/api/escrow/${escrowId}/release`, {
      method: "POST",
      body: JSON.stringify({ notes }),
    }),
  refundEscrow: (escrowId: string, notes?: string) =>
    request<Escrow>(`/api/escrow/${escrowId}/refund`, {
      method: "POST",
      body: JSON.stringify({ notes }),
    }),

  // --- Support chatbot ---
  sendChatMessage: (
    message: string,
    history: { role: "user" | "assistant"; content: string }[],
  ) =>
    request<{ reply: string }>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    }),
};

export { ApiError };
