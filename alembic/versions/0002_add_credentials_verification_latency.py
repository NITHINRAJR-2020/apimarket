"""add upstream-credential, verification, latency and idempotency columns to listings

Second half of the two-branch merge. The RBAC branch (0001) added users and
resource ownership; this revision adds the columns the other branch introduced
on `listings`, WITHOUT touching existing rows:

  * latency_samples        -- JSON ring buffer powering p50/p95 reputation
  * auth_type / auth_header_name / encrypted_credentials
                           -- Fernet-encrypted upstream provider credentials
  * verification_status / verification_method / verification_domain /
    verification_token / verified_at
                           -- provider domain/wallet verification
  * idempotency_key        -- idempotent listing publish (unique, nullable)

All added columns are nullable or carry a server_default, so pre-existing
listings survive untouched (auth_type -> 'none', verification_status ->
'unverified').

Revision ID: 0002_add_credentials_verification_latency
Revises: 0001_add_users_and_ownership
Create Date: 2026-08-22
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002_add_credentials_verification_latency"
down_revision: Union[str, None] = "0001_add_users_and_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("listings") as batch:
        batch.add_column(sa.Column("latency_samples", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("auth_type", sa.String(length=20), nullable=False, server_default="none")
        )
        batch.add_column(sa.Column("auth_header_name", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("encrypted_credentials", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "verification_status",
                sa.String(length=20),
                nullable=False,
                server_default="unverified",
            )
        )
        batch.add_column(sa.Column("verification_method", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("verification_domain", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("verification_token", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("idempotency_key", sa.String(length=200), nullable=True))
        batch.create_index("ix_listings_verification_status", ["verification_status"])
        batch.create_unique_constraint("uq_listings_idempotency_key", ["idempotency_key"])


def downgrade() -> None:
    with op.batch_alter_table("listings") as batch:
        batch.drop_constraint("uq_listings_idempotency_key", type_="unique")
        batch.drop_index("ix_listings_verification_status")
        batch.drop_column("idempotency_key")
        batch.drop_column("verified_at")
        batch.drop_column("verification_token")
        batch.drop_column("verification_domain")
        batch.drop_column("verification_method")
        batch.drop_column("verification_status")
        batch.drop_column("encrypted_credentials")
        batch.drop_column("auth_header_name")
        batch.drop_column("auth_type")
        batch.drop_column("latency_samples")
