# Merge notes — PayperQuery (RBAC branch × verification/credentials branch)

This repository is the merge of two divergent branches of PayperQuery that
evolved from a common ancestor. Neither was a strict superset of the other, so
this was a real two-branch feature merge rather than a copy.

## What each branch contributed

**Branch A — `2_file_to_merge` (marketplace / verification / credentials)**
- Encrypted upstream provider credentials at rest (`app/core/crypto.py`,
  Fernet keyed off `SECRET_KEY`) — injected into the proxied upstream request
  in memory only, never returned to the buying agent.
- Provider verification, domain or wallet (`app/services/verification_service.py`
  + `/api/listings/{id}/verify/initiate|confirm`).
- Richer reputation: p50/p95 latency from a bounded per-listing sample ring
  buffer (`app/policies/reputation.py`).
- Ranked marketplace search with price / latency / success-rate / verified-only
  filters and an explainable per-result ranking reason.
- Idempotent listing publish (`idempotency_key`).
- A real `pytest` suite under `tests/`.

**Branch B — `d_merged` (auth + RBAC + frontend)**
- Human accounts with bcrypt passwords and JWT auth (`app/models/user.py`,
  `app/core/security.py`, `/api/auth/*`).
- Role-based access control and query-level tenancy isolation
  (`app/api/deps.py`): publishers see only their own listings, users only their
  own agents, admins see everything; cross-tenant ids return 404, not 403.
- Admin surface (`/api/admin/*`) and a redesigned React frontend with login /
  signup, protected + role-based routing, and per-role dashboards.
- Alembic migrations (`alembic/versions/0001_add_users_and_ownership.py`).
- The escrow watchdog was already wired in this branch (identical to A's).

## How conflicts were resolved

Branch B was taken as the base (larger structural surface: auth, RBAC,
frontend, migrations). Branch A's domain features were ported on top:

- **Drop-in (A wholesale):** `reputation.py`, `marketplace_service.py`,
  `purchase_service.py`, plus new `crypto.py` and `verification_service.py`.
  These are agent/domain logic with no RBAC interaction.
- **True three-way merges:**
  - `models/listing.py` — B's `owner_id` + `owner` relationship **and** A's
    `latency_samples`, `auth_*`, `verification_*`, `idempotency_key` columns.
  - `schemas/listing.py` — A's `AuthConfig` + verification schemas + richer
    `ListingSearchResult`, **and** B's `owner_id` on `ListingOut`.
  - `api/routes_listings.py` — B's `require_role(PUBLISHER)` + `load_owned_listing`
    ownership guards wrapped around A's credential encryption, idempotent
    publish, and verification endpoints (the verification routes are now
    ownership-guarded too).
  - `api/routes_marketplace.py` — B's `get_current_user` guard **and** A's rich
    filtering / ranking.
- **No change needed:** `main.py`, `core/config.py` (B already contained the
  watchdog wiring and all escrow/JWT settings), and the entire frontend (A had
  no UI for its backend features, so B's redesigned frontend is used as-is; the
  extra JSON fields are simply ignored by the client).
- **New migration:** `0002_add_credentials_verification_latency.py` chains onto
  `0001` and adds A's listing columns without touching existing rows.
- **Tests:** A's `tests/` were ported; their fixtures now authenticate as a
  seeded admin (`tests/_auth.py`), since the endpoints they exercise are now
  behind auth. The test bodies are otherwise unchanged.

## Verification

- Branch B's RBAC end-to-end suite (`test_rbac.py`): **46/46 pass** against the
  merged app.
- Branch A's feature suite (`tests/`): **24/24 pass** against the merged app —
  including that a provider's upstream bearer credential reaches the upstream
  call but never leaks to the agent, wallet/domain verification, idempotent
  publish, and refund/replay accounting.
