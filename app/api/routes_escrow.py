import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.escrow import Escrow, EscrowStatus
from app.models.listing import Listing
from app.models.transaction import Transaction, TransactionStatus
from app.payments import escrow_wallet
from app.schemas.transaction import (
    EscrowOut,
    EscrowResolveRequest,
    EvidenceSubmitRequest,
    PartialReleaseRequest,
)

router = APIRouter(prefix="/api/escrow", tags=["escrow"], dependencies=[Depends(require_admin)])


@router.get("/health")
async def escrow_health(db: AsyncSession = Depends(get_db)) -> dict:
    """Outstanding platform liability: how much is currently HELD (owed to
    either a provider or an agent, depending on outcome) and how much is
    DISPUTED (stuck, needs a human). Useful as a solvency check against
    the actual on-chain escrow wallet balance, and as an early-warning
    signal if disputes are piling up faster than they're resolved."""

    async def _sum_for(status: EscrowStatus) -> int:
        result = await db.execute(
            select(func.coalesce(func.sum(Escrow.amount_microalgos), 0)).where(Escrow.status == status)
        )
        return int(result.scalar_one())

    held_total = await _sum_for(EscrowStatus.HELD)
    disputed_total = await _sum_for(EscrowStatus.DISPUTED)

    held_count_result = await db.execute(select(func.count()).where(Escrow.status == EscrowStatus.HELD))
    disputed_count_result = await db.execute(select(func.count()).where(Escrow.status == EscrowStatus.DISPUTED))

    oldest_held_result = await db.execute(
        select(func.min(Escrow.created_at)).where(Escrow.status == EscrowStatus.HELD)
    )
    oldest_held = oldest_held_result.scalar_one()

    return {
        "outstanding_held_microalgos": held_total,
        "outstanding_held_count": held_count_result.scalar_one(),
        "disputed_microalgos": disputed_total,
        "disputed_count": disputed_count_result.scalar_one(),
        "oldest_held_created_at": oldest_held.isoformat() if oldest_held else None,
        "total_platform_liability_microalgos": held_total + disputed_total,
        "escrow_wallet_address": escrow_wallet.escrow_wallet_address()
        if _has_wallet_configured()
        else None,
    }


def _has_wallet_configured() -> bool:
    from app.core.config import get_settings

    return bool(get_settings().ESCROW_WALLET_MNEMONIC)


