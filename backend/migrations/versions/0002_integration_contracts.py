"""integration contracts and consumer inbox

Revision ID: 0002_contracts
Revises: 0001_phase1
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_contracts"
down_revision: str | None = "0001_phase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_outbox_events_unpublished", table_name="outbox_events")
    op.alter_column(
        "outbox_events",
        "created_at",
        new_column_name="occurred_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.add_column("outbox_events", sa.Column("producer", sa.String(200)))
    op.add_column(
        "outbox_events",
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "outbox_events",
        sa.Column("causation_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column("outbox_events", sa.Column("traceparent", sa.String(255)))
    op.add_column("outbox_events", sa.Column("idempotency_key", sa.String(500)))
    op.execute("UPDATE outbox_events SET producer = 'legacy'")
    op.execute("UPDATE outbox_events SET idempotency_key = 'legacy:' || id::text")
    op.alter_column("outbox_events", "producer", nullable=False)
    op.alter_column("outbox_events", "idempotency_key", nullable=False)
    op.create_unique_constraint(
        "uq_outbox_events_idempotency_key",
        "outbox_events",
        ["idempotency_key"],
    )
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["published_at", "occurred_at"],
    )
    op.create_table(
        "consumer_inbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_name", sa.String(200), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handler_version", sa.String(100), nullable=False),
        sa.UniqueConstraint(
            "consumer_name",
            "event_id",
            name="uq_consumer_inbox_consumer_event",
        ),
    )


def downgrade() -> None:
    op.drop_table("consumer_inbox")
    op.drop_index("ix_outbox_events_unpublished", table_name="outbox_events")
    op.drop_constraint(
        "uq_outbox_events_idempotency_key",
        "outbox_events",
        type_="unique",
    )
    op.drop_column("outbox_events", "idempotency_key")
    op.drop_column("outbox_events", "traceparent")
    op.drop_column("outbox_events", "causation_id")
    op.drop_column("outbox_events", "correlation_id")
    op.drop_column("outbox_events", "producer")
    op.alter_column(
        "outbox_events",
        "occurred_at",
        new_column_name="created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["published_at", "created_at"],
    )
