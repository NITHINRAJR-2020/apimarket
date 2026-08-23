import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    listing_id: uuid.UUID | None
    amount_microalgos: int
    status: str
    deposit_tx_id: str | None
    payer_address: str | None
    risk_score: int | None
    response_status_code: int | None
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None


class EscrowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transaction_id: uuid.UUID
    status: str
    amount_microalgos: int
    platform_fee_microalgos: int
    deposit_tx_id: str
    payout_tx_id: str | None
    refund_tx_id: str | None
    provider_share_bps: int | None
    provider_amount_microalgos: int | None
    agent_amount_microalgos: int | None
    notes: str | None
    evidence: str | None
    created_at: datetime
    resolved_at: datetime | None


class EscrowResolveRequest(BaseModel):
    notes: str | None = None


class EvidenceSubmitRequest(BaseModel):
    submitted_by: str  # "agent" or "provider" -- freeform label for the audit trail
    message: str
    reference_url: str | None = None  # e.g. a link to logs, screenshots, upstream response dump


class PartialReleaseRequest(BaseModel):
    provider_share_bps: int  # 0-10000; provider gets this fraction, agent is refunded the rest
    notes: str | None = None
