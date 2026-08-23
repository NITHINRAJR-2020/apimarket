"""Provider-admin listing management.

Merges two feature sets:
  * RBAC/ownership (branch "d_merged"): every endpoint requires a PUBLISHER
    (admins always allowed); a publisher only ever sees/edits their own
    listings, enforced at the query level via load_owned_listing.
  * Encrypted upstream credentials + idempotent publish + provider
    verification (branch "2_file_to_merge"): provider auth is encrypted at
    rest before it touches the DB and never echoed back; retried publishes
    with the same idempotency_key resolve to the same row; providers prove
    control of a domain or the pay-out wallet before being marked verified.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import load_owned_listing, require_role
from app.core.crypto import encrypt_credentials
from app.core.database import get_db
from app.models.listing import Listing
from app.models.user import User, UserRole
from app.schemas.listing import (
    AuthConfig,
    ListingCreate,
    ListingOut,
    ListingUpdate,
    VerificationConfirmRequest,
    VerificationInitiateRequest,
    VerificationInitiateResponse,
    VerificationOut,
)
from app.services import verification_service

logger = logging.getLogger("apimarket.routes_listings")
router = APIRouter(prefix="/api/listings", tags=["provider-admin"])

# Listings belong to PUBLISHERs. Admins may also act (admin always allowed).
_require_publisher = require_role(UserRole.PUBLISHER)


def _encrypt_auth(auth: AuthConfig) -> tuple[str, str | None, str | None]:
    """Returns (auth_type, auth_header_name, encrypted_credentials).

    Never logs `auth` -- it may contain a live secret. Only the resulting
    ciphertext (safe to log) and the auth_type/header name (never secret)
    are returned.
    """
    if auth.type == "none":
        return "none", None, None
    if auth.type == "api_key":
        return "api_key", None, encrypt_credentials({"api_key": auth.api_key})
    if auth.type == "bearer":
        return "bearer", None, encrypt_credentials({"bearer_token": auth.bearer_token})
    if auth.type == "custom_header":
        return (
            "custom_header",
            auth.header_name,
            encrypt_credentials({"header_value": auth.header_value}),
        )
    raise HTTPException(status_code=422, detail=f"Unsupported auth.type '{auth.type}'")


@router.post("", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
async def publish_listing(
    payload: ListingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_publisher),
) -> Listing:
    """A publisher registers an API on the marketplace. Ownership is set from
    the authenticated user, never from client input. `pay_to_address` is where
    THEY get paid on escrow release -- it is never handed to buying agents. If
    `auth` is supplied, the credential is encrypted before it ever touches the
    database and is never included in this (or any) response."""
    # Idempotent publish, scoped to this owner so a publisher can't probe for
    # another publisher's listing by guessing an idempotency key.
    if payload.idempotency_key:
        existing = await db.execute(
            select(Listing).where(
                Listing.idempotency_key == payload.idempotency_key,
                Listing.owner_id == user.id,
            )
        )
        existing_listing = existing.scalar_one_or_none()
        if existing_listing is not None:
            return existing_listing

    auth_type, auth_header_name, encrypted_credentials = _encrypt_auth(payload.auth)
    data = payload.model_dump(exclude={"auth"})
    listing = Listing(
        **data,
        owner_id=user.id,
        auth_type=auth_type,
        auth_header_name=auth_header_name,
        encrypted_credentials=encrypted_credentials,
    )
    db.add(listing)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # Could be the path uniqueness constraint, or (rare, concurrent retry)
        # the idempotency_key uniqueness constraint racing us -- in the latter
        # case, resolve to the row the winner created.
        if payload.idempotency_key:
            existing = await db.execute(
                select(Listing).where(
                    Listing.idempotency_key == payload.idempotency_key,
                    Listing.owner_id == user.id,
                )
            )
            existing_listing = existing.scalar_one_or_none()
            if existing_listing is not None:
                return existing_listing
        raise HTTPException(
            status_code=409, detail=f"A listing already exists at path '{payload.path}'"
        ) from exc
    await db.refresh(listing)
    return listing


@router.get("", response_model=list[ListingOut])
async def list_listings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_publisher),
    include_inactive: bool = False,
) -> list[Listing]:
    """Provider-admin view: a publisher sees ONLY their own listings; an admin
    sees all. (The public catalogue is /market/search, which is separate.)"""
    query = select(Listing).order_by(Listing.created_at.desc())
    if user.role != UserRole.ADMIN:
        query = query.where(Listing.owner_id == user.id)
    if not include_inactive:
        query = query.where(Listing.is_active.is_(True))
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{listing_id}", response_model=ListingOut)
async def get_listing(
    listing_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_publisher),
) -> Listing:
    return await load_owned_listing(db, listing_id, user)


@router.patch("/{listing_id}", response_model=ListingOut)
async def update_listing(
    listing_id: uuid.UUID,
    payload: ListingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_publisher),
) -> Listing:
    listing = await load_owned_listing(db, listing_id, user)
    updates = payload.model_dump(exclude_unset=True, exclude={"auth"})
    for field, value in updates.items():
        setattr(listing, field, value)
    if payload.auth is not None:
        auth_type, auth_header_name, encrypted_credentials = _encrypt_auth(payload.auth)
        listing.auth_type = auth_type
        listing.auth_header_name = auth_header_name
        listing.encrypted_credentials = encrypted_credentials
    await db.commit()
    await db.refresh(listing)
    return listing


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_listing(
    listing_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_publisher),
) -> None:
    listing = await load_owned_listing(db, listing_id, user)
    listing.is_active = False
    await db.commit()


# --- Provider verification (Feature 4) --------------------------------------
# Ownership-guarded: a publisher can only (un)verify their own listing; an
# admin may act on any. load_owned_listing returns 404 for anything else.


@router.post("/{listing_id}/verify/initiate", response_model=VerificationInitiateResponse)
async def initiate_verification(
    listing_id: uuid.UUID,
    payload: VerificationInitiateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_publisher),
) -> VerificationInitiateResponse:
    listing = await load_owned_listing(db, listing_id, user)
    if payload.method == "domain" and not payload.domain:
        raise HTTPException(status_code=422, detail="domain is required for method 'domain'")

    token = verification_service.new_verification_token()
    listing.verification_status = "verification_pending"
    listing.verification_method = payload.method
    listing.verification_domain = payload.domain
    listing.verification_token = token
    listing.verified_at = None
    await db.commit()

    instructions = (
        verification_service.domain_instructions(payload.domain, token)
        if payload.method == "domain"
        else verification_service.wallet_instructions(token)
    )
    return VerificationInitiateResponse(
        verification_status=listing.verification_status,
        verification_method=listing.verification_method,
        instructions=instructions,
        verification_token=token,
    )


@router.post("/{listing_id}/verify/confirm", response_model=VerificationOut)
async def confirm_verification(
    listing_id: uuid.UUID,
    payload: VerificationConfirmRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_publisher),
) -> Listing:
    listing = await load_owned_listing(db, listing_id, user)
    if listing.verification_status != "verification_pending" or not listing.verification_token:
        raise HTTPException(status_code=409, detail="No verification is pending for this listing")

    try:
        if listing.verification_method == "domain":
            ok = await verification_service.check_domain_verification(
                listing.verification_domain, listing.verification_token
            )
        elif listing.verification_method == "wallet":
            if not payload.signed_message:
                raise HTTPException(status_code=422, detail="signed_message is required for wallet verification")
            ok = verification_service.check_wallet_verification(
                address=listing.pay_to_address,
                token=listing.verification_token,
                signed_message_b64=payload.signed_message,
            )
        else:
            raise HTTPException(status_code=409, detail="Unknown verification method")
    except verification_service.VerificationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not ok:
        raise HTTPException(status_code=422, detail="Verification proof did not match; still pending")

    listing.verification_status = "verified"
    listing.verified_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(listing)
    return listing
