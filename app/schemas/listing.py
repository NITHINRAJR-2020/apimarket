import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AUTH_TYPES = {"none", "api_key", "bearer", "custom_header"}


class AuthConfig(BaseModel):
    """Provider-supplied upstream credentials. This is a WRITE-ONLY shape:
    it is accepted on listing create/update, immediately encrypted into
    Listing.encrypted_credentials, and is never echoed back by any
    response schema -- see ListingOut / ListingSearchResult, neither of
    which has a field capable of holding it.
    """

    type: str = Field(default="none", description="none | api_key | bearer | custom_header")
    api_key: str | None = Field(default=None, description="Required when type == 'api_key'")
    bearer_token: str | None = Field(default=None, description="Required when type == 'bearer'")
    header_name: str | None = Field(
        default=None, description="Header name to send the credential as. Required for 'custom_header'."
    )
    header_value: str | None = Field(default=None, description="Required when type == 'custom_header'")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in AUTH_TYPES:
            raise ValueError(f"auth.type must be one of {sorted(AUTH_TYPES)}")
        return v

    @model_validator(mode="after")
    def validate_fields_for_type(self) -> "AuthConfig":
        if self.type == "api_key" and not self.api_key:
            raise ValueError("auth.api_key is required when auth.type == 'api_key'")
        if self.type == "bearer" and not self.bearer_token:
            raise ValueError("auth.bearer_token is required when auth.type == 'bearer'")
        if self.type == "custom_header" and not (self.header_name and self.header_value):
            raise ValueError(
                "auth.header_name and auth.header_value are required when auth.type == 'custom_header'"
            )
        return self


class ListingCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    category: str = Field(default="general", max_length=60)
    path: str = Field(..., min_length=1, max_length=200)
    upstream_url: str = Field(..., min_length=1)
    price_microalgos: int = Field(..., gt=0, description="Price in micro-USDC (6dp)")
    pay_to_address: str = Field(..., min_length=10, max_length=80)
    asa_id: int | None = None
    owner_contact: str | None = None
    auth: AuthConfig = Field(default_factory=AuthConfig)
    idempotency_key: str | None = Field(
        default=None, max_length=200, description="Optional; retried publishes with the same key are safe."
    )

    @field_validator("path")
    @classmethod
    def normalize_path(cls, v: str) -> str:
        return v.strip("/")

    @field_validator("upstream_url")
    @classmethod
    def validate_upstream(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("upstream_url must start with http:// or https://")
        return v


class ListingUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    upstream_url: str | None = None
    price_microalgos: int | None = Field(default=None, gt=0)
    pay_to_address: str | None = None
    asa_id: int | None = None
    is_active: bool | None = None
    auth: AuthConfig | None = None


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Ownership (the publisher who registered this API). Present for RBAC-aware
    # clients; None for legacy listings created before ownership existed.
    owner_id: uuid.UUID | None = None
    name: str
    description: str | None
    category: str
    path: str
    upstream_url: str
    price_microalgos: int
    asa_id: int | None
    pay_to_address: str
    successful_transactions: int
    failed_transactions: int
    average_latency_ms: int
    is_active: bool
    created_at: datetime
    # Public: how the upstream is protected, never the credential itself.
    auth_type: str
    verification_status: str
    verification_method: str | None = None


class ListingSearchResult(ListingOut):
    reputation_score: int
    success_rate: float
    p95_latency_ms: int
    transaction_count: int
    ranking_reason: str


class VerificationInitiateRequest(BaseModel):
    method: str = Field(..., description="'domain' or 'wallet'")
    domain: str | None = Field(default=None, description="Required for method == 'domain'")

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        if v not in {"domain", "wallet"}:
            raise ValueError("method must be 'domain' or 'wallet'")
        return v


class VerificationInitiateResponse(BaseModel):
    verification_status: str
    verification_method: str
    instructions: str
    verification_token: str


class VerificationConfirmRequest(BaseModel):
    signed_message: str | None = Field(
        default=None, description="For wallet verification: the verification_token signed by pay_to_address"
    )


class VerificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    verification_status: str
    verification_method: str | None
    verified_at: datetime | None
