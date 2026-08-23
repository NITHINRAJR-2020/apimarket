import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SpendingPolicyIn(BaseModel):
    max_transaction_amount: Decimal = Field(..., gt=0, description="USD, max per single purchase")
    daily_limit: Decimal = Field(..., gt=0, description="USD, max total spend per rolling day")
    min_provider_reputation: int = Field(default=50, ge=0, le=100)
    restrict_to_allowed_listings: bool = False
    allowed_listing_ids: list[uuid.UUID] = Field(default_factory=list)


class SpendingPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    max_transaction_amount: Decimal
    daily_limit: Decimal
    min_provider_reputation: int
    restrict_to_allowed_listings: bool


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    wallet_address: str = Field(..., min_length=10, max_length=80)
    policy: SpendingPolicyIn


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    name: str
    wallet_address: str
    api_key: str
    is_active: bool
    is_paused: bool
    created_at: datetime
    policy: SpendingPolicyOut | None = None


class AgentPauseRequest(BaseModel):
    paused: bool
