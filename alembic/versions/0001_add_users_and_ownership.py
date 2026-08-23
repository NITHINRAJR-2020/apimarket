"""add users table and resource ownership

Adds the RBAC layer on top of an existing PayperQuery database WITHOUT
touching existing rows:
  * creates the `users` table (with a `user_role` enum)
  * adds a nullable `owner_id` FK to `listings` (the publisher)
  * adds a nullable `owner_id` FK to `agents` (the operating user)

`owner_id` is nullable so pre-existing listings/agents survive the upgrade
unowned; assign them to an admin afterwards (see README) or let admins manage
them. Nothing is dropped or wiped.

Revision ID: 0001_add_users_and_ownership
Revises:
Create Date: 2026-08-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_add_users_and_ownership"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role = sa.Enum("admin", "publisher", "user", name="user_role")


def upgrade() -> None:
    bind = op.get_bind()
    # Create the enum explicitly on Postgres; SQLite has no native enum.
    if bind.dialect.name == "postgresql":
        user_role.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # Ownership FKs — nullable so existing rows are preserved.
    with op.batch_alter_table("listings") as batch:
        batch.add_column(sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True))
        batch.create_index("ix_listings_owner_id", ["owner_id"])
        batch.create_foreign_key(
            "fk_listings_owner_id_users", "users", ["owner_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("agents") as batch:
        batch.add_column(sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True))
        batch.create_index("ix_agents_owner_id", ["owner_id"])
        batch.create_foreign_key(
            "fk_agents_owner_id_users", "users", ["owner_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("agents") as batch:
        batch.drop_constraint("fk_agents_owner_id_users", type_="foreignkey")
        batch.drop_index("ix_agents_owner_id")
        batch.drop_column("owner_id")

    with op.batch_alter_table("listings") as batch:
        batch.drop_constraint("fk_listings_owner_id_users", type_="foreignkey")
        batch.drop_index("ix_listings_owner_id")
        batch.drop_column("owner_id")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        user_role.drop(bind, checkfirst=True)
