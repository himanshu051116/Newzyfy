"""phase 1 acquisition and event foundation

Revision ID: 0001_phase1
Revises:
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publishers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("slug", sa.String(200), nullable=False, unique=True),
        sa.Column("canonical_domain", sa.String(253), nullable=False, unique=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "discovery_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "publisher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publishers.id"),
            nullable=False,
        ),
        sa.Column("channel_type", sa.String(40), nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("strategy_version", sa.String(100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_poll_at", sa.DateTime(timezone=True)),
        sa.Column("etag", sa.Text()),
        sa.Column("last_modified", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "publisher_id",
            "endpoint_url",
            name="uq_discovery_channels_publisher_endpoint",
        ),
    )
    op.create_index(
        "ix_discovery_channels_next_poll",
        "discovery_channels",
        ["active", "next_poll_at"],
    )
    op.create_table(
        "url_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "publisher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publishers.id"),
            nullable=False,
        ),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("url_fingerprint", sa.LargeBinary(32), nullable=False, unique=True),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("priority_components", postgresql.JSONB(), nullable=False),
        sa.Column("priority_policy_version", sa.String(100), nullable=False),
        sa.Column("next_fetch_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(200)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_url_candidates_frontier",
        "url_candidates",
        ["state", "next_fetch_at", "priority_score"],
    )
    op.create_table(
        "url_discoveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "url_candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("url_candidates.id"),
            nullable=False,
        ),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("discovery_channels.id"),
            nullable=False,
        ),
        sa.Column("discovered_url", sa.Text(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel_position", sa.Integer()),
        sa.Column("payload_hash", sa.LargeBinary(32)),
        sa.UniqueConstraint(
            "url_candidate_id",
            "channel_id",
            name="uq_url_discoveries_candidate_channel",
        ),
    )
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(240), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("lifecycle_status", sa.String(40), nullable=False),
        sa.Column("assignment_status", sa.String(40), nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_material_change_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "publisher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publishers.id"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id"),
            nullable=False,
        ),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("normalized_url_hash", sa.LargeBinary(32), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("language", sa.String(35)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "event_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("articles.id"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id"),
            nullable=False,
        ),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("candidate_features", postgresql.JSONB(), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_event_assignments_article_current",
        "event_assignments",
        ["article_id", "is_current"],
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["published_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("event_assignments")
    op.drop_table("articles")
    op.drop_table("events")
    op.drop_table("url_discoveries")
    op.drop_table("url_candidates")
    op.drop_table("discovery_channels")
    op.drop_table("publishers")

