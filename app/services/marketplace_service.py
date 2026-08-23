"""Marketplace discovery: what an AI agent uses to find an API worth buying."""

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing import Listing
from app.policies.reputation import ReputationBreakdown, compute_reputation


@dataclass
class SearchResult:
    listing: Listing
    reputation: ReputationBreakdown
    ranking_reason: str


def _ranking_reason(reputation: ReputationBreakdown, price_microalgos: int) -> str:
    """Short, explainable reason string -- no internal security-sensitive
    details, just the signals that actually moved this result's rank."""
    reasons: list[str] = []
    if reputation.score >= 85:
        reasons.append("high reputation")
    elif reputation.score < 50:
        reasons.append("low reputation")

    if reputation.p95_latency_ms and reputation.p95_latency_ms <= 300:
        reasons.append("low latency")
    elif reputation.p95_latency_ms and reputation.p95_latency_ms >= 1500:
        reasons.append("higher latency")

    if reputation.success_rate >= 0.98 and reputation.total_volume > 0:
        reasons.append("strong success rate")

    if reputation.total_volume < 5:
        reasons.append("limited transaction history")

    if not reasons:
        reasons.append("balanced reputation, price, and latency")

    return ", ".join(reasons).capitalize()


def _rank_key(result: SearchResult) -> tuple:
    """Composite ranking: reputation dominates, then success rate, then
    lower price/latency break ties. All db-computed inputs, sorted in
    Python once (post-filter set is already narrowed by the SQL WHERE
    clause below, so this never touches the full marketplace table)."""
    return (
        -result.reputation.score,
        -result.reputation.success_rate,
        result.listing.price_microalgos,
        result.reputation.p95_latency_ms,
    )


async def search_listings(
    db: AsyncSession,
    *,
    query: str | None = None,
    category: str | None = None,
    min_reputation: int = 0,
    max_price: int | None = None,
    max_latency_ms: int | None = None,
    min_success_rate: float | None = None,
    verified_only: bool = False,
    include_inactive: bool = False,
) -> list[SearchResult]:
    """Returns ranked SearchResult objects, best match first.

    Reputation is computed live from each listing's transaction counters
    rather than cached, so it always reflects the latest escrow outcomes.
    Filtering that the database can do (active flag, category, free-text,
    price ceiling, verification) is pushed into the SQL WHERE clause;
    only filters that depend on the derived reputation score/latency
    percentile/success-rate (which aren't stored columns) are applied
    in Python, and only against the already-narrowed result set.
    """
    stmt = select(Listing)
    if not include_inactive:
        stmt = stmt.where(Listing.is_active.is_(True))
    if category:
        stmt = stmt.where(Listing.category == category)
    if query:
        like = f"%{query}%"
        stmt = stmt.where(or_(Listing.name.ilike(like), Listing.description.ilike(like), Listing.category.ilike(like)))
    if max_price is not None:
        stmt = stmt.where(Listing.price_microalgos <= max_price)
    if verified_only:
        stmt = stmt.where(Listing.verification_status == "verified")

    result = await db.execute(stmt)
    listings = list(result.scalars().all())

    scored: list[SearchResult] = []
    for listing in listings:
        reputation = compute_reputation(
            successful_transactions=listing.successful_transactions,
            failed_transactions=listing.failed_transactions,
            average_latency_ms=listing.average_latency_ms,
            refund_count=listing.refund_count,
            dispute_count=listing.dispute_count,
            latency_samples_json=listing.latency_samples,
        )
        if reputation.score < min_reputation:
            continue
        if max_latency_ms is not None and reputation.p95_latency_ms > max_latency_ms:
            continue
        if min_success_rate is not None and reputation.success_rate < min_success_rate:
            continue
        scored.append(
            SearchResult(
                listing=listing,
                reputation=reputation,
                ranking_reason=_ranking_reason(reputation, listing.price_microalgos),
            )
        )

    scored.sort(key=_rank_key)
    return scored
