import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.agent import Agent
from app.models.listing import Listing
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User, UserRole
from app.schemas.transaction import TransactionOut

router = APIRouter(prefix="/api/transactions", tags=["dashboard"])


def _scope_for(query, user: User):
    """Restrict a transactions query to what `user` is allowed to see.

    admin     -> everything
    user      -> transactions of agents they own
    publisher -> transactions against listings they own
    """
    if user.role == UserRole.ADMIN:
        return query
    if user.role == UserRole.USER:
        return query.join(Agent, Transaction.agent_id == Agent.id).where(Agent.owner_id == user.id)
    if user.role == UserRole.PUBLISHER:
        return query.join(Listing, Transaction.listing_id == Listing.id).where(
            Listing.owner_id == user.id
        )
    # Unknown role: see nothing.
    return query.where(False)  # noqa: FBT003


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    agent_id: uuid.UUID | None = None,
    listing_id: uuid.UUID | None = None,
    status_filter: TransactionStatus | None = None,
    limit: int = Query(default=50, le=500),
) -> list[Transaction]:
    query = select(Transaction).order_by(Transaction.created_at.desc()).limit(limit)
    query = _scope_for(query, user)
    if agent_id:
        query = query.where(Transaction.agent_id == agent_id)
    if listing_id:
        query = query.where(Transaction.listing_id == listing_id)
    if status_filter:
        query = query.where(Transaction.status == status_filter)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{transaction_id}", response_model=TransactionOut)
async def get_transaction(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Transaction:
    query = _scope_for(select(Transaction).where(Transaction.id == transaction_id), user)
    txn = (await db.execute(query)).scalar_one_or_none()
    if txn is None:
        # 404 (not 403) so we don't leak the existence of others' transactions.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return txn
