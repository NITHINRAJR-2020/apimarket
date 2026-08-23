"""Authentication & authorization dependencies -- the security source of truth.

Every protected endpoint depends on `get_current_user`, which re-loads the
user from the database on each request (so a disabled account or a changed
role takes effect immediately, never trusting the token's claims blindly).

Role gates (`require_admin`, `require_publisher`, `require_user`) reject
authenticated-but-unauthorized callers with 403.

Ownership resolvers (`load_owned_agent`, `load_owned_listing`) enforce
tenancy AT THE QUERY LEVEL: a non-admin only ever sees rows they own, and a
cross-tenant id returns 404 (not 403) so we don't leak that another owner's
resource exists. Admins bypass the ownership filter.
"""
import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.agent import Agent
from app.models.listing import Listing
from app.models.user import User, UserRole

# auto_error=False so we can return our own 401 shape consistently.
_bearer = HTTPBearer(auto_error=False)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise _CREDENTIALS_EXC
    payload = decode_access_token(creds.credentials)
    if payload is None or "sub" not in payload:
        raise _CREDENTIALS_EXC
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (ValueError, TypeError):
        raise _CREDENTIALS_EXC

    user = await db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_EXC
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


def require_role(*roles: UserRole) -> Callable:
    """Dependency factory: allow only the given roles (admin always allowed)."""
    allowed = set(roles) | {UserRole.ADMIN}

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return user

    return _checker


# Convenience gates.
require_admin = require_role(UserRole.ADMIN)
require_publisher = require_role(UserRole.PUBLISHER)
require_user = require_role(UserRole.USER)


async def load_owned_agent(db: AsyncSession, agent_id: uuid.UUID, user: User) -> Agent:
    """Return the agent if the caller may access it, else 404.

    admin  -> any agent
    user   -> only their own agents
    others -> treated as not found (no leak)
    """
    query = select(Agent).where(Agent.id == agent_id).options(selectinload(Agent.policy))
    if user.role != UserRole.ADMIN:
        query = query.where(Agent.owner_id == user.id)
    agent = (await db.execute(query)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


async def load_owned_listing(db: AsyncSession, listing_id: uuid.UUID, user: User) -> Listing:
    """Return the listing if the caller may manage it, else 404.

    admin     -> any listing
    publisher -> only listings they own
    others    -> treated as not found (no leak)
    """
    query = select(Listing).where(Listing.id == listing_id)
    if user.role != UserRole.ADMIN:
        query = query.where(Listing.owner_id == user.id)
    listing = (await db.execute(query)).scalar_one_or_none()
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    return listing
