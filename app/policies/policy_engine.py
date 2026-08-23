"""Deterministic policy engine.

`check_payment_policy` is the single gate every payment must pass through
BEFORE any x402 payment is attempted. It is pure and synchronous given its
inputs (no I/O), which is what makes it unit-testable in isolation -- all
I/O (loading the agent, policy, provider, today's spend) happens in the
caller (payments/payment_service.py) and is passed in here as plain values.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class PolicyBlockReason(str, Enum):
    AGENT_INACTIVE = "AGENT_INACTIVE"
    AGENT_PAUSED = "AGENT_PAUSED"
    PROVIDER_NOT_ALLOWED = "PROVIDER_NOT_ALLOWED"
    PROVIDER_INACTIVE = "PROVIDER_INACTIVE"
    PROVIDER_REPUTATION_TOO_LOW = "PROVIDER_REPUTATION_TOO_LOW"
    TRANSACTION_LIMIT_EXCEEDED = "TRANSACTION_LIMIT_EXCEEDED"
    DAILY_LIMIT_EXCEEDED = "DAILY_LIMIT_EXCEEDED"
    INVALID_AMOUNT = "INVALID_AMOUNT"


@dataclass
class PolicyDecision:
    approved: bool
    reason: PolicyBlockReason | None = None
    risk_score: int = 0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "reason": self.reason.value if self.reason else None,
            "risk_score": self.risk_score,
            "details": self.details,
        }


def _compute_risk_score(
    *,
    amount: Decimal,
    max_transaction_amount: Decimal,
    remaining_daily_budget: Decimal,
    daily_limit: Decimal,
    provider_reputation: int,
) -> int:
    """A simple, explainable 0-100 risk score for APPROVED transactions
    (higher = riskier, though still within policy). Not used for the
    approve/block decision itself -- that's purely rule-based above --
    this is supplementary context shown in the dashboard/response.
    """
    tx_ratio = float(amount / max_transaction_amount) if max_transaction_amount > 0 else 1.0
    daily_ratio = (
        float((daily_limit - remaining_daily_budget + amount) / daily_limit) if daily_limit > 0 else 1.0
    )
    reputation_risk = max(0, 100 - provider_reputation) / 100

    score = (tx_ratio * 40) + (daily_ratio * 35) + (reputation_risk * 25)
    return min(100, round(score))


def check_payment_policy(
    *,
    agent_is_active: bool,
    agent_is_paused: bool,
    amount: Decimal,
    max_transaction_amount: Decimal,
    daily_limit: Decimal,
    already_spent_today: Decimal,
    provider_is_allowed: bool,
    provider_is_active: bool,
    provider_reputation: int,
    min_provider_reputation: int,
) -> PolicyDecision:
    """Pure function evaluating all policy rules in a fixed, deterministic
    order. The FIRST failing rule determines the block reason (rules are
    checked cheapest/most-fundamental first).
    """
    if amount <= 0:
        return PolicyDecision(
            approved=False,
            reason=PolicyBlockReason.INVALID_AMOUNT,
            risk_score=100,
            details={"amount": str(amount)},
        )

    if not agent_is_active:
        return PolicyDecision(approved=False, reason=PolicyBlockReason.AGENT_INACTIVE, risk_score=100)

    if agent_is_paused:
        return PolicyDecision(approved=False, reason=PolicyBlockReason.AGENT_PAUSED, risk_score=100)

    if not provider_is_active:
        return PolicyDecision(
            approved=False, reason=PolicyBlockReason.PROVIDER_INACTIVE, risk_score=100
        )

    if not provider_is_allowed:
        return PolicyDecision(
            approved=False, reason=PolicyBlockReason.PROVIDER_NOT_ALLOWED, risk_score=100
        )

    if provider_reputation < min_provider_reputation:
        return PolicyDecision(
            approved=False,
            reason=PolicyBlockReason.PROVIDER_REPUTATION_TOO_LOW,
            risk_score=95,
            details={
                "provider_reputation": provider_reputation,
                "min_required": min_provider_reputation,
            },
        )

    if amount > max_transaction_amount:
        return PolicyDecision(
            approved=False,
            reason=PolicyBlockReason.TRANSACTION_LIMIT_EXCEEDED,
            risk_score=90,
            details={
                "requested": str(amount),
                "max_allowed": str(max_transaction_amount),
            },
        )

    remaining_daily_budget = daily_limit - already_spent_today
    if amount > remaining_daily_budget:
        return PolicyDecision(
            approved=False,
            reason=PolicyBlockReason.DAILY_LIMIT_EXCEEDED,
            risk_score=90,
            details={
                "requested": str(amount),
                "remaining_daily_budget": str(remaining_daily_budget),
                "daily_limit": str(daily_limit),
            },
        )

    risk_score = _compute_risk_score(
        amount=amount,
        max_transaction_amount=max_transaction_amount,
        remaining_daily_budget=remaining_daily_budget,
        daily_limit=daily_limit,
        provider_reputation=provider_reputation,
    )

    return PolicyDecision(
        approved=True,
        reason=None,
        risk_score=risk_score,
        details={
            "remaining_daily_budget_after": str(remaining_daily_budget - amount),
        },
    )
