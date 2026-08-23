import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PUBLISHER = "publisher"
    USER = "user"


class User(Base):
    """A human account on the platform.

    Roles map onto the existing domain:
      * publisher -> owns Listings (the APIs published to the marketplace)
      * user      -> owns Agents (the autonomous buyers)
      * admin     -> full system access + escrow dispute resolution

    `password_hash` is a bcrypt hash -- plaintext passwords are never stored.
    `is_active` gates login: a disabled account authenticates to nothing.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.USER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    listings: Mapped[list["Listing"]] = relationship(  # noqa: F821
        back_populates="owner", foreign_keys="Listing.owner_id"
    )
    agents: Mapped[list["Agent"]] = relationship(  # noqa: F821
        back_populates="owner", foreign_keys="Agent.owner_id"
    )

    def __repr__(self) -> str:
        return f"<User email={self.email} role={self.role}>"
