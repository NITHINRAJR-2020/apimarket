import asyncio
import base64
import logging
from dataclasses import dataclass

from algosdk.v2client import algod, indexer

from app.core.config import get_settings

logger = logging.getLogger("apimarket.algorand_verifier")
settings = get_settings()


class PaymentVerificationError(Exception):
    """Raised when a submitted payment proof cannot be verified against the
    quoted price/recipient/asset on-chain."""


@dataclass
class VerifiedPayment:
    tx_id: str
    payer_address: str
    receiver_address: str
    amount: int
    asa_id: int | None
    confirmed_round: int
    note: str | None = None


def _get_algod_client() -> algod.AlgodClient:
    return algod.AlgodClient(settings.ALGOD_TOKEN, settings.ALGOD_ADDRESS)


def _get_indexer_client() -> indexer.IndexerClient:
    return indexer.IndexerClient(settings.INDEXER_TOKEN, settings.INDEXER_ADDRESS)


def _extract_payment_fields(txn_dict: dict) -> tuple[str, str, int, int | None, str | None]:
    """Normalize an algod/indexer transaction record into
    (sender, receiver, amount, asa_id, note) for both Algo payments
    (pay) and Algorand Standard Asset transfers (axfer).
    """
    sender = txn_dict.get("sender") or txn_dict.get("from")
    note_b64 = txn_dict.get("note")
    note = None
    if note_b64:
        try:
            note = base64.b64decode(note_b64).decode("utf-8", errors="ignore")
        except Exception:
            note = None

    if "payment-transaction" in txn_dict or "pay" in txn_dict.get("tx-type", ""):
        pay = txn_dict.get("payment-transaction", {})
        receiver = pay.get("receiver")
        amount = int(pay.get("amount", 0))
        return sender, receiver, amount, None, note

    if "asset-transfer-transaction" in txn_dict or "axfer" in txn_dict.get("tx-type", ""):
        axfer = txn_dict.get("asset-transfer-transaction", {})
        receiver = axfer.get("receiver")
        amount = int(axfer.get("amount", 0))
        asa_id = int(axfer.get("asset-id", 0)) or None
        return sender, receiver, amount, asa_id, note

    raise PaymentVerificationError(
        "Transaction is neither a native ALGO payment nor an ASA transfer"
    )


async def fetch_confirmed_transaction(tx_id: str) -> dict:
    """Fetch a transaction by ID, preferring algod's pending-transaction
    lookup (fast, works immediately after confirmation) and falling back
    to the indexer (works for older/settled transactions).
    """
    algod_client = _get_algod_client()

    def _algod_lookup() -> dict | None:
        try:
            info = algod_client.pending_transaction_info(tx_id)
            if info.get("confirmed-round", 0) > 0:
                txn = info.get("txn", {}).get("txn", {})
                normalized = {
                    "tx-type": txn.get("type", ""),
                    "sender": info.get("txn", {}).get("txn", {}).get("snd"),
                    "confirmed-round": info["confirmed-round"],
                    "note": txn.get("note"),
                }
                if txn.get("type") == "pay":
                    normalized["payment-transaction"] = {
                        "receiver": txn.get("rcv"),
                        "amount": txn.get("amt", 0),
                    }
                elif txn.get("type") == "axfer":
                    normalized["asset-transfer-transaction"] = {
                        "receiver": txn.get("arcv"),
                        "amount": txn.get("aamt", 0),
                        "asset-id": txn.get("xaid"),
                    }
                # algod encodes addresses/notes in msgpack-derived raw form
                # in some SDK versions; if sender/receiver look non-standard
                # we bail out and let the indexer fallback handle decoding.
                if normalized["sender"] and isinstance(normalized["sender"], str):
                    return normalized
            return None
        except Exception as exc:
            logger.debug("algod pending_transaction_info lookup failed for %s: %s", tx_id, exc)
            return None

    result = await asyncio.to_thread(_algod_lookup)
    if result is not None:
        return result

    def _indexer_lookup() -> dict:
        idx_client = _get_indexer_client()
        response = idx_client.search_transactions(txid=tx_id)
        txns = response.get("transactions", [])
        if not txns:
            raise PaymentVerificationError(f"Transaction {tx_id} not found on indexer")
        return txns[0]

    try:
        return await asyncio.to_thread(_indexer_lookup)
    except PaymentVerificationError:
        raise
    except Exception as exc:
        raise PaymentVerificationError(
            f"Failed to look up transaction {tx_id} via algod or indexer: {exc}"
        ) from exc


async def verify_payment_on_chain(
    *,
    tx_id: str,
    expected_recipient: str,
    expected_amount: int,
    expected_asa_id: int | None,
) -> VerifiedPayment:
    """Fetch the given transaction and assert it pays at least the expected
    amount to the expected recipient, in the expected asset. Raises
    PaymentVerificationError on any mismatch or if unconfirmed.
    """
    txn_dict = await fetch_confirmed_transaction(tx_id)

    confirmed_round = int(txn_dict.get("confirmed-round", 0))
    if confirmed_round <= 0:
        raise PaymentVerificationError(f"Transaction {tx_id} is not yet confirmed")

    sender, receiver, amount, asa_id, note = _extract_payment_fields(txn_dict)

    if receiver != expected_recipient:
        raise PaymentVerificationError(
            f"Payment recipient mismatch: expected {expected_recipient}, got {receiver}"
        )
    if amount < expected_amount:
        raise PaymentVerificationError(
            f"Payment amount insufficient: expected >= {expected_amount}, got {amount}"
        )
    if (asa_id or 0) != (expected_asa_id or 0):
        raise PaymentVerificationError(
            f"Payment asset mismatch: expected asset {expected_asa_id or 'ALGO'}, "
            f"got {asa_id or 'ALGO'}"
        )

    return VerifiedPayment(
        tx_id=tx_id,
        payer_address=sender,
        receiver_address=receiver,
        amount=amount,
        asa_id=asa_id,
        confirmed_round=confirmed_round,
        note=note,
    )


