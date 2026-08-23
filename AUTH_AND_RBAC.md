# Authentication & Role-Based Access Control

This document describes the auth + RBAC layer added to PayperQuery. The
existing marketplace/escrow/x402 functionality is unchanged — this adds a
login system, three roles, and backend-enforced authorization + data
isolation on top of it.

> **Backend authorization is the source of truth.** The React role-based UI
> is only a presentation layer. Every rule below is enforced server-side and
> cannot be bypassed by calling the API directly — proven by `test_rbac.py`
> (46 checks, all passing).

---

## Roles

The three roles map onto the existing domain:

| Role        | Owns / controls                      | Home route          |
| ----------- | ------------------------------------ | ------------------- |
| `admin`     | Everything + escrow dispute resolution | `/admin`          |
| `publisher` | The API **listings** they published   | `/publisher`      |
| `user`      | The **agents** they operate           | `/user`           |

At signup a person may choose **user** or **publisher** (active immediately).
`admin` cannot be self-assigned — admins are created via `scripts/create_admin.py`
or by promotion from an existing admin.

---

## How to run

### 1. Backend

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then edit values (see "Environment variables")

# Fresh database (dev): tables auto-create on startup via init_models().
# Existing database with data: apply the migration instead (see below).

uvicorn app.main:app --reload   # http://localhost:8000  (docs at /docs)
```

Create the first admin (reads credentials from the environment — nothing
hardcoded):

```bash
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='a-strong-password' \
  python -m scripts.create_admin
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api, /market to :8000)
```

### 3. Existing database? Run the migration (no data loss)

If you already have a PayperQuery database with data, apply the Alembic
migration to add the `users` table and the `owner_id` columns without
wiping anything:

```bash
export DATABASE_URL="postgresql+asyncpg://.../apimarket?ssl=require"
alembic upgrade head
```

Existing listings/agents keep working; their `owner_id` starts NULL
(admins can see/manage them, and you can reassign ownership as needed).

---

## Authentication flow

```
signup / login  ──►  bcrypt-verify  ──►  issue JWT (HS256, 24h)
                                              │
             client stores token (localStorage), sends:
                     Authorization: Bearer <token>
                                              │
   every protected request ──► decode token ──► re-load user from DB
                                              │  (checks is_active + role LIVE)
                                              ▼
                          role gate ──► ownership gate ──► handler