@router.get("/analytics/by-listing")
async def escrow_analytics_by_listing(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Per-listing escrow risk signals -- what an agent (or you) would
    want to check before buying from a provider: how often its escrows
    get disputed or refunded rather than cleanly released, and how long
    funds typically sit in HELD before resolving. High dispute_rate or
    refund_rate signals a flaky/dishonest provider; a high
    avg_resolution_seconds signals a provider whose upstream is slow or
    whose failures take a while to surface."""
    query = (
        select(
            Listing.id,
            Listing.name,
            Listing.path,
            Escrow.status,
            Escrow.created_at,
            Escrow.resolved_at,
        )
        .join(Transaction, Transaction.listing_id == Listing.id)
        .join(Escrow, Escrow.transaction_id == Transaction.id)
    )
    result = await db.execute(query)
    rows = result.all()

    by_listing: dict[uuid.UUID, dict] = {}
    for listing_id, name, path, status, created_at, resolved_at in rows:
        bucket = by_listing.setdefault(
            listing_id,
            {
                "listing_id": listing_id,
                "listing_name": name,
                "listing_path": path,
                "total_escrows": 0,
                "released": 0,
                "partially_released": 0,
                "refunded": 0,
                "disputed": 0,
                "held": 0,
                "_resolution_seconds_sum": 0.0,
                "_resolution_count": 0,
            },
        )
        bucket["total_escrows"] += 1
        bucket[status.value.lower()] = bucket.get(status.value.lower(), 0) + 1
        if resolved_at is not None:
            bucket["_resolution_seconds_sum"] += (resolved_at - created_at).total_seconds()
            bucket["_resolution_count"] += 1

    analytics = []
    for bucket in by_listing.values():
        total = bucket["total_escrows"]
        resolution_count = bucket.pop("_resolution_count")
        resolution_sum = bucket.pop("_resolution_seconds_sum")
        bucket["dispute_rate"] = round(bucket["disputed"] / total, 4) if total else 0.0
        bucket["refund_rate"] = round(bucket["refunded"] / total, 4) if total else 0.0
        bucket["avg_resolution_seconds"] = (
            round(resolution_sum / resolution_count, 1) if resolution_count else None
        )
        analytics.append(bucket)

    analytics.sort(key=lambda b: b["dispute_rate"], reverse=True)
    return analytics


@router.get("", response_model=list[EscrowOut])
async def list_escrows(status_filter: EscrowStatus | None = None, db: AsyncSession = Depends(get_db)) -> list[Escrow]:
    query = select(Escrow).order_by(Escrow.created_at.desc())
    if status_filter:
        query = query.where(Escrow.status == status_filter)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{escrow_id}", response_model=EscrowOut)
async def get_escrow(escrow_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Escrow:
    escrow = await db.get(Escrow, escrow_id)
    if escrow is None:
        raise HTTPException(status_code=404, detail="Escrow not found")
    return escrow


@router.post("/{escrow_id}/release", response_model=EscrowOut)
async def manual_release(
    escrow_id: uuid.UUID, payload: EscrowResolveRequest, db: AsyncSession = Depends(get_db)
) -> Escrow:
    """Manual admin override -- e.g. resolving a DISPUTED escrow where
    auto-release failed, once the underlying issue is fixed."""
    escrow = await db.get(Escrow, escrow_id)
    if escrow is None:
        raise HTTPException(status_code=404, detail="Escrow not found")
    if escrow.status not in (EscrowStatus.HELD, EscrowStatus.DISPUTED):
        raise HTTPException(status_code=409, detail=f"Escrow {escrow_id} is {escrow.status}, cannot release")

    txn = await db.get(Transaction, escrow.transaction_id)
    listing = await db.get(Listing, txn.listing_id) if txn else None
    if listing is None:
        raise HTTPException(status_code=409, detail="Underlying listing no longer exists")

    try:
        payout = escrow_wallet.release_to_provider(
            pay_to_address=listing.pay_to_address,
            amount_microalgos=escrow.amount_microalgos,
            asa_id=escrow.asa_id,
            platform_fee_microalgos=escrow.platform_fee_microalgos,
        )
    except escrow_wallet.EscrowWalletError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    escrow.status = EscrowStatus.RELEASED
    escrow.payout_tx_id = payout.tx_id
    escrow.notes = payload.notes
    escrow.resolved_at = datetime.now(UTC)
    if txn:
        txn.status = TransactionStatus.SERVICE_COMPLETED
        txn.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(escrow)
    return escrow


@router.post("/{escrow_id}/refund", response_model=EscrowOut)
async def manual_refund(
    escrow_id: uuid.UUID, payload: EscrowResolveRequest, db: AsyncSession = Depends(get_db)
) -> Escrow:
    escrow = await db.get(Escrow, escrow_id)
    if escrow is None:
        raise HTTPException(status_code=404, detail="Escrow not found")
    if escrow.status not in (EscrowStatus.HELD, EscrowStatus.DISPUTED):
        raise HTTPException(status_code=409, detail=f"Escrow {escrow_id} is {escrow.status}, cannot refund")

    txn = await db.get(Transaction, escrow.transaction_id)
    if txn is None or not txn.payer_address:
        raise HTTPException(status_code=409, detail="No payer address recorded for this transaction")

    try:
        refund = escrow_wallet.refund_to_agent(
            payer_address=txn.payer_address,
            amount_microalgos=escrow.amount_microalgos,
            asa_id=escrow.asa_id,
        )
    except escrow_wallet.EscrowWalletError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    escrow.status = EscrowStatus.REFUNDED
    escrow.refund_tx_id = refund.tx_id
    escrow.notes = payload.notes
    escrow.resolved_at = datetime.now(UTC)
    txn.status = TransactionStatus.REFUNDED
    txn.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(escrow)
    return escrow


@router.post("/{escrow_id}/dispute", response_model=EscrowOut)
async def open_dispute(
    escrow_id: uuid.UUID, payload: EvidenceSubmitRequest, db: AsyncSession = Depends(get_db)
) -> Escrow:
    """Either party (agent or provider) can flag a HELD escrow as disputed
    -- e.g. the agent thinks the response was garbage despite a 2xx, or
    the provider thinks a refund was issued unfairly. This freezes the
    escrow (moves it OUT of any auto-release/auto-refund path) and starts
    the evidence trail. From here an admin resolves via /release,
    /refund, or /partial-release once they've reviewed the evidence."""
    escrow = await db.get(Escrow, escrow_id)
    if escrow is None:
        raise HTTPException(status_code=404, detail="Escrow not found")
    if escrow.status not in (EscrowStatus.HELD, EscrowStatus.DISPUTED):
        raise HTTPException(
            status_code=409,
            detail=f"Escrow {escrow_id} is already {escrow.status}, cannot open a new dispute",
        )

    escrow.status = EscrowStatus.DISPUTED
    _append_evidence(escrow, payload)

    txn = await db.get(Transaction, escrow.transaction_id)
    if txn:
        txn.status = TransactionStatus.DISPUTED

    await db.commit()
    await db.refresh(escrow)
    return escrow


@router.post("/{escrow_id}/evidence", response_model=EscrowOut)
async def submit_evidence(
    escrow_id: uuid.UUID, payload: EvidenceSubmitRequest, db: AsyncSession = Depends(get_db)
) -> Escrow:
    """Attach additional evidence to an already-open dispute (logs,
    screenshots, a link to the upstream response that was returned,
    counter-argument from the other party, etc.) without changing its
    resolution yet. Requires the escrow to already be DISPUTED --
    use /dispute first to open one."""
    escrow = await db.get(Escrow, escrow_id)
    if escrow is None:
        raise HTTPException(status_code=404, detail="Escrow not found")
    if escrow.status != EscrowStatus.DISPUTED:
        raise HTTPException(
            status_code=409,
            detail=f"Escrow {escrow_id} is {escrow.status}, not under an open dispute. Call /dispute first.",
        )

    _append_evidence(escrow, payload)
    await db.commit()
    await db.refresh(escrow)
    return escrow


def _append_evidence(escrow: Escrow, payload: EvidenceSubmitRequest) -> None:
    """Appends one evidence entry to escrow.evidence as a JSON array
    stored in a Text column (no new table needed for what's likely a
    handful of entries per dispute)."""
    try:
        entries = json.loads(escrow.evidence) if escrow.evidence else []
    except (json.JSONDecodeError, TypeError):
        entries = []
    entries.append(
        {
            "submitted_by": payload.submitted_by,
            "message": payload.message,
            "reference_url": payload.reference_url,
            "submitted_at": datetime.now(UTC).isoformat(),
        }
    )
    escrow.evidence = json.dumps(entries)


@router.post("/{escrow_id}/partial-release", response_model=EscrowOut)
async def manual_partial_release(
    escrow_id: uuid.UUID, payload: PartialReleaseRequest, db: AsyncSession = Depends(get_db)
) -> Escrow:
    """Admin resolution for a dispute (or a HELD escrow) that splits the
    funds between the provider and the agent rather than an all-or-
    nothing release/refund -- e.g. the evidence shows the provider did
    partial but not full work."""
    escrow = await db.get(Escrow, escrow_id)
    if escrow is None:
        raise HTTPException(status_code=404, detail="Escrow not found")
    if escrow.status not in (EscrowStatus.HELD, EscrowStatus.DISPUTED):
        raise HTTPException(
            status_code=409, detail=f"Escrow {escrow_id} is {escrow.status}, cannot partially release"
        )

    txn = await db.get(Transaction, escrow.transaction_id)
    if txn is None or not txn.payer_address:
        raise HTTPException(status_code=409, detail="No payer address recorded for this transaction")
    listing = await db.get(Listing, txn.listing_id) if txn.listing_id else None
    if listing is None:
        raise HTTPException(status_code=409, detail="Underlying listing no longer exists")

    try:
        split = escrow_wallet.split_release(
            pay_to_address=listing.pay_to_address,
            payer_address=txn.payer_address,
            total_amount_microalgos=escrow.amount_microalgos,
            provider_share_bps=payload.provider_share_bps,
            asa_id=escrow.asa_id,
            platform_fee_microalgos=escrow.platform_fee_microalgos,
        )
    except escrow_wallet.EscrowWalletError as exc:
        # split_release's message already distinguishes "nothing went out"
        # from "provider got paid but agent refund failed" -- surface it
        # as-is so the admin knows exactly what state the funds are in.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    escrow.status = EscrowStatus.PARTIALLY_RELEASED
    escrow.payout_tx_id = split.provider_payout.tx_id if split.provider_payout else None
    escrow.refund_tx_id = split.agent_refund.tx_id if split.agent_refund else None
    escrow.provider_share_bps = payload.provider_share_bps
    escrow.provider_amount_microalgos = split.provider_amount_microalgos
    escrow.agent_amount_microalgos = split.agent_amount_microalgos
    escrow.notes = payload.notes
    escrow.resolved_at = datetime.now(UTC)
    txn.status = TransactionStatus.PARTIALLY_COMPLETED
    txn.completed_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(escrow)
    return escrow
