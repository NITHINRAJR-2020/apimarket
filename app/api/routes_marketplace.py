from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.listing import ListingOut, ListingSearchResult
from app.services.marketplace_service import search_listings

router = APIRouter(prefix="/market", tags=["marketplace"])


@router.get("/search", response_model=list[ListingSearchResult])
async def search(
    q: str | None = None,
    category: str | None = None,
    min_reputation: int = 0,
    max_price: int | None = None,
    max_latency_ms: int | None = None,
    min_success_rate: float | None = None,
    verified_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    """What a logged-in user (or an agent operator) calls to find an API:
    free-text query, optional category filter, an optional reputation floor,
    and optional price / latency / success-rate / verification filters.
    Results are ranked by a blend of reputation, success rate, price, and
    latency -- never a single hard-coded provider -- with a short explainable
    reason per result. Callers that pass only `q`, `category`, or
    `min_reputation` see identical behavior to before; the new filters are
    optional and additive."""
    results = await search_listings(
        db,
        query=q,
        category=category,
        min_reputation=min_reputation,
        max_price=max_price,
        max_latency_ms=max_latency_ms,
        min_success_rate=min_success_rate,
        verified_only=verified_only,
    )
    out = []
    for r in results:
        base = ListingOut.model_validate(r.listing, from_attributes=True)
        out.append(
            ListingSearchResult(
                **base.model_dump(),
                reputation_score=r.reputation.score,
                success_rate=r.reputation.success_rate,
                p95_latency_ms=r.reputation.p95_latency_ms,
                transaction_count=r.reputation.total_volume,
                ranking_reason=r.ranking_reason,
            )
        )
    return out
