"""Signed, tamper-evident x402 price quotes.

The one deliberate change from a plain pay-per-request gateway: `to` in
every quote is always `settings.ESCROW_WALLET_ADDRESS` -- the platform's
own custody wallet -- never the listing's `pay_to_address`. That's what
makes the marketplace escrow-backed: an agent's payment proof can only
ever verify against a payment that landed in platform custody, and the
provider is paid out later, separately, by the escrow service.
"""

import base64
import hashlib
import hmac
import json
import time

from app.core.config import get_settings

settings = get_settings()


class QuoteError(Exception):
    pass


def _sign(payload: str) -> str:
    digest = hmac.new(
        settings.X402_QUOTE_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def create_quote(
    *,
    listing_path: str,
    price_microalgos: int,
    asa_id: int | None,
) -> tuple[str, int]:
    """Create a tamper-evident quote token binding the terms of payment.

    Returns (quote_token, expires_at_unix_ts).
    """
    expires_at = int(time.time()) + settings.X402_QUOTE_TTL_SECONDS
    claims = {
        "path": listing_path,
        "amt": price_microalgos,
        "to": settings.ESCROW_WALLET_ADDRESS,
        "asa": asa_id or 0,
        "net": settings.ALGORAND_NETWORK,
        "exp": expires_at,
    }
    raw = json.dumps(claims, separators=(",", ":"), sort_keys=True)
    encoded_claims = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")
    signature = _sign(encoded_claims)
    return f"{encoded_claims}.{signature}", expires_at


def verify_quote(
    quote_token: str,
    *,
    listing_path: str,
    price_microalgos: int,
    asa_id: int | None,
) -> dict:
    """Validate the quote token's signature, freshness, and that its terms
    match the listing currently being purchased. Raises QuoteError on any
    mismatch. Returns the decoded claims on success.
    """
    try:
        encoded_claims, signature = quote_token.split(".", 1)
    except ValueError as exc:
        raise QuoteError("Malformed quote token") from exc

    expected_signature = _sign(encoded_claims)
    if not hmac.compare_digest(signature, expected_signature):
        raise QuoteError("Quote signature invalid")

    padded = encoded_claims + "=" * (-len(encoded_claims) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")))
    except Exception as exc:
        raise QuoteError("Quote payload could not be decoded") from exc

    if int(claims.get("exp", 0)) < int(time.time()):
        raise QuoteError("Quote has expired")
    if claims.get("path") != listing_path:
        raise QuoteError("Quote does not match requested listing")
    if int(claims.get("amt", -1)) != int(price_microalgos):
        raise QuoteError("Quote price does not match the listing's current price")
    if claims.get("to") != settings.ESCROW_WALLET_ADDRESS:
        raise QuoteError("Quote recipient is not the platform escrow wallet")
    if int(claims.get("asa", 0)) != int(asa_id or 0):
        raise QuoteError("Quote asset does not match the listing's asset")

    return claims
