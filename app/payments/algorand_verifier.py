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


async def verify_payment_with_x402_avm(
    *,
    tx_id: str,
    expected_recipient: str,
    expected_amount: int,
    expected_asa_id: int | None,
) -> VerifiedPayment | None:
    """Best-effort fast path using the x402-avm SDK's facilitator/verify
    helpers, if the package is installed. Falls back silently (returns
    None) if the package is absent or its verification call fails, so the
    caller can retry against algod/indexer directly.

    NOTE: the x402-avm package is an emerging, actively-evolving SDK for
    the x402 Global Challenge. Its exact API surface may change between
    versions, so this integration is written defensively: any import or
    call failure is caught and logged, and control returns to the caller
    to fall back on the direct algod/indexer verification path above,
    which is protocol-stable and does not depend on this package.
    """
    try:
        from x402_avm import facilitator as x402_facilitator  # type: ignore
    except ImportError:
        logger.info("x402-avm not installed; using direct algod/indexer verification only")
        return None

    def _verify() -> VerifiedPayment | None:
        try:
            result = x402_facilitator.verify(
                tx_id=tx_id,
                network=settings.ALGORAND_NETWORK,
                pay_to=expected_recipient,
                amount=expected_amount,
                asset_id=expected_asa_id,
            )
            if not result or not getattr(result, "is_valid", False):
                return None
            return VerifiedPayment(
                tx_id=tx_id,
                payer_address=result.payer,
                receiver_address=expected_recipient,
                amount=expected_amount,
                asa_id=expected_asa_id,
                confirmed_round=getattr(result, "confirmed_round", 0),
            )
        except Exception as exc:
            logger.warning("x402-avm verification failed, falling back to algod: %s", exc)
            return None

    return await asyncio.to_thread(_verify)


async def verify_payment(
    *,
    tx_id: str,
    expected_recipient: str,
    expected_amount: int,
    expected_asa_id: int | None,
) -> VerifiedPayment:
    """Primary entrypoint used by the middleware: try the x402-avm SDK
    first for speed/protocol conformance, and always fall back to a
    direct algod/indexer check so verification never hard-depends on a
    third-party package being installed or working.
    """
    fast_result = await verify_payment_with_x402_avm(
        tx_id=tx_id,
        expected_recipient=expected_recipient,
        expected_amount=expected_amount,
        expected_asa_id=expected_asa_id,
    )
    if fast_result is not None:
        return fast_result

    return await verify_payment_on_chain(
        tx_id=tx_id,
        expected_recipient=expected_recipient,
        expected_amount=expected_amount,
        expected_asa_id=expected_asa_id,
    )
