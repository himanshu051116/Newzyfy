"""article processing, versioning, and fetch audit records

Revision ID: 0004_articles
Revises: 0003_polling
Create Date: 2026-06-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_articles"
down_revision: str | None = "0003_polling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "url_candidates",
        sa.Column("article_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "url_candidates",
        sa.Column("last_fetch_at", sa.DateTime(timezone=True)),
    )
    op.add_column("url_candidates", sa.Column("last_error", sa.Text()))
    op.create_foreign_key(
        "fk_url_candidates_article_id_articles",
        "url_candidates",
        "articles",
        ["article_id"],
        ["id"],
    )

    op.create_table(
        "article_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("articles.id"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("final_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("byline", sa.Text()),
        sa.Column("language", sa.String(35)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.String(100), nullable=False),
        sa.Column(
            "extraction_warnings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "article_id",
            "version_number",
            name="uq_article_versions_article_number",
        ),
        sa.UniqueConstraint(
            "article_id",
            "content_sha256",
            name="uq_article_versions_content",
        ),
    )
    op.create_index(
        "ix_article_versions_article_created",
        "article_versions",
        ["article_id", "created_at"],
    )

    op.create_table(
        "article_fetch_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("url_candidates.id"),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(200), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("response_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_url", sa.Text()),
        sa.Column("body_sha256", sa.String(64)),
        sa.Column("error_type", sa.String(200)),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index(
        "ix_article_fetch_runs_candidate_started",
        "article_fetch_runs",
        ["candidate_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("article_fetch_runs")
    op.drop_table("article_versions")
    op.drop_constraint(
        "fk_url_candidates_article_id_articles",
        "url_candidates",
        type_="foreignkey",
    )
    op.drop_column("url_candidates", "last_error")
    op.drop_column("url_candidates", "last_fetch_at")
    op.drop_column("url_candidates", "article_id")
