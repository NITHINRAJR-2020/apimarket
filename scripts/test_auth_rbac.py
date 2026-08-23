"""
End-to-end Authentication + RBAC test for PayperQuery.

Tests the auth/RBAC layer directly against the backend:
- signup/login/me
- duplicate signup and self-admin rejection
- unauthenticated protection
- publisher -> own listings
- user -> own agents
- cross-role 403s
- owner_id spoofing protection
- marketplace authentication
- transaction access
- admin users/stats/escrow access
- logout behavior

Run:
    export ADMIN_EMAIL="admin@payperquery.local"
    export ADMIN_PASSWORD="your-admin-password"
    python scripts/test_auth_rbac.py --base-url http://localhost:8000
"""

import argparse
import os
import sys
import uuid

import httpx


PASSED = 0
FAILED = 0


def check(condition: bool, message: str):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"   ✓ {message}")
    else:
        FAILED += 1
        print(f"   ✗ {message}")


def headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def expect(response, status: int, message: str):
    check(
        response.status_code == status,
        f"{message} (expected {status}, got {response.status_code})",
    )


def signup(client, email, password, name, role):
    return client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": password,
            "name": name,
            "role": role,
        },
    )


def login(client, email, password):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )


def get_token(response):
    body = response.json()
    return body.get("access_token") or body.get("token")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    client = httpx.Client(
        base_url=args.base_url,
        timeout=30.0,
    )

    suffix = uuid.uuid4().hex[:10]
    password = "RBAC-Test-" + uuid.uuid4().hex + "A1!"

    publisher_email = f"publisher-{suffix}@example.com"
    user_email = f"user-{suffix}@example.com"

    admin_email = os.getenv(
        "ADMIN_EMAIL",
        "admin@payperquery.local",
    )
    admin_password = os.getenv("ADMIN_PASSWORD")

    print("=" * 72)
    print("PAYPERQUERY AUTH + RBAC TEST")
    print("=" * 72)
    print(f"Backend: {args.base_url}")

    # ------------------------------------------------------------------
    # 1. Unauthenticated requests
    # ------------------------------------------------------------------

    print("\n1. Unauthenticated access")

    expect(
        client.get("/api/auth/me"),
        401,
        "/api/auth/me requires authentication",
    )

    expect(
        client.get("/api/admin/users"),
        401,
        "/api/admin/users requires authentication",
    )

    expect(
        client.get("/api/admin/stats"),
        401,
        "/api/admin/stats requires authentication",
    )

    # ------------------------------------------------------------------
    # 2. Publisher signup
    # ------------------------------------------------------------------

    print("\n2. Publisher signup")

    response = signup(
        client,
        publisher_email,
        password,
        f"Test Publisher {suffix}",
        "publisher",
    )

    if response.status_code not in (200, 201):
        print(response.text)

    expect(
        response,
        201,
        "publisher signup succeeds",
    )

    if response.status_code in (200, 201):
        publisher = response.json()
        check(
            publisher.get("role") == "publisher",
            "publisher receives publisher role",
        )

    # ------------------------------------------------------------------
    # 3. User signup
    # ------------------------------------------------------------------

    print("\n3. User signup")

    response = signup(
        client,
        user_email,
        password,
        f"Test User {suffix}",
        "user",
    )

    if response.status_code not in (200, 201):
        print(response.text)

    expect(
        response,
        201,
        "user signup succeeds",
    )

    # ------------------------------------------------------------------
    # 4. Self-admin rejection
    # ------------------------------------------------------------------

    print("\n4. Self-admin protection")

    response = signup(
        client,
        f"fake-admin-{suffix}@example.com",
        password,
        "Fake Admin",
        "admin",
    )

    check(
        response.status_code in (400, 403, 422),
        "public signup cannot create an admin",
    )

    # ------------------------------------------------------------------
    # 5. Duplicate signup
    # ------------------------------------------------------------------

    print("\n5. Duplicate email protection")

    response = signup(
        client,
        publisher_email,
        password,
        "Duplicate",
        "publisher",
    )

    expect(
        response,
        409,
        "duplicate email returns 409",
    )

    # ------------------------------------------------------------------
    # 6. Login
    # ------------------------------------------------------------------

    print("\n6. Login")

    response = login(
        client,
        publisher_email,
        password,
    )

    expect(
        response,
        200,
        "publisher login succeeds",
    )

    publisher_token = get_token(response)

    check(
        bool(publisher_token),
        "publisher receives access token",
    )

    response = login(
        client,
        user_email,
        password,
    )

    expect(
        response,
        200,
        "user login succeeds",
    )

    user_token = get_token(response)

    check(
        bool(user_token),
        "user receives access token",
    )

    # ------------------------------------------------------------------
    # 7. Wrong password
    # ------------------------------------------------------------------

    print("\n7. Wrong password")

    response = login(
        client,
        publisher_email,
        "wrong-password",
    )

    check(
        response.status_code in (400, 401),
        "wrong password is rejected",
    )

    # ------------------------------------------------------------------
    # 8. /me
    # ------------------------------------------------------------------

    print("\n8. Current-user endpoint")

    response = client.get(
        "/api/auth/me",
        headers=headers(publisher_token),
    )

    expect(
        response,
        200,
        "publisher can access /me",
    )

    publisher_me = response.json()

    check(
        publisher_me.get("email") == publisher_email,
        "publisher identity is correct",
    )

    check(
        publisher_me.get("role") == "publisher",
        "publisher role is correct",
    )

    response = client.get(
        "/api/auth/me",
        headers=headers(user_token),
    )

    expect(
        response,
        200,
        "user can access /me",
    )

    user_me = response.json()

    check(
        user_me.get("email") == user_email,
        "user identity is correct",
    )

    # ------------------------------------------------------------------
    # 9. Publisher creates listing
    # ------------------------------------------------------------------

    print("\n9. Publisher listing ownership")

    listing_path = f"rbac-test-{suffix}"

    listing_payload = {
        "name": f"RBAC Test Listing {suffix}",
        "description": "Temporary RBAC test listing",
        "category": "testing",
        "path": listing_path,
        "upstream_url": (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=52.52&longitude=13.41"
            "&current_weather=true"
        ),
        "price_microalgos": 100000,
        # Only used as listing data; no payment is made by this test.
        "pay_to_address": (
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            "AAAAAAAAAAAAAAAAAAAAY5HFKQ"
        ),
        "asa_id": 10458941,
    }

    response = client.post(
        "/api/listings",
        headers=headers(publisher_token),
        json=listing_payload,
    )

    if response.status_code not in (200, 201):
        print(response.text)

    expect(
        response,
        201,
        "publisher can create listing",
    )

    listing_id = None

    if response.status_code in (200, 201):
        listing = response.json()
        listing_id = listing.get("id")

        check(
            listing_id is not None,
            "listing has an id",
        )

        check(
            str(listing.get("owner_id"))
            == str(publisher_me.get("id")),
            "listing owner_id is assigned by server",
        )

    # Publisher can read its own listing.
    if listing_id:
        response = client.get(
            f"/api/listings/{listing_id}",
            headers=headers(publisher_token),
        )

        expect(
            response,
            200,
            "publisher can read own listing",
        )

        # User cannot read publisher's listing.
        response = client.get(
            f"/api/listings/{listing_id}",
            headers=headers(user_token),
        )

        expect(
            response,
            403,
            "user cannot access publisher listing",
        )

    # User cannot use listing collection.
    response = client.get(
        "/api/listings",
        headers=headers(user_token),
    )

    expect(
        response,
        403,
        "user cannot access listing management",
    )

    # ------------------------------------------------------------------
    # 10. User creates agent
    # ------------------------------------------------------------------

    print("\n10. User agent ownership")

    agent_payload = {
        "name": f"RBAC Test Agent {suffix}",
        "wallet_address": (
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            "AAAAAAAAAAAAAAAAAAAAY5HFKQ"
        ),
        "policy": {
            "max_transaction_amount": "5.00",
            "daily_limit": "50.00",
            "min_provider_reputation": 0,
        },
    }

    response = client.post(
        "/api/agents",
        headers=headers(user_token),
        json=agent_payload,
    )

    if response.status_code not in (200, 201):
        print(response.text)

    expect(
        response,
        201,
        "user can create agent",
    )

    agent_id = None

    if response.status_code in (200, 201):
        agent = response.json()
        agent_id = agent.get("id")

        check(
            agent_id is not None,
            "agent has an id",
        )

        check(
            str(agent.get("owner_id"))
            == str(user_me.get("id")),
            "agent owner_id is assigned by server",
        )

    # User can read own agent.
    if agent_id:
        response = client.get(
            f"/api/agents/{agent_id}",
            headers=headers(user_token),
        )

        expect(
            response,
            200,
            "user can read own agent",
        )

        # Publisher cannot read it.
        response = client.get(
            f"/api/agents/{agent_id}",
            headers=headers(publisher_token),
        )

        expect(
            response,
            403,
            "publisher cannot access user agent",
        )

    # Publisher cannot manage agents.
    response = client.get(
        "/api/agents",
        headers=headers(publisher_token),
    )

    expect(
        response,
        403,
        "publisher cannot access agent management",
    )

    # ------------------------------------------------------------------
    # 11. owner_id spoofing
    # ------------------------------------------------------------------

    print("\n11. owner_id spoofing protection")

    spoof = dict(agent_payload)
    spoof["owner_id"] = publisher_me.get("id")

    response = client.post(
        "/api/agents",
        headers=headers(user_token),
        json=spoof,
    )

    if response.status_code in (200, 201):
        created = response.json()

        check(
            str(created.get("owner_id"))
            == str(user_me.get("id")),
            "client cannot spoof agent owner_id",
        )
    else:
        check(
            response.status_code in (400, 422),
            "spoofed owner_id is rejected",
        )

    # ------------------------------------------------------------------
    # 12. Marketplace search
    # ------------------------------------------------------------------

    print("\n12. Marketplace authentication")

    response = client.get(
        "/market/search",
        headers=headers(user_token),
    )

    expect(
        response,
        200,
        "authenticated user can search marketplace",
    )

    response = client.get(
        "/market/search",
        headers=headers(publisher_token),
    )

    expect(
        response,
        200,
        "authenticated publisher can search marketplace",
    )

    response = client.get("/market/search")

    expect(
        response,
        401,
        "unauthenticated marketplace search is rejected",
    )

    # ------------------------------------------------------------------
    # 13. Transactions
    # ------------------------------------------------------------------

    print("\n13. Transaction authorization")

    response = client.get(
        "/api/transactions",
        headers=headers(user_token),
    )

    expect(
        response,
        200,
        "user can access transaction endpoint",
    )

    response = client.get(
        "/api/transactions",
        headers=headers(publisher_token),
    )

    expect(
        response,
        200,
        "publisher can access transaction endpoint",
    )

    response = client.get("/api/transactions")

    expect(
        response,
        401,
        "unauthenticated transaction access is rejected",
    )

    # ------------------------------------------------------------------
    # 14. Escrow admin-only
    # ------------------------------------------------------------------

    print("\n14. Escrow role gate")

    response = client.get(
        "/api/escrow",
        headers=headers(user_token),
    )

    expect(
        response,
        403,
        "user cannot access escrow",
    )

    response = client.get(
        "/api/escrow",
        headers=headers(publisher_token),
    )

    expect(
        response,
        403,
        "publisher cannot access escrow",
    )

    # ------------------------------------------------------------------
    # 15. Chat authentication
    # ------------------------------------------------------------------

    print("\n15. Chat authentication")

    response = client.get(
        "/api/chat",
        headers=headers(user_token),
    )

    check(
        response.status_code in (200, 405),
        "authenticated chat route is reachable",
    )

    response = client.get("/api/chat")

    check(
        response.status_code in (401, 405),
        "unauthenticated chat is protected/method-gated",
    )

    # ------------------------------------------------------------------
    # 16. Admin
    # ------------------------------------------------------------------

    print("\n16. Admin access")

    if not admin_password:
        print(
            "   ! ADMIN_PASSWORD is not set; "
            "skipping admin login checks."
        )
        print(
            "   Set ADMIN_PASSWORD and rerun for full admin coverage."
        )
    else:
        response = login(
            client,
            admin_email,
            admin_password,
        )

        expect(
            response,
            200,
            "admin login succeeds",
        )

        if response.status_code == 200:
            admin_token = get_token(response)

            check(
                bool(admin_token),
                "admin receives access token",
            )

            response = client.get(
                "/api/auth/me",
                headers=headers(admin_token),
            )

            expect(
                response,
                200,
                "admin can access /me",
            )

            admin_me = response.json()

            check(
                admin_me.get("role") == "admin",
                "admin role is active",
            )

            response = client.get(
                "/api/admin/users",
                headers=headers(admin_token),
            )

            expect(
                response,
                200,
                "admin can list users",
            )

            if response.status_code == 200:
                users = response.json()
                check(
                    isinstance(users, list),
                    "admin users endpoint returns a list",
                )

                emails = {
                    u.get("email")
                    for u in users
                    if isinstance(u, dict)
                }

                check(
                    publisher_email in emails,
                    "admin sees test publisher",
                )

                check(
                    user_email in emails,
                    "admin sees test user",
                )

            response = client.get(
                "/api/admin/stats",
                headers=headers(admin_token),
            )

            expect(
                response,
                200,
                "admin can access system stats",
            )

            response = client.get(
                "/api/escrow",
                headers=headers(admin_token),
            )

            expect(
                response,
                200,
                "admin can access escrow",
            )

            response = client.get(
                "/api/listings",
                headers=headers(admin_token),
            )

            expect(
                response,
                200,
                "admin can access all listings",
            )

            response = client.get(
                "/api/agents",
                headers=headers(admin_token),
            )

            expect(
                response,
                200,
                "admin can access all agents",
            )

    # ------------------------------------------------------------------
    # 17. Logout
    # ------------------------------------------------------------------

    print("\n17. Logout")

    response = client.post(
        "/api/auth/logout",
        headers=headers(user_token),
    )

    expect(
        response,
        200,
        "authenticated user can logout",
    )

    # JWTs are stateless according to the patch/report, so logout is
    # client-side unless a denylist is later introduced.
    response = client.get(
        "/api/auth/me",
        headers=headers(user_token),
    )

    check(
        response.status_code == 200,
        "stateless JWT remains valid after client-side logout",
    )

    client.close()

    print("\n" + "=" * 72)
    print("RBAC TEST SUMMARY")
    print("=" * 72)
    print(f"Passed: {PASSED}")
    print(f"Failed: {FAILED}")

    if FAILED:
        print("\n❌ RBAC TEST FAILED")
        sys.exit(1)

    print("\n✅ RBAC TEST PASSED")


if __name__ == "__main__":
    main()
