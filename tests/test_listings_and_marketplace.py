import os
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import Base, engine
from app.main import app
from tests._auth import seed_admin_token


@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers["Authorization"] = f"Bearer {await seed_admin_token()}"
        yield c
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _listing_payload(**overrides):
    payload = {
        "name": "Weather API",
        "path": f"weather-{uuid.uuid4().hex[:8]}",
        "upstream_url": "https://example.com/weather",
        "price_microalgos": 1000,
        "pay_to_address": "P" * 58,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_credentials_never_returned_on_create(client: AsyncClient):
    payload = _listing_payload(auth={"type": "bearer", "bearer_token": "TOP-SECRET"})
    r = await client.post("/api/listings", json=payload)
    assert r.status_code == 201
    assert "TOP-SECRET" not in r.text
    assert "encrypted_credentials" not in r.json()


@pytest.mark.asyncio
async def test_credentials_never_returned_on_get_or_list(client: AsyncClient):
    payload = _listing_payload(auth={"type": "api_key", "api_key": "sk-live-abc"})
    created = (await client.post("/api/listings", json=payload)).json()

    r = await client.get(f"/api/listings/{created['id']}")
    assert "sk-live-abc" not in r.text

    r2 = await client.get("/api/listings")
    assert "sk-live-abc" not in r2.text


@pytest.mark.asyncio
async def test_invalid_auth_config_rejected(client: AsyncClient):
    payload = _listing_payload(auth={"type": "bearer"})  # missing bearer_token
    r = await client.post("/api/listings", json=payload)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_listing_publish_idempotency(client: AsyncClient):
    key = str(uuid.uuid4())
    payload = _listing_payload(idempotency_key=key)
    r1 = await client.post("/api/listings", json=payload)
    r2 = await client.post("/api/listings", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


@pytest.mark.asyncio
async def test_duplicate_path_without_idempotency_key_conflicts(client: AsyncClient):
    payload = _listing_payload()
    r1 = await client.post("/api/listings", json=payload)
    r2 = await client.post("/api/listings", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_marketplace_search_backward_compatible_params(client: AsyncClient):
    await client.post("/api/listings", json=_listing_payload(name="Weather API", category="weather"))
    r = await client.get("/market/search", params={"q": "weather", "category": "weather", "min_reputation": 0})
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_marketplace_search_new_filters(client: AsyncClient):
    await client.post("/api/listings", json=_listing_payload(name="Cheap API", price_microalgos=100))
    await client.post("/api/listings", json=_listing_payload(name="Pricey API", price_microalgos=100_000))

    r = await client.get("/market/search", params={"max_price": 500})
    names = [item["name"] for item in r.json()]
    assert "Cheap API" in names
    assert "Pricey API" not in names


@pytest.mark.asyncio
async def test_marketplace_search_verified_only_filter(client: AsyncClient):
    unverified = (await client.post("/api/listings", json=_listing_payload(name="Unverified"))).json()

    r_all = await client.get("/market/search")
    r_verified = await client.get("/market/search", params={"verified_only": True})
    assert any(x["name"] == "Unverified" for x in r_all.json())
    assert not any(x["name"] == "Unverified" for x in r_verified.json())


@pytest.mark.asyncio
async def test_search_result_never_leaks_secrets_and_has_ranking_reason(client: AsyncClient):
    await client.post(
        "/api/listings",
        json=_listing_payload(name="Secretive API", auth={"type": "bearer", "bearer_token": "shh"}),
    )
    r = await client.get("/market/search")
    assert "shh" not in r.text
    result = r.json()[0]
    assert "ranking_reason" in result and result["ranking_reason"]
    assert "p95_latency_ms" in result
    assert "success_rate" in result


@pytest.mark.asyncio
async def test_domain_verification_fails_without_real_proof(client: AsyncClient):
    listing = (await client.post("/api/listings", json=_listing_payload())).json()
    init = await client.post(
        f"/api/listings/{listing['id']}/verify/initiate", json={"method": "domain", "domain": "example.invalid"}
    )
    assert init.status_code == 200
    assert init.json()["verification_status"] == "verification_pending"

    confirm = await client.post(f"/api/listings/{listing['id']}/verify/confirm", json={})
    assert confirm.status_code == 422

    # still unverified after a failed confirm
    got = await client.get(f"/api/listings/{listing['id']}")
    assert got.json()["verification_status"] == "verification_pending"


@pytest.mark.asyncio
async def test_wallet_verification_succeeds_with_valid_signature(client: AsyncClient):
    from algosdk import account
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import base64

    private_key, address = account.generate_account()
    # algosdk mnemonic-derived key isn't directly an Ed25519PrivateKey object,
    # so re-derive raw seed bytes for signing via `cryptography`.
    import algosdk.encoding as enc
    raw_key = base64.b64decode(private_key)[:32]
    signing_key = Ed25519PrivateKey.from_private_bytes(raw_key)

    listing = (await client.post("/api/listings", json=_listing_payload(pay_to_address=address))).json()
    init = await client.post(f"/api/listings/{listing['id']}/verify/initiate", json={"method": "wallet"})
    token = init.json()["verification_token"]

    signature = signing_key.sign(token.encode("utf-8"))
    confirm = await client.post(
        f"/api/listings/{listing['id']}/verify/confirm",
        json={"signed_message": base64.b64encode(signature).decode()},
    )
    assert confirm.status_code == 200
    assert confirm.json()["verification_status"] == "verified"
