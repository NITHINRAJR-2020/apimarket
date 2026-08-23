"""Minimal at-rest encryption for provider upstream-API credentials.

The repo had no encryption infrastructure, so this is a small, single-purpose
abstraction rather than scattering encryption logic across the listings
routes/service: `encrypt_credentials` / `decrypt_credentials` are the only
two functions anything else should call.

Uses Fernet (AES-128-CBC + HMAC, from the `cryptography` package) with a key
derived from `settings.SECRET_KEY` via PBKDF2, so no extra required env var
is introduced -- operators who already set SECRET_KEY get encryption at rest
for free. Rotate SECRET_KEY -> old encrypted credentials become unreadable,
same trade-off as ESCROW_WALLET_MNEMONIC/X402_QUOTE_SECRET already have.
"""

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

settings = get_settings()

_SALT = b"apimarket-provider-credentials-v1"


class CredentialCryptoError(Exception):
    pass


def _fernet() -> Fernet:
    derived = hashlib.pbkdf2_hmac("sha256", settings.SECRET_KEY.encode("utf-8"), _SALT, 390_000, dklen=32)
    key = base64.urlsafe_b64encode(derived)
    return Fernet(key)


def encrypt_credentials(credentials: dict) -> str:
    """Serialize + encrypt a credentials dict for storage in
    Listing.encrypted_credentials. Never call this with anything that
    should end up in a log line -- the ciphertext is safe to log, the
    input never is.
    """
    raw = json.dumps(credentials, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _fernet().encrypt(raw).decode("utf-8")


def decrypt_credentials(ciphertext: str) -> dict:
    """Inverse of encrypt_credentials. Only ever called internally by the
    proxy/purchase service when constructing the upstream request --
    the result must never be attached to a response sent to an agent.
    """
    try:
        raw = _fernet().decrypt(ciphertext.encode("utf-8"))
    except InvalidToken as exc:
        raise CredentialCryptoError("Stored credentials could not be decrypted") from exc
    return json.loads(raw.decode("utf-8"))
