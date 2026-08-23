import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Agent(Base):
    """An autonomous AI agent with a wallet and an enforced spending policy."""

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Ownership: the USER who operates this agent. Nullable for pre-RBAC rows;
    # set from the authenticated user's token on creation, never from client input.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    wallet_address: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    api_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User | None"] = relationship(  # noqa: F821
        back_populates="agents", foreign_keys=[owner_id]
    )
    policy: Mapped["SpendingPolicy"] = relationship(
        back_populates="agent", uselist=False, cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="agent")

    def __repr__(self) -> str:
        return f"<Agent name={self.name} wallet={self.wallet_address}>"


class SpendingPolicy(Base):
    """Enforced spending policy for a single agent.

    Monetary values are stored as USD with 6 decimal places (matching
    USDC's 6-decimal precision) using Numeric, never floats.
    """

    __tablename__ = "spending_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    max_transaction_amount: Mapped[Numeric] = mapped_column(Numeric(18, 6), nullable=False)
    daily_limit: Mapped[Numeric] = mapped_column(Numeric(18, 6), nullable=False)
    min_provider_reputation: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    restrict_to_allowed_listings: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agent: Mapped["Agent"] = relationship(back_populates="policy")
    allowed_listings: Mapped[list["AllowedListing"]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SpendingPolicy agent_id={self.agent_id} max_tx={self.max_transaction_amount}>"


class AllowedListing(Base):
    """Join table: which marketplace listings a policy permits the agent to buy from.

    Only enforced when `restrict_to_allowed_listings` is True on the policy,
    so by default an agent can shop the whole marketplace subject to its
    limits and the minimum reputation bar.
    """

    __tablename__ = "allowed_listings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spending_policies.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )

    policy: Mapped["SpendingPolicy"] = relationship(back_populates="allowed_listings")
    listing: Mapped["Listing"] = relationship()
