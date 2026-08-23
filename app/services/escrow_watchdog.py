"""Auto-refund escrows that got stuck in HELD.

Normal flow: HELD -> UPSTREAM_CALLED -> RELEASED/REFUNDED, all inside one
request in purchase_service.fulfil_and_settle(). If the process dies
between "payment verified into escrow" and "settled" (crash, deploy,
OOM-kill), the Escrow row is left at HELD forever with nobody watching it.
That's a silent liability: the agent paid, got nothing, and has no
automatic way to get its money back.

This module scans for HELD escrows older than settings.ESCROW_STALE_SECONDS
and refunds them automatically, exactly like a normal upstream-failure
refund. Call run_once() from a scheduler (APScheduler/cron/Celery beat);
it's safe to call frequently since it only touches rows past the deadline.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.escrow import Escrow, EscrowStatus
from app.models.transaction import Transaction, TransactionStatus
from app.payments import escrow_wallet

logger = logging.getLogger("apimarket.escrow_watchdog")
settings = get_settings()


async def _refund_stale_escrow(db: AsyncSession, escrow: Escrow, transaction: Transaction) -> None:
    if not transaction.payer_address:
        # Nothing we can safely do automatically -- flag for a human instead
        # of guessing where the money should go.
        escrow.status = EscrowStatus.DISPUTED
        escrow.notes = "Stale HELD escrow with no payer_address on record; needs manual resolution"
        transaction.status = TransactionStatus.DISPUTED
        logger.error("Stale escrow %s has no payer_address, marking DISPUTED", escrow.id)
        return

    try:
        refund = escrow_wallet.refund_to_agent(
            payer_address=transaction.payer_address,
            amount_microalgos=escrow.amount_microalgos,
            asa_id=escrow.asa_id,
        )
        escrow.status = EscrowStatus.REFUNDED
        escrow.refund_tx_id = refund.tx_id
        escrow.resolved_at = datetime.now(UTC)
        escrow.notes = "Auto-refunded by watchdog: stuck in HELD past timeout (likely an interrupted request)"
        transaction.status = TransactionStatus.REFUNDED
        transaction.failure_reason = "Escrow timed out in HELD; auto-refunded by watchdog"
        transaction.completed_at = datetime.now(UTC)
        logger.warning("Watchdog auto-refunded stale escrow %s (tx=%s)", escrow.id, refund.tx_id)
    except escrow_wallet.EscrowWalletError as exc:
        escrow.status = EscrowStatus.DISPUTED
        escrow.notes = f"Watchdog auto-refund failed, needs manual resolution: {exc}"
        transaction.status = TransactionStatus.DISPUTED
        logger.error("Watchdog auto-refund FAILED for escrow %s: %s", escrow.id, exc)


async def run_once() -> int:
    """Scans for stale HELD escrows and refunds them. Returns count handled."""
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.ESCROW_STALE_SECONDS)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Escrow).where(Escrow.status == EscrowStatus.HELD, Escrow.created_at < cutoff)
        )
        stale_escrows = list(result.scalars().all())
        if not stale_escrows:
            return 0

        for escrow in stale_escrows:
            txn = await db.get(Transaction, escrow.transaction_id)
            if txn is None:
                escrow.status = EscrowStatus.DISPUTED
                escrow.notes = "Stale HELD escrow with no matching transaction row"
                continue
            await _refund_stale_escrow(db, escrow, txn)

        await db.commit()
        logger.info("Watchdog processed %d stale escrow(s)", len(stale_escrows))
        return len(stale_escrows)
