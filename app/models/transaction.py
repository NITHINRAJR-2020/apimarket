import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"                    # created, policy not yet evaluated
    POLICY_BLOCKED = "POLICY_BLOCKED"       # policy engine rejected before any payment
    QUOTE_ISSUED = "QUOTE_ISSUED"           # 402 quote sent to the agent, awaiting payment
    PAYMENT_SUBMITTED = "PAYMENT_SUBMITTED"  # payment proof received, verification in flight
    ESCROW_HELD = "ESCROW_HELD"             # payment verified on-chain, funds sitting in platform escrow
    UPSTREAM_CALLED = "UPSTREAM_CALLED"     # proxying to the provider's API, awaiting result
    SERVICE_COMPLETED = "SERVICE_COMPLETED"  # upstream call succeeded, escrow released to provider
    FAILED = "FAILED"                       # upstream call failed / payment verification failed
    REFUNDED = "REFUNDED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"  # upstream returned a partial result, escrow split                   # escrow refunded back to the agent
    DISPUTED = "DISPUTED"                   # manually flagged, awaiting human resolution


class Transaction(Base):
    """One purchase attempt by an agent against a marketplace listing.

    `idempotency_key` has a unique index: a retried request with the same
    key resolves to the SAME row instead of creating a new transaction or
    double-charging the agent.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_idempotency_key_unique", "idempotency_key", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="SET NULL"), nullable=True
    )
    amount_microalgos: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asa_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status"),
        default=TransactionStatus.PENDING,
        nullable=False,
    )
    quote_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    deposit_tx_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # agent -> escrow
    payer_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_status_code: Mapped[int | None] = mapped_column(nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agent: Mapped["Agent"] = relationship(back_populates="transactions")
    escrow: Mapped["Escrow | None"] = relationship(
        back_populates="transaction", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} status={self.status} amount={self.amount_microalgos}>"
