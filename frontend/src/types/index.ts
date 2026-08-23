export type TransactionStatus =
  | "PENDING"
  | "POLICY_BLOCKED"
  | "QUOTE_ISSUED"
  | "PAYMENT_SUBMITTED"
  | "ESCROW_HELD"
  | "UPSTREAM_CALLED"
  | "SERVICE_COMPLETED"
  | "FAILED"
  | "REFUNDED"
  | "DISPUTED";

export type EscrowStatus = "HELD" | "RELEASED" | "REFUNDED" | "DISPUTED";

export interface SpendingPolicy {
  max_transaction_amount: string;
  daily_limit: string;
  min_provider_reputation: number;
  restrict_to_allowed_listings: boolean;
}

export interface Agent {
  id: string;
  owner_id: string | null;
  name: string;
  wallet_address: string;
  api_key: string;
  is_active: boolean;
  is_paused: boolean;
  created_at: string;
  policy: SpendingPolicy | null;
}

export interface Listing {
  id: string;
  owner_id: string | null;
  name: string;
  description: string | null;
  category: string;
  path: string;
  upstream_url: string;
  price_microalgos: number;
  asa_id: number | null;
  pay_to_address: string;
  successful_transactions: number;
  failed_transactions: number;
  average_latency_ms: number;
  is_active: boolean;
  created_at: string;
}

export interface ListingSearchResult extends Listing {
  reputation_score: number;
}

export interface Transaction {
  id: string;
  agent_id: string;
  listing_id: string | null;
  amount_microalgos: number;
  status: TransactionStatus;
  deposit_tx_id: string | null;
  payer_address: string | null;
  risk_score: number | null;
  response_status_code: number | null;
  failure_reason: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface Escrow {
  id: string;
  transaction_id: string;
  status: EscrowStatus;
  amount_microalgos: number;
  platform_fee_microalgos: number;
  deposit_tx_id: string;
  payout_tx_id: string | null;
  refund_tx_id: string | null;
  notes: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface QuotePreview {
  x402Version: number;
  scheme: string;
  network: string;
  resource: string;
  description: string;
  payTo: string;
  maxAmountRequired: string;
  asset: string;
  quote: string;
  expiresAt: string;
  note?: string;
}

// --- Auth / RBAC types ---
export type UserRole = "admin" | "publisher" | "user";

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface AdminStats {
  users: { total: number; active: number; publishers: number; regular_users: number; admins: number };
  listings: { total: number; active: number };
  agents: { total: number; active: number; paused: number };
  transactions: { total: number };
  escrow: { held: number; released: number; refunded: number; disputed: number };
}
