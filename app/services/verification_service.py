"""Provider verification (Feature 4).

Two verification methods, both proving actual control rather than just
trusting a claimed name:

  * domain -- the provider must publish a token at
    https://{domain}/.well-known/apimarket that we fetch and check.
  * wallet -- the provider must sign the issued verification_token with
    the private key of the listing's own `pay_to_address`, proving they
    control that Algorand account (the same one escrow will pay out to).

This intentionally does not claim verification just because a domain
string was typed into a form -- confirm_verification() always re-checks
the actual proof before flipping verification_status to "verified".
"""

import base64
import logging
import secrets

import httpx
from algosdk import encoding
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger("apimarket.verification_service")


class VerificationError(Exception):
    pass


def new_verification_token() -> str:
    return secrets.token_hex(16)


def domain_instructions(domain: str, token: str) -> str:
    return (
        f"Publish a file at https://{domain}/.well-known/apimarket containing exactly: {token}"
    )


def wallet_instructions(token: str) -> str:
    return (
        f"Sign the exact UTF-8 bytes of this token with the private key for the listing's "
        f"pay_to_address and submit the base64 signature: {token}"
    )


async def check_domain_verification(domain: str, expected_token: str) -> bool:
    url = f"https://{domain}/.well-known/apimarket"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url)
    except httpx.RequestError as exc:
        raise VerificationError(f"Could not reach {url}: {exc}") from exc

    if resp.status_code != 200:
        raise VerificationError(f"{url} returned HTTP {resp.status_code}")

    return resp.text.strip() == expected_token.strip()


def check_wallet_verification(*, address: str, token: str, signed_message_b64: str) -> bool:
    try:
        public_key_bytes = encoding.decode_address(address)
    except Exception as exc:
        raise VerificationError(f"Invalid Algorand address: {exc}") from exc

    try:
        signature = base64.b64decode(signed_message_b64)
    except Exception as exc:
        raise VerificationError("signed_message must be base64-encoded") from exc

    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, token.encode("utf-8"))
    except InvalidSignature:
        return False
    except Exception as exc:
        raise VerificationError(f"Could not verify signature: {exc}") from exc
    return True
