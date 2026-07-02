"""homepage source discovery and fetch jobs

Revision ID: 0006_sources
Revises: 0005_claims
Create Date: 2026-06-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_sources"
down_revision: str | None = "0005_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("publishers", sa.Column("homepage_url", sa.Text()))
    op.add_column(
        "publishers",
        sa.Column(
            "fetch_frequency",
            sa.String(40),
            nullable=False,
            server_default="hourly",
        ),
    )
    op.add_column(
        "publishers",
        sa.Column(
            "discovery_status",
            sa.String(40),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("publishers", sa.Column("discovery_message", sa.Text()))
    op.add_column(
        "publishers",
        sa.Column("last_fetched_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "fetch_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "publisher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publishers.id"),
        ),
        sa.Column("job_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("publishers_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "publishers_processed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("urls_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("articles_queued", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("articles_extracted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_articles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text()),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_fetch_jobs_status_created",
        "fetch_jobs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_fetch_jobs_publisher_created",
        "fetch_jobs",
        ["publisher_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("fetch_jobs")
    op.drop_column("publishers", "last_fetched_at")
    op.drop_column("publishers", "discovery_message")
    op.drop_column("publishers", "discovery_status")
    op.drop_column("publishers", "fetch_frequency")
    op.drop_column("publishers", "homepage_url")
