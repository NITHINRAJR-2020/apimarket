import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EscrowStatus(str, enum.Enum):
    HELD = "HELD"          # funds confirmed in the platform's escrow wallet
    RELEASED = "RELEASED"    # paid out on-chain to the provider's pay_to_address
    REFUNDED = "REFUNDED"
    PARTIALLY_RELEASED = "PARTIALLY_RELEASED"  # split between provider and agent    # paid out on-chain back to the agent's payer_address
    DISPUTED = "DISPUTED"    # frozen, awaiting manual admin resolution


class Escrow(Base):
    """Real, platform-custodied escrow.

    Unlike a status flag layered on top of an already-settled direct
    payment, this row IS the custody record: `deposit_tx_id` is the
    on-chain transaction that moved the agent's funds into
    `settings.ESCROW_WALLET_ADDRESS`, and the funds stay there -- under
    the platform's control, not the provider's -- until either:

      * `release()` fires a real payout transaction, signed by the
        platform's escrow wallet, to the provider's `pay_to_address`
        (recorded in `payout_tx_id`), or
      * `refund()` fires a real payout transaction back to the agent's
        `payer_address` (recorded in `refund_tx_id`).

    Nothing reaches the provider until the upstream API call the agent
    paid for has actually been proxied and returned a successful
    response -- that's what turns "pay and pray" into an actual escrow.
    """

    __tablename__ = "escrows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[EscrowStatus] = mapped_column(
        Enum(EscrowStatus, name="escrow_status"), default=EscrowStatus.HELD, nullable=False
    )
    amount_microalgos: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asa_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    platform_fee_microalgos: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    deposit_tx_id: Mapped[str] = mapped_column(String(100), nullable=False)   # agent -> escrow wallet
    payout_tx_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # escrow -> provider
    refund_tx_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # escrow -> agent

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Populated only when status == PARTIALLY_RELEASED
    provider_share_bps: Mapped[int | None] = mapped_column(nullable=True)
    provider_amount_microalgos: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    agent_amount_microalgos: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Dispute evidence trail -- freeform JSON-serializable text blobs
    # attached by either party or the platform while status == DISPUTED.
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="escrow")

    def __repr__(self) -> str:
        return f"<Escrow tx_id={self.transaction_id} status={self.status}>"
