"""channel polling lifecycle

Revision ID: 0003_polling
Revises: 0002_contracts
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_polling"
down_revision: str | None = "0002_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "discovery_channels",
        sa.Column("poll_min_seconds", sa.Integer(), server_default="60", nullable=False),
    )
    op.add_column(
        "discovery_channels",
        sa.Column(
            "poll_max_seconds",
            sa.Integer(),
            server_default="3600",
            nullable=False,
        ),
    )
    op.add_column(
        "discovery_channels",
        sa.Column(
            "current_poll_seconds",
            sa.Integer(),
            server_default="300",
            nullable=False,
        ),
    )
    op.add_column(
        "discovery_channels",
        sa.Column("last_polled_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "discovery_channels",
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "discovery_channels",
        sa.Column("lease_owner", sa.String(200)),
    )
    op.add_column(
        "discovery_channels",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "discovery_channels",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_table(
        "channel_poll_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("discovery_channels.id"),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(200), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("not_modified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("discovered_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("admitted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("observation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("response_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_type", sa.String(200)),
        sa.Column("error_message", sa.Text()),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_index(
        "ix_channel_poll_runs_channel_started",
        "channel_poll_runs",
        ["channel_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("channel_poll_runs")
    op.drop_column("discovery_channels", "consecutive_failures")
    op.drop_column("discovery_channels", "lease_expires_at")
    op.drop_column("discovery_channels", "lease_owner")
    op.drop_column("discovery_channels", "last_success_at")
    op.drop_column("discovery_channels", "last_polled_at")
    op.drop_column("discovery_channels", "current_poll_seconds")
    op.drop_column("discovery_channels", "poll_max_seconds")
    op.drop_column("discovery_channels", "poll_min_seconds")
