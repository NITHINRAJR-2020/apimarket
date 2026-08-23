import os
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.database import Base, engine
from app.main import app
from tests._auth import seed_admin_token
from app.payments.algorand_verifier import VerifiedPayment
from app.payments.escrow_wallet import PayoutResult


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


async def _make_agent(client: AsyncClient, min_reputation: int = 0) -> dict:
    payload = {
        "name": "Test Agent",
        "wallet_address": "W" * 58,
        "policy": {
            "max_transaction_amount": "100.00",
            "daily_limit": "1000.00",
            "min_provider_reputation": min_reputation,
        },
    }
    r = await client.post("/api/agents", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def _make_listing(client: AsyncClient, **overrides) -> dict:
    payload = {
        "name": "Test API",
        "path": f"test-{uuid.uuid4().hex[:8]}",
        "upstream_url": "https://upstream.example.com/do-thing",
        "price_microalgos": 1000,
        "pay_to_address": "P" * 58,
    }
    payload.update(overrides)
    r = await client.post("/api/listings", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _fake_verified_payment(tx_id: str) -> VerifiedPayment:
    return VerifiedPayment(
        tx_id=tx_id, payer_address="AGENTWALLET", receiver_address="ESCROW",
        amount=1000, asa_id=None, confirmed_round=1,
    )


class _FakeUpstreamResponse:
    def __init__(self, status_code=200, headers=None, content=b'{"ok":true}'):
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}
        self.content = content


class _FakeAsyncClient:
    def __init__(self, *args, response=None, capture_headers=None, **kwargs):
        self._response = response or _FakeUpstreamResponse()
        self._capture = capture_headers

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def request(self, method, url, headers=None, params=None, content=None):
        if self._capture is not None:
            self._capture.update(headers or {})
        return self._response


@pytest.mark.asyncio
async def test_full_success_flow_releases_escrow_and_updates_reputation(client: AsyncClient):
    agent = await _make_agent(client)
    listing = await _make_listing(client, auth={"type": "bearer", "bearer_token": "SECRET-UPSTREAM-TOKEN"})

    captured_headers: dict = {}

    with patch(
        "app.services.purchase_service.verify_payment",
        new=AsyncMock(return_value=_fake_verified_payment("TXID1")),
    ), patch(
        "app.services.purchase_service.escrow_wallet.compute_platform_fee_microalgos", return_value=25
    ), patch(
        "app.services.purchase_service.escrow_wallet.release_to_provider",
        return_value=PayoutResult(tx_id="PAYOUT1", from_address="ESCROW", to_address="PROVIDER", amount_microalgos=975, asa_id=None),
    ), patch(
        "app.services.purchase_service.httpx.AsyncClient",
        lambda *a, **kw: _FakeAsyncClient(*a, capture_headers=captured_headers, **kw),
    ):
        headers = {"X-Agent-Key": agent["api_key"]}
        r1 = await client.get(f"/market/{listing['path']}/call", headers=headers)
        assert r1.status_code == 402
        quote = r1.json()

        headers2 = dict(headers)
        headers2["X-402-Payment-Proof"] = f'{{"tx_id": "TXID1", "quote": "{quote["quote"]}"}}'
        r2 = await client.get(f"/market/{listing['path']}/call", headers=headers2)
        assert r2.status_code == 200

    # Upstream must have received the decrypted provider credential...
    assert captured_headers.get("Authorization") == "Bearer SECRET-UPSTREAM-TOKEN"

    # ...but the AGENT must never see it.
    assert "SECRET-UPSTREAM-TOKEN" not in r2.text
    assert "Authorization" not in dict(r2.headers)

    updated_listing = (await client.get(f"/api/listings/{listing['id']}")).json()
    assert updated_listing["successful_transactions"] == 1
    assert updated_listing["failed_transactions"] == 0


@pytest.mark.asyncio
async def test_upstream_failure_refunds_and_counts_failure_and_refund(client: AsyncClient):
    agent = await _make_agent(client)
    listing = await _make_listing(client)

    with patch(
        "app.services.purchase_service.verify_payment",
        new=AsyncMock(return_value=_fake_verified_payment("TXID2")),
    ), patch(
        "app.services.purchase_service.escrow_wallet.compute_platform_fee_microalgos", return_value=0
    ), patch(
        "app.services.purchase_service.escrow_wallet.refund_to_agent",
        return_value=PayoutResult(tx_id="REFUND1", from_address="ESCROW", to_address="AGENT", amount_microalgos=1000, asa_id=None),
    ), patch(
        "app.services.purchase_service.httpx.AsyncClient",
        lambda *a, **kw: _FakeAsyncClient(*a, response=_FakeUpstreamResponse(status_code=500), **kw),
    ):
        headers = {"X-Agent-Key": agent["api_key"]}
        r1 = await client.get(f"/market/{listing['path']}/call", headers=headers)
        quote = r1.json()
        headers2 = dict(headers)
        headers2["X-402-Payment-Proof"] = f'{{"tx_id": "TXID2", "quote": "{quote["quote"]}"}}'
        r2 = await client.get(f"/market/{listing['path']}/call", headers=headers2)
        # The upstream's own status is proxied through as-is; the refund
        # happens transparently behind it.
        assert r2.status_code == 500

    updated = (await client.get(f"/api/listings/{listing['id']}")).json()
    assert updated["failed_transactions"] == 1


@pytest.mark.asyncio
async def test_idempotent_purchase_retry_does_not_double_charge(client: AsyncClient):
    agent = await _make_agent(client)
    listing = await _make_listing(client)
    idem_key = str(uuid.uuid4())

    call_count = {"n": 0}

    class CountingClient(_FakeAsyncClient):
        async def request(self, *a, **kw):
            call_count["n"] += 1
            return await super().request(*a, **kw)

    with patch(
        "app.services.purchase_service.verify_payment",
        new=AsyncMock(return_value=_fake_verified_payment("TXID3")),
    ), patch(
        "app.services.purchase_service.escrow_wallet.compute_platform_fee_microalgos", return_value=0
    ), patch(
        "app.services.purchase_service.escrow_wallet.release_to_provider",
        return_value=PayoutResult(tx_id="PAYOUT3", from_address="E", to_address="P", amount_microalgos=1000, asa_id=None),
    ), patch(
        "app.services.purchase_service.httpx.AsyncClient", lambda *a, **kw: CountingClient(*a, **kw)
    ):
        headers = {"X-Agent-Key": agent["api_key"], "X-Idempotency-Key": idem_key}
        r1 = await client.get(f"/market/{listing['path']}/call", headers=headers)
        quote = r1.json()
        headers2 = dict(headers)
        headers2["X-402-Payment-Proof"] = f'{{"tx_id": "TXID3", "quote": "{quote["quote"]}"}}'
        r2 = await client.get(f"/market/{listing['path']}/call", headers=headers2)
        assert r2.status_code == 200

        # Retry with the SAME idempotency key -- must not re-call upstream,
        # re-charge, or move escrow again.
        r3 = await client.get(f"/market/{listing['path']}/call", headers=headers2)
        assert r3.status_code == 200

    assert call_count["n"] == 1  # upstream was only ever actually called once

    updated = (await client.get(f"/api/listings/{listing['id']}")).json()
    assert updated["successful_transactions"] == 1  # not double-counted


@pytest.mark.asyncio
async def test_replayed_deposit_tx_id_rejected(client: AsyncClient):
    """Same on-chain payment tx_id reused for a second, different
    purchase attempt must be rejected as a replay."""
    agent = await _make_agent(client)
    listing = await _make_listing(client)

    with patch(
        "app.services.purchase_service.verify_payment",
        new=AsyncMock(return_value=_fake_verified_payment("REPLAYED-TX")),
    ), patch(
        "app.services.purchase_service.escrow_wallet.compute_platform_fee_microalgos", return_value=0
    ), patch(
        "app.services.purchase_service.escrow_wallet.release_to_provider",
        return_value=PayoutResult(tx_id="PAYOUT4", from_address="E", to_address="P", amount_microalgos=1000, asa_id=None),
    ), patch(
        "app.services.purchase_service.httpx.AsyncClient", lambda *a, **kw: _FakeAsyncClient(*a, **kw)
    ):
        headers = {"X-Agent-Key": agent["api_key"]}
        r1 = await client.get(f"/market/{listing['path']}/call", headers=headers)
        quote = r1.json()
        headers2 = dict(headers)
        headers2["X-402-Payment-Proof"] = f'{{"tx_id": "REPLAYED-TX", "quote": "{quote["quote"]}"}}'
        r2 = await client.get(f"/market/{listing['path']}/call", headers=headers2)
        assert r2.status_code == 200

        # New purchase attempt (different idempotency key), same deposit tx_id.
        r3 = await client.get(f"/market/{listing['path']}/call", headers=headers)
        quote3 = r3.json()
        headers3 = dict(headers)
        headers3["X-Idempotency-Key"] = str(uuid.uuid4())
        headers3["X-402-Payment-Proof"] = f'{{"tx_id": "REPLAYED-TX", "quote": "{quote3["quote"]}"}}'
        r4 = await client.get(f"/market/{listing['path']}/call", headers=headers3)
        assert r4.status_code == 409


@pytest.mark.asyncio
async def test_latency_recorded_from_real_upstream_timing(client: AsyncClient):
    import asyncio

    agent = await _make_agent(client)
    listing = await _make_listing(client)

    class SlowClient(_FakeAsyncClient):
        async def request(self, *a, **kw):
            await asyncio.sleep(0.05)
            return await super().request(*a, **kw)

    with patch(
        "app.services.purchase_service.verify_payment",
        new=AsyncMock(return_value=_fake_verified_payment("TXID5")),
    ), patch(
        "app.services.purchase_service.escrow_wallet.compute_platform_fee_microalgos", return_value=0
    ), patch(
        "app.services.purchase_service.escrow_wallet.release_to_provider",
        return_value=PayoutResult(tx_id="PAYOUT5", from_address="E", to_address="P", amount_microalgos=1000, asa_id=None),
    ), patch(
        "app.services.purchase_service.httpx.AsyncClient", lambda *a, **kw: SlowClient(*a, **kw)
    ):
        headers = {"X-Agent-Key": agent["api_key"]}
        r1 = await client.get(f"/market/{listing['path']}/call", headers=headers)
        quote = r1.json()
        headers2 = dict(headers)
        headers2["X-402-Payment-Proof"] = f'{{"tx_id": "TXID5", "quote": "{quote["quote"]}"}}'
        await client.get(f"/market/{listing['path']}/call", headers=headers2)

    updated = (await client.get(f"/api/listings/{listing['id']}")).json()
    # Was measured, not the old static default of 200ms.
    assert updated["average_latency_ms"] >= 40
