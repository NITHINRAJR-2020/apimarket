"""Shared test helper: seed an admin and mint a bearer token.

The RBAC merge means /api/listings, /api/agents and /market/search now
require authentication. An admin passes every role gate (require_role
always allows admin) and may read any owned resource, so authenticating
the test client as an admin lets the pre-RBAC test bodies run unchanged
while still exercising the real auth stack.
"""
import uuid

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, hash_password
from app.models.user import User, UserRole


async def seed_admin_token(email: str | None = None) -> str:
    email = email or f"admin-{uuid.uuid4().hex[:8]}@test.local"
    async with AsyncSessionLocal() as db:
        admin = User(
            name="Test Admin",
            email=email,
            password_hash=hash_password("password123"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
    return create_access_token(subject=str(admin.id), role=admin.role.value)
