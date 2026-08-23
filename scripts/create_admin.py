"""Create (or promote) the initial platform admin from environment variables.

Usage:
    ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='a-strong-password' \
        python -m scripts.create_admin

Safe to run repeatedly: if the account already exists it is promoted to
admin and (optionally) re-activated, but the password is only set on
creation. Credentials come from the environment -- nothing is hardcoded.
"""
import asyncio
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, init_models
from app.core.security import hash_password
from app.models.user import User, UserRole

settings = get_settings()


async def main() -> int:
    email = settings.ADMIN_EMAIL.strip().lower()
    password = settings.ADMIN_PASSWORD

    if not email:
        print("ERROR: ADMIN_EMAIL is empty.", file=sys.stderr)
        return 1

    # Ensure tables exist (harmless if already created / migrated).
    await init_models()

    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(User).where(func.lower(User.email) == email))
        ).scalar_one_or_none()

        if existing is not None:
            existing.role = UserRole.ADMIN
            existing.is_active = True
            await db.commit()
            print(f"Promoted existing user {email} to admin.")
            return 0

        if not password:
            print(
                "ERROR: user does not exist and ADMIN_PASSWORD is empty; "
                "set ADMIN_PASSWORD to create a new admin.",
                file=sys.stderr,
            )
            return 1

        admin = User(
            name=settings.ADMIN_NAME or "Platform Admin",
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        print(f"Created admin {email}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
