"""End-to-end demo client for APIMarket.

Walks through the full flow against a running local server:

  1. Publish a marketplace listing (a free public API, priced in testnet USDC).
  2. Register an agent with a spending policy.
  3. Call the listing with no payment -> expect 402 with a signed quote
     whose payTo is the PLATFORM escrow wallet (not the listing's
     pay_to_address).
  4. Sign and submit that exact payment on Algorand Testnet from the
     agent's own funded account.
  5. Retry the call with the payment proof -> the platform verifies the
     deposit, proxies the request to the upstream API, and (assuming the
     upstream call succeeds) releases escrow to the provider automatically.
  6. Print the resulting transaction + escrow rows so you can see the
     full HELD -> RELEASED lifecycle.

Usage:
    export PAYER_MNEMONIC="your 25 word funded testnet mnemonic here"
    python scripts/test_client.py --base-url http://localhost:8000
"""

import argparse
import json
import sys
import time

import httpx
from algosdk import account, mnemonic
from algosdk.transaction import AssetTransferTxn, PaymentTxn, wait_for_confirmation
from algosdk.v2client import algod

ALGOD_ADDRESS = "https://testnet-api.algonode.cloud"
DEMO_ASA_ID = 10458941  # USDC testnet, must match the server's USDC_TESTNET_ASA_ID


def pay_quote(quote_body: dict, payer_mnemonic: str) -> str:
    private_key = mnemonic.to_private_key(payer_mnemonic)
    payer_address = account.address_from_private_key(private_key)

    client = algod.AlgodClient("", ALGOD_ADDRESS)
    params = client.suggested_params()

    pay_to = quote_body["payTo"]
    amount = int(quote_body["maxAmountRequired"])
    asset_label = quote_body["asset"]

    if asset_label.startswith("asa:"):
        asa_id = int(asset_label.split(":", 1)[1])
        txn = AssetTransferTxn(sender=payer_address, sp=params, receiver=pay_to, amt=amount, index=asa_id)
    else:
        txn = PaymentTxn(sender=payer_address, sp=params, receiver=pay_to, amt=amount)

    signed = txn.sign(private_key)
    tx_id = client.send_transaction(signed)
    wait_for_confirmation(client, tx_id, 10)
    print(f"  paid quote: tx_id={tx_id} payer={payer_address} -> escrow={pay_to} amount={amount}")
    return tx_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--payer-mnemonic", default=None, help="Overrides $PAYER_MNEMONIC")
    args = parser.parse_args()

    import os

    payer_mnemonic = args.payer_mnemonic or os.environ.get("PAYER_MNEMONIC")
    if not payer_mnemonic:
        print("Set PAYER_MNEMONIC (a funded Algorand Testnet account) or pass --payer-mnemonic")
        sys.exit(1)

    private_key = mnemonic.to_private_key(payer_mnemonic)
    payer_address = account.address_from_private_key(private_key)

    client = httpx.Client(base_url=args.base_url, timeout=70.0)

    print("1. Publishing a demo marketplace listing (Open-Meteo weather API)...")
    listing_resp = client.post(
        "/api/listings",
        json={
            "name": "Sample Weather API",
            "description": "Current weather for Berlin, via Open-Meteo",
            "category": "weather",
            "path": "sample-weather",
            "upstream_url": (
                "https://api.open-meteo.com/v1/forecast"
                "?latitude=52.52&longitude=13.41&current_weather=true"
            ),
            "price_microalgos": 100000,  # $0.10 in testnet USDC
            "pay_to_address": payer_address,  # demo only: provider payout == this same test address
            "asa_id": DEMO_ASA_ID,
        },
    )
    if listing_resp.status_code == 409:
        print("   listing already exists, continuing")
    else:
        listing_resp.raise_for_status()
        print(f"   listing created: {listing_resp.json()['id']}")

    print("2. Registering an agent with a spending policy...")
    agent_resp = client.post(
        "/api/agents",
        json={
            "name": "Demo Research Agent",
            "wallet_address": payer_address,
            "policy": {
                "max_transaction_amount": "5.00",
                "daily_limit": "50.00",
                "min_provider_reputation": 0,
            },
        },
    )
    agent_resp.raise_for_status()
    agent = agent_resp.json()
    api_key = agent["api_key"]
    print(f"   agent created: {agent['id']} api_key={api_key[:8]}...")

    print("3. Calling the listing with no payment (expect 402 + escrow quote)...")
    first = client.get("/market/sample-weather/call", headers={"X-Agent-Key": api_key})
    if first.status_code != 402:
        print(f"   unexpected status {first.status_code}: {first.text}")
        sys.exit(1)
    quote_body = first.json()
    print(f"   402 received. payTo (escrow wallet) = {quote_body['payTo']}")
    print(f"   note: {quote_body.get('note')}")

    print("4. Paying the quote on Algorand Testnet (into the ESCROW wallet)...")
    tx_id = pay_quote(quote_body, payer_mnemonic)

    print("5. Retrying the call with payment proof...")
    proof = json.dumps({"tx_id": tx_id, "quote": quote_body["quote"]})
    time.sleep(1)
    second = client.get(
        "/market/sample-weather/call",
        headers={"X-Agent-Key": api_key, "X-402-Payment-Proof": proof},
    )
    print(f"   status: {second.status_code}")
    print(f"   body: {second.text[:500]}")
    txn_id = second.headers.get("X-Transaction-Id")

    if txn_id:
        print("6. Checking the transaction + escrow outcome...")
        txn = client.get(f"/api/transactions/{txn_id}").json()
        print(f"   transaction status: {txn['status']}")
        escrows = client.get("/api/escrow").json()
        for e in escrows:
            if e["transaction_id"] == txn_id:
                print(f"   escrow status: {e['status']} payout_tx={e.get('payout_tx_id')}")


if __name__ == "__main__":
    main()
