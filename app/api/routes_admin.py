import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.agent import Agent
from app.models.escrow import Escrow, EscrowStatus
from app.models.listing import Listing
from app.models.transaction import Transaction
from app.models.user import User, UserRole
from app.schemas.auth import RoleUpdateRequest, StatusUpdateRequest, UserOut

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_admin)])
async def list_users(
    role: UserRole | None = None, db: AsyncSession = Depends(get_db)
) -> list[User]:
    query = select(User).order_by(User.created_at.desc())
    if role:
        query = query.where(User.role == role)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def set_user_role(
    user_id: uuid.UUID,
    payload: RoleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    target.role = payload.role
    await db.commit()
    await db.refresh(target)
    return target


@router.patch("/users/{user_id}/status", response_model=UserOut)
async def set_user_status(
    user_id: uuid.UUID,
    payload: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    if user_id == admin.id and not payload.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot disable your own account."
        )
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    target.is_active = payload.is_active
    await db.commit()
    await db.refresh(target)
    return target


async def _count(db: AsyncSession, model, *where) -> int:
    query = select(func.count()).select_from(model)
    for clause in where:
        query = query.where(clause)
    return int((await db.execute(query)).scalar_one())


@router.get("/stats", dependencies=[Depends(require_admin)])
async def system_stats(db: AsyncSession = Depends(get_db)) -> dict:
    return {
        "users": {
            "total": await _count(db, User),
            "active": await _count(db, User, User.is_active.is_(True)),
            "publishers": await _count(db, User, User.role == UserRole.PUBLISHER),
            "regular_users": await _count(db, User, User.role == UserRole.USER),
            "admins": await _count(db, User, User.role == UserRole.ADMIN),
        },
        "listings": {
            "total": await _count(db, Listing),
            "active": await _count(db, Listing, Listing.is_active.is_(True)),
        },
        "agents": {
            "total": await _count(db, Agent),
            "active": await _count(db, Agent, Agent.is_active.is_(True)),
            "paused": await _count(db, Agent, Agent.is_paused.is_(True)),
        },
        "transactions": {"total": await _count(db, Transaction)},
        "escrow": {
            "held": await _count(db, Escrow, Escrow.status == EscrowStatus.HELD),
            "released": await _count(db, Escrow, Escrow.status == EscrowStatus.RELEASED),
            "refunded": await _count(db, Escrow, Escrow.status == EscrowStatus.REFUNDED),
            "disputed": await _count(db, Escrow, Escrow.status == EscrowStatus.DISPUTED),
        },
    }
