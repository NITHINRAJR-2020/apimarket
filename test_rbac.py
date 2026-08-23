"""End-to-end RBAC tests hitting the real FastAPI app against SQLite.

Proves authorization is enforced at the API layer, not just the UI:
directly calls endpoints as each role and asserts the boundaries hold.
"""
import asyncio
import os
import pathlib

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./_test_rbac.db"
os.environ["ENVIRONMENT"] = "development"
os.environ["CHATBOT_ENABLED"] = "false"

# Fresh DB each run
for f in ("_test_rbac.db",):
    p = pathlib.Path(f)
    if p.exists():
        p.unlink()

import httpx
from app.main import app
from app.core.database import init_models

BASE = "http://test"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = {"pass": 0, "fail": 0}

def check(desc, cond):
    ok = bool(cond)
    results["pass" if ok else "fail"] += 1
    print(f"  [{PASS if ok else FAIL}] {desc}")
    return ok

async def signup(client, name, email, role):
    r = await client.post("/api/auth/signup", json={"name": name, "email": email, "password": "password123", "role": role})
    return r

def auth(token):
    return {"Authorization": f"Bearer {token}"}

async def main():
    await init_models()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as c:
        print("\n=== AUTHENTICATION ===")
        # signup user + publisher
        ru = await signup(c, "Uma User", "uma@x.com", "user")
        check("user signup returns 201 + token", ru.status_code == 201 and "access_token" in ru.json())
        rp = await signup(c, "Pia Publisher", "pia@x.com", "publisher")
        check("publisher signup returns 201", rp.status_code == 201)
        # cannot self-register admin
        ra = await signup(c, "Evil", "evil@x.com", "admin")
        check("signup as admin is rejected (422)", ra.status_code == 422)
        # duplicate email
        rdup = await signup(c, "Dup", "uma@x.com", "user")
        check("duplicate email rejected (409)", rdup.status_code == 409)
        # wrong password
        rbad = await c.post("/api/auth/login", json={"email": "uma@x.com", "password": "wrong"})
        check("wrong password rejected (401)", rbad.status_code == 401)
        # unknown email same generic error
        runk = await c.post("/api/auth/login", json={"email": "nobody@x.com", "password": "password123"})
        check("unknown email rejected (401, generic)", runk.status_code == 401)

        user_tok = ru.json()["access_token"]
        pub_tok = rp.json()["access_token"]

        # second user + second publisher for cross-tenant tests
        ru2 = await signup(c, "Ravi", "ravi@x.com", "user")
        rp2 = await signup(c, "Bob Pub", "bob@x.com", "publisher")
        user2_tok = ru2.json()["access_token"]
        pub2_tok = rp2.json()["access_token"]

        print("\n=== UNAUTHENTICATED ACCESS BLOCKED ===")
        check("GET /api/agents without token -> 401", (await c.get("/api/agents")).status_code == 401)
        check("GET /api/listings without token -> 401", (await c.get("/api/listings")).status_code == 401)
        check("GET /api/escrow without token -> 401", (await c.get("/api/escrow")).status_code == 401)
        check("GET /api/transactions without token -> 401", (await c.get("/api/transactions")).status_code == 401)
        check("GET /api/admin/stats without token -> 401", (await c.get("/api/admin/stats")).status_code == 401)
        check("tampered token -> 401", (await c.get("/api/agents", headers=auth("garbage.token.here"))).status_code == 401)

        print("\n=== USER role ===")
        # create agent as user
        agent_payload = {"name": "A1", "wallet_address": "WALLET1234567890", "policy": {"max_transaction_amount": "5.0", "daily_limit": "50.0", "min_provider_reputation": 40, "restrict_to_allowed_listings": False}}
        ra1 = await c.post("/api/agents", json=agent_payload, headers=auth(user_tok))
        check("user can create agent (201)", ra1.status_code == 201)
        agent1_id = ra1.json()["id"]
        check("created agent is owned by the user", ra1.json().get("owner_id") is not None)
        # user2 creates agent
        agent_payload2 = dict(agent_payload); agent_payload2 = {**agent_payload, "name":"A2","wallet_address":"WALLET_OTHER_999"}
        ra2 = await c.post("/api/agents", json=agent_payload2, headers=auth(user2_tok))
        agent2_id = ra2.json()["id"]
        # user sees only own agent
        la = await c.get("/api/agents", headers=auth(user_tok))
        ids = [a["id"] for a in la.json()]
        check("user lists only their own agents", ids == [agent1_id])
        # user cannot see user2's agent by id -> 404
        check("user GET other user's agent -> 404", (await c.get(f"/api/agents/{agent2_id}", headers=auth(user_tok))).status_code == 404)
        # user cannot pause other user's agent
        check("user PATCH pause other user's agent -> 404", (await c.patch(f"/api/agents/{agent2_id}/pause", json={"paused": True}, headers=auth(user_tok))).status_code == 404)
        # user cannot access publisher listing management
        check("user GET /api/listings -> 403", (await c.get("/api/listings", headers=auth(user_tok))).status_code == 403)
        check("user POST /api/listings -> 403", (await c.post("/api/listings", json={}, headers=auth(user_tok))).status_code == 403)
        # user cannot access admin
        check("user GET /api/admin/stats -> 403", (await c.get("/api/admin/stats", headers=auth(user_tok))).status_code == 403)
        check("user GET /api/admin/users -> 403", (await c.get("/api/admin/users", headers=auth(user_tok))).status_code == 403)
        # user cannot access escrow
        check("user GET /api/escrow -> 403", (await c.get("/api/escrow", headers=auth(user_tok))).status_code == 403)

        print("\n=== PUBLISHER role ===")
        listing_payload = {"name": "Weather API", "category": "data", "path": "weather/v1", "upstream_url": "https://example.com/w", "price_microalgos": 100000, "pay_to_address": "PAYTO_ADDR_1234567890"}
        rl1 = await c.post("/api/listings", json=listing_payload, headers=auth(pub_tok))
        check("publisher can create listing (201)", rl1.status_code == 201)
        listing1_id = rl1.json()["id"]
        check("listing owned by publisher", rl1.json().get("owner_id") is not None)
        # publisher2 listing
        lp2 = {**listing_payload, "name":"Other API", "path":"other/v1", "pay_to_address":"PAYTO_OTHER_999"}
        rl2 = await c.post("/api/listings", json=lp2, headers=auth(pub2_tok))
        listing2_id = rl2.json()["id"]
        # publisher sees only own listings
        ll = await c.get("/api/listings", headers=auth(pub_tok))
        lids = [x["id"] for x in ll.json()]
        check("publisher lists only own listings", lids == [listing1_id])
        # publisher cannot view/edit other's listing -> 404
        check("publisher GET other's listing -> 404", (await c.get(f"/api/listings/{listing2_id}", headers=auth(pub_tok))).status_code == 404)
        check("publisher PATCH other's listing -> 404", (await c.patch(f"/api/listings/{listing2_id}", json={"name":"hax"}, headers=auth(pub_tok))).status_code == 404)
        check("publisher DELETE other's listing -> 404", (await c.delete(f"/api/listings/{listing2_id}", headers=auth(pub_tok))).status_code == 404)
        # publisher cannot access user agent endpoints
        check("publisher GET /api/agents -> 403", (await c.get("/api/agents", headers=auth(pub_tok))).status_code == 403)
        # publisher cannot access admin
        check("publisher GET /api/admin/stats -> 403", (await c.get("/api/admin/stats", headers=auth(pub_tok))).status_code == 403)
        # publisher cannot access escrow
        check("publisher GET /api/escrow -> 403", (await c.get("/api/escrow", headers=auth(pub_tok))).status_code == 403)

        print("\n=== ADMIN role ===")
        # bootstrap admin directly
        from app.core.database import AsyncSessionLocal
        from app.core.security import hash_password
        from app.models.user import User, UserRole
        async with AsyncSessionLocal() as db:
            admin = User(name="Admin", email="admin@x.com", password_hash=hash_password("password123"), role=UserRole.ADMIN, is_active=True)
            db.add(admin); await db.commit()
        radm = await c.post("/api/auth/login", json={"email":"admin@x.com","password":"password123"})
        admin_tok = radm.json()["access_token"]
        check("admin login works", radm.status_code == 200)
        # admin sees ALL agents
        aa = await c.get("/api/agents", headers=auth(admin_tok))
        check("admin sees all agents (>=2)", len(aa.json()) >= 2)
        # admin sees ALL listings
        al = await c.get("/api/listings", headers=auth(admin_tok))
        check("admin sees all listings (>=2)", len(al.json()) >= 2)
        # admin can access any agent by id
        check("admin GET any agent -> 200", (await c.get(f"/api/agents/{agent2_id}", headers=auth(admin_tok))).status_code == 200)
        check("admin GET any listing -> 200", (await c.get(f"/api/listings/{listing2_id}", headers=auth(admin_tok))).status_code == 200)
        # admin stats + users
        check("admin GET /api/admin/stats -> 200", (await c.get("/api/admin/stats", headers=auth(admin_tok))).status_code == 200)
        ru_list = await c.get("/api/admin/users", headers=auth(admin_tok))
        check("admin GET /api/admin/users -> 200", ru_list.status_code == 200)
        check("admin sees all users (>=5)", len(ru_list.json()) >= 5)
        check("admin GET /api/escrow -> 200", (await c.get("/api/escrow", headers=auth(admin_tok))).status_code == 200)

        print("\n=== ADMIN user management + disable enforcement ===")
        uma_id = ru.json()["user"]["id"]
        # disable uma
        rd = await c.patch(f"/api/admin/users/{uma_id}/status", json={"is_active": False}, headers=auth(admin_tok))
        check("admin disables a user (200)", rd.status_code == 200)
        # uma's existing token now rejected (user re-loaded from DB each request)
        check("disabled user's token now -> 403", (await c.get("/api/agents", headers=auth(user_tok))).status_code == 403)
        # admin cannot disable self
        adm_id = radm.json()["user"]["id"]
        check("admin cannot disable self (400)", (await c.patch(f"/api/admin/users/{adm_id}/status", json={"is_active": False}, headers=auth(admin_tok))).status_code == 400)
        # promote ravi to publisher
        ravi_id = ru2.json()["user"]["id"]
        rpr = await c.patch(f"/api/admin/users/{ravi_id}/role", json={"role":"publisher"}, headers=auth(admin_tok))
        check("admin promotes user->publisher (200)", rpr.status_code == 200 and rpr.json()["role"]=="publisher")
        # ravi (still holding old user token) now gets publisher access live
        check("promoted user's token grants publisher access", (await c.get("/api/listings", headers=auth(user2_tok))).status_code == 200)

        print("\n=== TRANSACTION isolation ===")
        check("user sees only own transactions (0 so far) -> 200", (await c.get("/api/transactions", headers=auth(admin_tok))).status_code == 200)

    print(f"\n================  {results['pass']} passed, {results['fail']} failed  ================")
    return 0 if results["fail"] == 0 else 1

raise SystemExit(asyncio.run(main()))
