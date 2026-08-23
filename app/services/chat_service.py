"""Support chatbot for APIMarket, backed by Google's Gemini Flash.

This is a plain REST call to the Gemini `generateContent` endpoint (no SDK
dependency needed -- `httpx` is already a project dependency). The bot is
grounded with a fixed system prompt describing APIMarket's architecture and
purchase lifecycle so it answers questions about *this* app specifically,
rather than as a generic assistant.

Scope is deliberately narrow: if someone asks something unrelated to
APIMarket, the model is instructed to say so and redirect, rather than
answering off-topic questions.
"""

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("apimarket.chat_service")
settings = get_settings()

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Grounding knowledge the model is given on every request. Kept in sync with
# README.md by hand -- update this if the purchase lifecycle or endpoints
# change materially.
SYSTEM_PROMPT = """You are the support assistant embedded in APIMarket, a \
marketplace where AI agents search for APIs and pay for them via the x402 \
protocol into a platform-controlled escrow wallet on Algorand -- not \
directly to the provider. Funds are only released to the provider once the \
platform has proxied the call and confirmed it succeeded; otherwise they are \
refunded automatically to the agent.

Answer questions about how APIMarket works, plainly and concretely, for \
whoever is asking (they may be a provider publishing an API, an agent \
operator, or someone evaluating the project). Prefer short, direct answers; \
use a numbered or bulleted list only when the question genuinely has \
multiple steps. Do not use markdown headers.

Here is what you know about the app:

ARCHITECTURE
- Backend: FastAPI + async SQLAlchemy 2.0, Postgres (Neon), Algorand Testnet.
- Frontend: React + Vite + Tailwind dashboard for agents, listings, \
transactions, and the escrow ledger.
- Payment rail: the x402 HTTP-402 protocol, with real on-chain Algorand \
payment verification (algod/indexer), not a simulated flow.

HOW A PURCHASE WORKS
1. An AI agent calls GET /market/search to find a listing.
2. It calls GET /market/{path}/call with its X-Agent-Key header.
3. The policy engine checks the agent (active/paused), the provider \
(active/allow-listed/reputation), the per-transaction limit, and the daily \
budget -- all BEFORE any money moves. A blocked purchase never reaches \
payment.
4. If approved and no payment proof is attached, the server replies with \
HTTP 402 and a signed quote. Critically, `payTo` in that quote is the \
PLATFORM's escrow wallet, never the provider's address directly.
5. The agent pays that quote on Algorand Testnet, then retries the call \
with a payment proof (tx id + quote token).
6. The server verifies the payment on-chain against the escrow wallet, \
marks escrow HELD, and only then proxies the real request to the \
provider's upstream_url.
7. If the upstream call succeeds, escrow is RELEASED to the provider (a \
real signed payout transaction) and the listing's reputation counters \
update. If it fails, escrow is REFUNDED back to the agent's own wallet \
instead, and the provider's failure counter updates -- the provider is \
only ever paid for work it actually delivered.
8. If an automatic release or refund itself fails to sign/submit (e.g. \
insufficient ALGO for fees), the escrow is marked DISPUTED for manual \
admin resolution rather than silently losing track of funds.

TRANSACTION STATUS LIFECYCLE
PENDING -> POLICY_BLOCKED | QUOTE_ISSUED -> ESCROW_HELD -> UPSTREAM_CALLED \
-> SERVICE_COMPLETED | REFUNDED | DISPUTED

REPUTATION
Each listing's reputation (0-100) is computed live, not cached, from a \
transparent weighted formula: 60% success rate, 15% latency, 15% refund \
rate, 10% dispute rate. New providers with low transaction volume are \
blended toward a neutral baseline score so one lucky success doesn't show \
as a perfect 100.

TRUST MODEL, HONESTLY
This is platform-custodied escrow -- the same trust model as a payment \
processor holding buyer funds -- not trustless on-chain escrow enforced by \
a smart contract. The platform's escrow wallet key is a real secret an \
operator controls. Fully trustless escrow would need an Algorand smart \
contract (stateful app / ASC1) instead of a single platform-held key. Be \
upfront about this if asked whether funds are "safe" or "trustless".

KEY ENDPOINTS
- POST /api/agents -- register a buying agent + its spending policy, \
returns an api_key used as the X-Agent-Key header.
- POST /api/listings -- publish a paid API as a provider (name, category, \
path, upstream_url, price, pay_to_address).
- GET /market/search -- discovery, returns listings ranked by live \
reputation.
- GET|POST /market/{path}/call -- the actual buy-and-call endpoint.
- GET /api/escrow -- escrow ledger; admin release/refund for DISPUTED \
cases.
- GET /api/dashboard/... -- transaction history and lookups.
- GET /health -- basic liveness + which Algorand network/escrow wallet is \
configured.

CURRENT LIMITATIONS (be honest if asked)
- Admin routes (/api/listings, /api/agents, /api/escrow) have no auth yet \
beyond what protects purchases (X-Agent-Key).
- No automated test suite is wired up yet for the escrow-wallet payout \
path.
- No rate limiting yet.

STYLE
- Be conversational and concise, like a helpful teammate, not a formal \
document.
- If you don't know something specific (e.g. exact pricing of a particular \
live listing, or account-specific data), say so plainly instead of \
guessing, and suggest checking the dashboard or docs.
- If a question is entirely unrelated to APIMarket (e.g. general trivia, \
other companies), politely say you're the APIMarket assistant and steer \
back to what you can help with.
"""


class ChatServiceError(Exception):
    pass


async def ask_gemini(message: str, history: list[dict[str, str]] | None = None) -> str:
    """Send one chat turn to Gemini Flash, grounded with SYSTEM_PROMPT.

    `history` is a list of {"role": "user"|"assistant", "content": str}
    from the current conversation, oldest first. Only the last
    CHATBOT_HISTORY_TURNS entries are sent, to keep requests small.
    """
    if not settings.GEMINI_API_KEY:
        raise ChatServiceError(
            "Chatbot is not configured yet -- GEMINI_API_KEY is missing on the server."
        )

    contents = []
    for turn in (history or [])[-settings.CHATBOT_HISTORY_TURNS :]:
        role = "model" if turn.get("role") == "assistant" else "user"
        text = (turn.get("content") or "").strip()
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 512,
        },
    }

    url = GEMINI_ENDPOINT.format(model=settings.GEMINI_MODEL)

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                url,
                params={"key": settings.GEMINI_API_KEY},
                json=payload,
            )
    except httpx.RequestError as exc:
        logger.error("Gemini request failed: %s", exc)
        raise ChatServiceError("Couldn't reach the chatbot service. Try again shortly.") from exc

    if response.status_code != 200:
        logger.error("Gemini returned %s: %s", response.status_code, response.text[:500])
        raise ChatServiceError("The chatbot service returned an error. Try again shortly.")

    data = response.json()
    try:
        candidates = data["candidates"]
        if not candidates:
            raise KeyError("candidates")
        parts = candidates[0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts).strip()
    except (KeyError, IndexError) as exc:
        logger.error("Unexpected Gemini response shape: %s", data)
        raise ChatServiceError("Got an unexpected response from the chatbot service.") from exc

    if not text:
        raise ChatServiceError("The chatbot didn't return a response. Try rephrasing.")

    return text
