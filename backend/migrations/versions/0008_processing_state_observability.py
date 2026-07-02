"""article processing state and observability fields

Revision ID: 0008_processing_state
Revises: 0007_candidate_job_metadata
Create Date: 2026-07-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_processing_state"
down_revision: str | None = "0007_candidate_job_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "url_candidates",
        sa.Column(
            "processing_stage",
            sa.String(60),
            nullable=False,
            server_default="queued",
        ),
    )
    op.add_column("url_candidates", sa.Column("current_worker", sa.String(200)))
    op.add_column("url_candidates", sa.Column("content_type", sa.String(160)))
    op.add_column("url_candidates", sa.Column("last_failure_code", sa.String(160)))
    op.add_column("url_candidates", sa.Column("last_failure_message", sa.Text()))
    op.add_column(
        "url_candidates",
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "url_candidates",
        sa.Column("processing_completed_at", sa.DateTime(timezone=True)),
    )
    op.add_column("url_candidates", sa.Column("processing_duration_ms", sa.Integer()))
    op.add_column(
        "url_candidates",
        sa.Column(
            "stage_timestamps",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE url_candidates
        SET processing_stage = CASE
            WHEN state = 'processed' THEN 'completed'
            WHEN state = 'failed' THEN 'permanent_failure'
            WHEN state = 'rejected' THEN 'rejected'
            WHEN state = 'retry' THEN 'retryable_failure'
            WHEN state = 'leased' THEN 'leased'
            ELSE 'queued'
        END
        """
    )
    op.create_index(
        "ix_url_candidates_processing_stage",
        "url_candidates",
        ["processing_stage", "next_fetch_at"],
    )
    op.create_index(
        "ix_url_candidates_failure",
        "url_candidates",
        ["publisher_id", "processing_stage", "last_failure_code"],
    )
    op.create_index(
        "ix_url_candidates_lease_expiry",
        "url_candidates",
        ["state", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_url_candidates_lease_expiry", table_name="url_candidates")
    op.drop_index("ix_url_candidates_failure", table_name="url_candidates")
    op.drop_index("ix_url_candidates_processing_stage", table_name="url_candidates")
    op.drop_column("url_candidates", "stage_timestamps")
    op.drop_column("url_candidates", "processing_duration_ms")
    op.drop_column("url_candidates", "processing_completed_at")
    op.drop_column("url_candidates", "processing_started_at")
    op.drop_column("url_candidates", "last_failure_message")
    op.drop_column("url_candidates", "last_failure_code")
    op.drop_column("url_candidates", "content_type")
    op.drop_column("url_candidates", "current_worker")
    op.drop_column("url_candidates", "processing_stage")
