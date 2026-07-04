"""store URL candidate content type classification

Revision ID: 0009_candidate_url_type
Revises: 0008_processing_state
Create Date: 2026-07-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_candidate_url_type"
down_revision: str | None = "0008_processing_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("url_candidates", sa.Column("url_type", sa.String(60)))
    op.execute(
        """
        UPDATE url_candidates
        SET url_type = 'standard_article'
        WHERE url_type IS NULL
        """
    )
    op.create_index(
        "ix_url_candidates_url_type_state",
        "url_candidates",
        ["url_type", "state", "next_fetch_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_url_candidates_url_type_state", table_name="url_candidates")
    op.drop_column("url_candidates", "url_type")