```

Key property: authorization **re-loads the user from the database on every
request** and reads the role/status from there — it never trusts the token's
claims at a security boundary. So disabling an account or changing a role
takes effect on the *next* request, even with an unexpired token.

Passwords are hashed with **bcrypt**; plaintext is never stored. Login
returns the same generic error for unknown-email and wrong-password, so
registered emails aren't enumerable.

---

## New API endpoints

| Method | Path                              | Access        | Purpose                          |
| ------ | --------------------------------- | ------------- | -------------------------------- |
| POST   | `/api/auth/signup`                | public        | Register (user/publisher only)   |
| POST   | `/api/auth/login`                 | public        | Get an access token              |
| POST   | `/api/auth/logout`                | authenticated | Client discards token            |
| GET    | `/api/auth/me`                    | authenticated | Current user                     |
| GET    | `/api/admin/users`                | admin         | List all users                   |
| PATCH  | `/api/admin/users/{id}/role`      | admin         | Change a user's role             |
| PATCH  | `/api/admin/users/{id}/status`    | admin         | Enable/disable a user            |
| GET    | `/api/admin/stats`                | admin         | System-wide counts               |

### Existing endpoints — now protected

| Path                          | Before | After                                                        |
| ----------------------------- | ------ | ----------------------------------------------------------- |
| `/api/agents` (all)           | open   | user → own agents only; admin → all; publisher → 403        |
| `/api/listings` (all)         | open   | publisher → own listings only; admin → all; user → 403      |
| `/api/transactions`           | open   | user → own agents' txns; publisher → own listings' txns; admin → all |
| `/api/escrow/*`               | open   | admin only                                                  |
| `/market/search`              | open   | any authenticated user                                      |
| `/api/chat`                   | open   | any authenticated user                                      |
| `/market/{path}/call`         | agent key | unchanged (agent-to-machine auth via `X-Agent-Key`)      |

---

## RBAC rules (permission matrix)

| Resource               | Admin | Publisher            | User                 |
| ---------------------- | ----- | -------------------- | -------------------- |
| All users              | CRUD  | —                    | —                    |
| Any listing            | CRUD  | own only (CRUD)      | —                    |
| Any agent              | CRUD  | —                    | own only (CRUD)      |
| Marketplace search     | Yes   | Yes                  | Yes                  |
| Transactions           | all   | on own listings      | on own agents        |
| Escrow release/refund  | Yes   | —                    | —                    |
| System stats           | Yes   | own listings (via Usage) | own agents (via Activity) |

**Ownership is enforced in the database query**, e.g. a publisher fetching a
listing runs `WHERE id = :id AND owner_id = :current_user_id`. A cross-tenant
id returns **404, not 403**, so we don't leak that another owner's resource
exists. Admins skip the ownership filter.

---

## Security notes

- Identity always comes from the JWT, never from a client-sent `user_id` /
  `role` / `owner_id`.
- `owner_id` on new listings/agents is set from the authenticated user
  server-side; the client cannot spoof it.
- Secrets (`SECRET_KEY` / `JWT_SECRET`, DB URL, escrow mnemonic) come from
  environment variables — none are committed.
- HTTP status codes: `401` unauthenticated, `403` authenticated-but-forbidden,
  `404` for cross-tenant/no-leak, `409` on conflicts (duplicate email/path).

---

## Environment variables (new)

```
JWT_SECRET=                 # falls back to SECRET_KEY if blank; use a long random value in prod
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

ADMIN_EMAIL=admin@payperquery.local   # used by scripts/create_admin.py
ADMIN_PASSWORD=                        # set to create the first admin
ADMIN_NAME=Platform Admin
```

---

## Files created

**Backend**
- `app/models/user.py` — `User` model + `UserRole`
- `app/core/security.py` — bcrypt hashing + JWT create/decode
- `app/api/deps.py` — `get_current_user`, `require_role`/`require_admin`/…, ownership resolvers
- `app/api/routes_auth.py` — signup / login / logout / me
- `app/api/routes_admin.py` — user management + system stats
- `app/schemas/auth.py` — auth request/response schemas
- `scripts/create_admin.py` — bootstrap/promote the initial admin from env
- `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_add_users_and_ownership.py`
- `test_rbac.py` — 46-case end-to-end authorization test

**Frontend**
- `src/context/AuthContext.tsx` — auth state, session restore, login/signup/logout
- `src/services/api.ts` — token injection + central 401 handling (rewritten)
- `src/components/ProtectedRoute.tsx` — auth + role guard
- `src/components/Layout.tsx` — role-aware sidebar layout
- `src/pages/auth/{LoginPage,SignupPage,AuthShell}.tsx`
- `src/pages/admin/{AdminDashboard,AdminUsers}.tsx`
- `src/pages/publisher/PublisherDashboard.tsx`
- `src/pages/user/UserDashboard.tsx`

## Files modified

- `app/models/{listing,agent}.py` — added `owner_id` FK + `owner` relationship
- `app/models/__init__.py` — export `User`
- `app/core/config.py` — JWT + admin-bootstrap settings
- `app/main.py` — register auth + admin routers
- `app/api/routes_{agents,listings,escrow,dashboard,marketplace,chat}.py` — auth + ownership scoping
- `app/schemas/{agent,listing}.py` — `owner_id` in output
- `requirements.txt`, `.env.example`
- `frontend/src/App.tsx`, `main.tsx`, `types/index.ts`

## Files removed

- `frontend/src/components/NavBar.tsx`, `frontend/src/pages/DashboardPage.tsx`
  (replaced by the role-aware `Layout` + per-role dashboards)

---

## Testing

```bash
source .venv/bin/activate
python test_rbac.py        # spins up the app on SQLite, runs 46 authorization checks
```

Covers: signup/login validation, self-admin rejection, unauthenticated blocks,
tampered tokens, cross-publisher and cross-user isolation (→404), role gates
(→403), admin full access, live disable/promote enforcement.

## Remaining notes / possible next steps

- Tokens are stored in `localStorage` (standard for SPА + JWT). For stricter
  XSS posture you could move to httpOnly refresh cookies later.
- JWTs are stateless, so logout is client-side; add a token denylist only if
  you need server-side revocation before expiry.
- The `/market/{path}/call` proxy still authenticates agents by `X-Agent-Key`
  (unchanged) — a natural follow-up is linking each agent's key back to its
  owning user for per-user billing views.
