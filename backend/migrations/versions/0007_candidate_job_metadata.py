"""url candidate freshness metadata

Revision ID: 0007_candidate_job_metadata
Revises: 0006_sources
Create Date: 2026-06-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_candidate_job_metadata"
down_revision: str | None = "0006_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "url_candidates",
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "url_candidates",
        sa.Column("first_discovered_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        """
        UPDATE url_candidates
        SET first_discovered_at = created_at
        WHERE first_discovered_at IS NULL
        """
    )
    op.create_index(
        "ix_url_candidates_freshness_queue",
        "url_candidates",
        ["state", "published_at", "first_discovered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_url_candidates_freshness_queue", table_name="url_candidates")
    op.drop_column("url_candidates", "first_discovered_at")
    op.drop_column("url_candidates", "published_at")
