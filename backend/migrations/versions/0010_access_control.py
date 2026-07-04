"""approval-based platform access control

Revision ID: 0010_access_control
Revises: 0009_candidate_url_type
Create Date: 2026-07-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_access_control"
down_revision: str | None = "0009_candidate_url_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("auth_provider", sa.String(80), nullable=False),
        sa.Column("auth_provider_user_id", sa.String(255), nullable=False),
        sa.Column("verified_email", sa.String(320)),
        sa.Column("display_name", sa.String(300)),
        sa.Column("avatar_url", sa.Text()),
        sa.Column("access_status", sa.String(40), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "approved_by_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_users.id"),
        ),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("suspended_at", sa.DateTime(timezone=True)),
        sa.Column("suspension_reason", sa.Text()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revocation_reason", sa.Text()),
        sa.Column("access_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("last_activity_at", sa.DateTime(timezone=True)),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "auth_provider",
            "auth_provider_user_id",
            name="uq_platform_users_provider_subject",
        ),
    )
    op.create_index(
        "ix_platform_users_access_status",
        "platform_users",
        ["access_status", "requested_at"],
    )
    op.create_index("ix_platform_users_email", "platform_users", ["verified_email"])

    op.create_table(
        "access_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_users.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("purpose", sa.String(500)),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "closed_by_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_users.id"),
        ),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_access_requests_status_requested",
        "access_requests",
        ["status", "requested_at"],
    )
    op.create_index(
        "ix_access_requests_user",
        "access_requests",
        ["user_id", "requested_at"],
    )
    op.create_index(
        "uq_access_requests_one_open_per_user",
        "access_requests",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "access_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_users.id"),
        ),
        sa.Column(
            "affected_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_users.id"),
            nullable=False,
        ),
        sa.Column("previous_status", sa.String(40)),
        sa.Column("new_status", sa.String(40)),
        sa.Column("previous_role", sa.String(40)),
        sa.Column("new_role", sa.String(40)),
        sa.Column("reason", sa.Text()),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "request_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_access_audit_affected_created",
        "access_audit_log",
        ["affected_user_id", "created_at"],
    )
    op.create_index(
        "ix_access_audit_actor_created",
        "access_audit_log",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_access_audit_action_created",
        "access_audit_log",
        ["action", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("access_audit_log")
    op.drop_index("uq_access_requests_one_open_per_user", table_name="access_requests")
    op.drop_table("access_requests")
    op.drop_table("platform_users")
