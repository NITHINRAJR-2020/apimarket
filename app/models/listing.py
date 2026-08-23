import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Listing(Base):
    """A paid API published to the marketplace.

    Combines PayPerQuery's registered "Endpoint" (what to call, and the
    x402 price) with AgentVault's "Provider" (reputation bookkeeping),
    with one crucial change: `pay_to_address` is the PROVIDER'S OWN payout
    address, but it is never handed to the buying agent as the x402
    recipient. The x402 quote for every listing always names the
    platform's escrow wallet as `payTo` (see payments/x402_quote.py) --
    `pay_to_address` here is only used later, by the escrow service, to
    pay the provider out of escrow after a successful call.
    """

    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # --- Ownership: the PUBLISHER who registered this API. Nullable so that
    # rows created before RBAC survive the migration; new listings always set
    # it from the authenticated publisher's token, never from client input. ---
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # --- Marketplace catalog fields ---
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False, default="general", index=True)
    path: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    upstream_url: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Pricing (x402 "exact" scheme, USDC on Algorand) ---
    price_microalgos: Mapped[int] = mapped_column(BigInteger, nullable=False)  # micro-USDC, 6dp
    asa_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # None => native ALGO

    # --- Where the provider actually gets paid, from escrow, on release ---
    pay_to_address: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # --- Reputation inputs (see policies/reputation.py for the formula) ---
    successful_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    partial_transactions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_latency_ms: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    refund_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dispute_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Bounded ring-buffer of the most recent real upstream latencies
    # (JSON-encoded list of ints, capped at LATENCY_SAMPLE_WINDOW in
    # policies/reputation.py). Powers p50/p95 and weights recent
    # performance more than old, without a full time-decay model.
    latency_samples: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Provider authentication for the upstream API (Feature 1) ---
    # `auth_type` is public (agents/discovery may see how a listing is
    # protected); `encrypted_credentials` never is -- it is Fernet-encrypted
    # (see app/core/crypto.py) and only ever decrypted inside the proxy
    # service immediately before forwarding the upstream request.
    auth_type: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    auth_header_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    encrypted_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Provider verification (Feature 4) ---
    verification_status: Mapped[str] = mapped_column(
        String(20), default="unverified", nullable=False, index=True
    )
    verification_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # wallet | domain
    verification_domain: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Optional client-supplied idempotency key so retried "publish listing"
    # requests resolve to the same row instead of creating duplicates
    # (Feature 5). Nullable + unique: NULLs are treated as distinct.
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User | None"] = relationship(  # noqa: F821
        back_populates="listings", foreign_keys=[owner_id]
    )

    def __repr__(self) -> str:
        return f"<Listing path={self.path} price={self.price_microalgos}>"
