import json
import logging
import uuid

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.core.database import AsyncSessionLocal
from app.models.transaction import TransactionStatus
from app.services.purchase_service import (
    HOP_BY_HOP_HEADERS,
    PurchaseError,
    fulfil_and_settle,
    start_or_settle_purchase,
)

logger = logging.getLogger("apimarket.routes_purchase")
router = APIRouter(prefix="/market", tags=["purchase"])

PAYMENT_PROOF_HEADER = "X-402-Payment-Proof"
AGENT_KEY_HEADER = "X-Agent-Key"
IDEMPOTENCY_HEADER = "X-Idempotency-Key"


@router.api_route("/{listing_path:path}/call", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def call_listing(listing_path: str, request: Request) -> Response:
    """The single entrypoint an AI agent hits to actually consume a paid
    API from the marketplace. Two round trips, x402-style:

      1. No X-402-Payment-Proof header -> 402 with a signed quote whose
         payTo is the platform's escrow wallet.
      2. Agent pays that quote on Algorand, then retries with
         X-402-Payment-Proof:{"payment_payload": {...}, "quote": ...} -> funds
         are verified into escrow, the upstream API is called on the
         agent's behalf, and escrow is released/refunded automatically
         based on whether that call actually succeeded.
    """
    agent_key = request.headers.get(AGENT_KEY_HEADER)
    if not agent_key:
        return JSONResponse(status_code=401, content={"detail": f"Missing {AGENT_KEY_HEADER} header"})

    idempotency_key = request.headers.get(IDEMPOTENCY_HEADER) or str(uuid.uuid4())

    payment_proof = None
    proof_raw = request.headers.get(PAYMENT_PROOF_HEADER)
    if proof_raw:
        try:
            payment_proof = json.loads(proof_raw)
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=400,
                content={"detail": f"{PAYMENT_PROOF_HEADER} must be valid JSON with 'tx_id' and 'quote'"},
            )

    async with AsyncSessionLocal() as db:
        try:
            agent, listing, txn, quote_body, quote_headers = await start_or_settle_purchase(
                db,
                api_key=agent_key,
                listing_path=listing_path,
                idempotency_key=idempotency_key,
                payment_proof=payment_proof,
            )
        except PurchaseError as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        if quote_body is not None:
            return JSONResponse(status_code=402, content=quote_body, headers=quote_headers)

        # Idempotent replay of an already-settled transaction: return its
        # last known outcome instead of re-charging or re-calling upstream.
        if txn.status in (
            TransactionStatus.SERVICE_COMPLETED,
            TransactionStatus.FAILED,
            TransactionStatus.REFUNDED,
            TransactionStatus.DISPUTED,
            TransactionStatus.POLICY_BLOCKED,
        ):
            return JSONResponse(
                status_code=200 if txn.status == TransactionStatus.SERVICE_COMPLETED else 409,
                content={
                    "detail": "Idempotent replay",
                    "transaction_id": str(txn.id),
                    "status": txn.status.value,
                },
            )

        body = await request.body()
        try:
            upstream_response = await fulfil_and_settle(
                db,
                transaction=txn,
                listing=listing,
                method=request.method,
                headers=dict(request.headers),
                query_params=dict(request.query_params),
                body=body,
            )
        except PurchaseError as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        response_headers = {
            k: v for k, v in upstream_response.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS
        }
        response_headers["X-402-Escrow-Deposit-Tx"] = txn.deposit_tx_id or ""
        response_headers["X-Transaction-Id"] = str(txn.id)

        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=upstream_response.headers.get("content-type"),
        )
