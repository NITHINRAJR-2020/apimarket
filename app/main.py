import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_admin,
    routes_agents,
    routes_auth,
    routes_chat,
    routes_dashboard,
    routes_escrow,
    routes_listings,
    routes_marketplace,
    routes_purchase,
)
from app.core.config import get_settings
from app.core.database import init_models
from app.payments import escrow_wallet
from app.services import escrow_watchdog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("apimarket.main")
settings = get_settings()


async def _escrow_watchdog_loop() -> None:
    """Runs escrow_watchdog.run_once() on a fixed interval for the life of
    the app. A single misbehaving sweep logs and retries next tick rather
    than crashing the whole process."""
    while True:
        try:
            handled = await escrow_watchdog.run_once()
            if handled:
                logger.info("Escrow watchdog auto-resolved %d stale escrow(s)", handled)
        except Exception:
            logger.exception("Escrow watchdog sweep failed")
        await asyncio.sleep(settings.ESCROW_WATCHDOG_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.ENVIRONMENT == "development":
        await init_models()

    if settings.ESCROW_WALLET_MNEMONIC:
        derived = escrow_wallet.escrow_wallet_address()
        if derived != settings.ESCROW_WALLET_ADDRESS:
            logger.warning(
                "ESCROW_WALLET_ADDRESS (%s) does not match the address derived from "
                "ESCROW_WALLET_MNEMONIC (%s) -- quotes and payouts will disagree on "
                "where funds live. Fix this before accepting real payments.",
                settings.ESCROW_WALLET_ADDRESS, derived,
            )
        else:
            logger.info("Escrow wallet configured correctly: %s", derived)
    else:
        logger.warning(
            "ESCROW_WALLET_MNEMONIC is not set -- quotes will be issued but escrow "
            "release/refund payouts will fail until it is configured."
        )

    watchdog_task = asyncio.create_task(_escrow_watchdog_loop())
    try:
        yield
    finally:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "A marketplace where AI agents search for APIs, and pay for them via the "
        "x402 protocol into a platform-held escrow wallet -- not directly to the "
        "provider. Funds are only released to the provider once the paid API call "
        "has actually been proxied and confirmed successful; otherwise they're "
        "refunded back to the agent. No pay-and-pray."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_auth.router)
app.include_router(routes_admin.router)
app.include_router(routes_agents.router)
app.include_router(routes_listings.router)
app.include_router(routes_marketplace.router)
app.include_router(routes_purchase.router)
app.include_router(routes_escrow.router)
app.include_router(routes_dashboard.router)
app.include_router(routes_chat.router)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "network": settings.ALGORAND_NETWORK, "escrow_wallet": settings.ESCROW_WALLET_ADDRESS}