# ---------------------------------------------------------------------------
# GoPlausible x402 v2 facilitator integration (verify + settle)
# ---------------------------------------------------------------------------
# Real SDK types/client -- confirmed against the installed x402-avm==2.0.2
# package (x402.http.HTTPFacilitatorClient / x402.schemas), not guessed.

from x402.http import FacilitatorConfig, HTTPFacilitatorClient  # noqa: E402
from x402.schemas import PaymentPayload, PaymentRequirements  # noqa: E402

_facilitator_client: HTTPFacilitatorClient | None = None


def get_facilitator_client() -> HTTPFacilitatorClient:
    global _facilitator_client
    if _facilitator_client is None:
        _facilitator_client = HTTPFacilitatorClient(FacilitatorConfig(url=settings.FACILITATOR_URL))
    return _facilitator_client


def build_payment_requirements(
    *, expected_recipient: str, expected_amount: int, expected_asa_id: int | None
) -> PaymentRequirements:
    """Builds the x402 v2 PaymentRequirements GoPlausible will verify the
    client's PaymentPayload against. asset is the ASA id as a string;
    for native ALGO (no asa_id) we still need an asset identifier -- the
    marketplace prices exclusively in the configured USDC ASA today, so
    expected_asa_id should always be set in practice.
    """
    return PaymentRequirements(
        scheme=settings.X402_SCHEME,
        network=settings.X402_NETWORK_CAIP2,
        asset=str(expected_asa_id or settings.USDC_TESTNET_ASA_ID),
        amount=str(expected_amount),
        pay_to=expected_recipient,
        max_timeout_seconds=settings.X402_MAX_TIMEOUT_SECONDS,
    )


async def verify_and_settle_via_facilitator(
    *,
    payment_payload_dict: dict,
    expected_recipient: str,
    expected_amount: int,
    expected_asa_id: int | None,
) -> VerifiedPayment:
    """Primary x402 v2 entrypoint. Sends the agent's signed PaymentPayload
    to GoPlausible's hosted facilitator for /verify then /settle, and
    returns the resulting on-chain settlement as a VerifiedPayment.

    Raises PaymentVerificationError on any facilitator-reported failure,
    or if the facilitator itself is unreachable/errors -- this deliberately
    does NOT fall back to direct algod verification, because a payment
    that GoPlausible hasn't settled was never actually paid into escrow.
    """
    requirements = build_payment_requirements(
        expected_recipient=expected_recipient,
        expected_amount=expected_amount,
        expected_asa_id=expected_asa_id,
    )

    try:
        payload = PaymentPayload.model_validate(
            {**payment_payload_dict, "accepted": requirements.model_dump(by_alias=True)}
        )
    except Exception as exc:
        raise PaymentVerificationError(f"Malformed PaymentPayload: {exc}") from exc

    facilitator = get_facilitator_client()

    logger.info("facilitator verification started network=%s asset=%s", requirements.network, requirements.asset)
    try:
        verify_result = await facilitator.verify(payload, requirements)
    except Exception as exc:
        raise PaymentVerificationError(f"GoPlausible facilitator unreachable or errored on /verify: {exc}") from exc

    if not verify_result.is_valid:
        raise PaymentVerificationError(
            f"Facilitator rejected payment: {verify_result.invalid_reason or verify_result.invalid_message}"
        )
    logger.info("facilitator verification succeeded payer=%s", verify_result.payer)

    logger.info("facilitator settlement started")
    try:
        settle_result = await facilitator.settle(payload, requirements)
    except Exception as exc:
        raise PaymentVerificationError(f"GoPlausible facilitator unreachable or errored on /settle: {exc}") from exc

    if not settle_result.success:
        raise PaymentVerificationError(
            f"Facilitator settlement failed: {settle_result.error_reason or settle_result.error_message}"
        )
    logger.info("facilitator settlement succeeded tx=%s", settle_result.transaction)

    return VerifiedPayment(
        tx_id=settle_result.transaction,
        payer_address=settle_result.payer or verify_result.payer or "",
        receiver_address=expected_recipient,
        amount=expected_amount,
        asa_id=expected_asa_id,
        confirmed_round=0,  # GoPlausible's SettleResponse doesn't return a round; the
                            # settlement tx id itself is what you look up on Lora.
    )


async def verify_payment(
    *,
    payment_payload_dict: dict | None = None,
    tx_id: str | None = None,
    expected_recipient: str,
    expected_amount: int,
    expected_asa_id: int | None,
) -> VerifiedPayment:
    """Primary entrypoint used by purchase_service.

    If a PaymentPayload dict is supplied, verification/settlement goes
    through the GoPlausible facilitator (the required path). The legacy
    tx_id path is kept only for the existing direct algod/indexer
    fallback -- useful for tests/local dev without a live facilitator --
    but is no longer what production purchases use.
    """
    if payment_payload_dict is not None:
        return await verify_and_settle_via_facilitator(
            payment_payload_dict=payment_payload_dict,
            expected_recipient=expected_recipient,
            expected_amount=expected_amount,
            expected_asa_id=expected_asa_id,
        )

    if tx_id is not None:
        return await verify_payment_on_chain(
            tx_id=tx_id,
            expected_recipient=expected_recipient,
            expected_amount=expected_amount,
            expected_asa_id=expected_asa_id,
        )

    raise PaymentVerificationError("verify_payment requires either payment_payload_dict or tx_id")
