import secrets
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import load_owned_agent, require_role
from app.core.database import get_db
from app.models.agent import Agent, AllowedListing, SpendingPolicy
from app.models.user import User, UserRole
from app.schemas.agent import AgentCreate, AgentOut, AgentPauseRequest

router = APIRouter(prefix="/api/agents", tags=["agents"])

# Agents belong to USERs. Admins may also act (require_role always allows admin).
_require_user = require_role(UserRole.USER)


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_user),
) -> Agent:
    # Ownership is derived from the authenticated user, never from the client.
    agent = Agent(
        name=payload.name,
        wallet_address=payload.wallet_address,
        api_key=secrets.token_hex(24),
        owner_id=user.id,
    )
    db.add(agent)
    await db.flush()

    policy = SpendingPolicy(
        agent_id=agent.id,
        max_transaction_amount=payload.policy.max_transaction_amount,
        daily_limit=payload.policy.daily_limit,
        min_provider_reputation=payload.policy.min_provider_reputation,
        restrict_to_allowed_listings=payload.policy.restrict_to_allowed_listings,
    )
    db.add(policy)
    await db.flush()

    for listing_id in payload.policy.allowed_listing_ids:
        db.add(AllowedListing(policy_id=policy.id, listing_id=listing_id))

    await db.commit()

    result = await db.execute(
        select(Agent).where(Agent.id == agent.id).options(selectinload(Agent.policy))
    )
    return result.scalar_one()


@router.get("", response_model=list[AgentOut])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_user),
) -> list[Agent]:
    # Data isolation enforced in the query: users see only their own agents,
    # admins see everything.
    query = select(Agent).options(selectinload(Agent.policy)).order_by(Agent.created_at.desc())
    if user.role != UserRole.ADMIN:
        query = query.where(Agent.owner_id == user.id)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_user),
) -> Agent:
    return await load_owned_agent(db, agent_id, user)


@router.patch("/{agent_id}/pause", response_model=AgentOut)
async def pause_agent(
    agent_id: uuid.UUID,
    payload: AgentPauseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_user),
) -> Agent:
    """Emergency stop: the policy engine checks is_paused BEFORE any
    payment attempt, so this blocks every subsequent purchase instantly."""
    agent = await load_owned_agent(db, agent_id, user)
    agent.is_paused = payload.paused
    await db.commit()
    await db.refresh(agent)
    return agent
