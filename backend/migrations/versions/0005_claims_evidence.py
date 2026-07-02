"""claim extraction and evidence lineage foundation

Revision ID: 0005_claims
Revises: 0004_articles
Create Date: 2026-06-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_claims"
down_revision: str | None = "0004_articles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "article_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("articles.id"),
            nullable=False,
        ),
        sa.Column(
            "article_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("article_versions.id"),
            nullable=False,
        ),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("claim_sha256", sa.String(64), nullable=False),
        sa.Column("sentence_index", sa.Integer(), nullable=False),
        sa.Column("extractor_version", sa.String(100), nullable=False),
        sa.Column(
            "extraction_features",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "article_version_id",
            "claim_sha256",
            name="article_version_claim",
        ),
    )
    op.create_index(
        "ix_article_claims_article_created",
        "article_claims",
        ["article_id", "created_at"],
    )

    op.create_table(
        "claim_evidence_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("article_claims.id"),
            nullable=False,
        ),
        sa.Column(
            "evidence_article_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("articles.id"),
        ),
        sa.Column(
            "evidence_article_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("article_versions.id"),
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("relationship", sa.String(80), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("similarity_score", sa.Float()),
        sa.Column(
            "independence_score",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "claim_id",
            "evidence_article_version_id",
            "relationship",
            name="claim_evidence_relationship",
        ),
    )
    op.create_index(
        "ix_claim_evidence_links_claim",
        "claim_evidence_links",
        ["claim_id", "retrieved_at"],
    )

    op.create_table(
        "claim_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("article_claims.id"),
            nullable=False,
        ),
        sa.Column("label", sa.String(40), nullable=False),
        sa.Column("confidence_score", sa.Float()),
        sa.Column("methodology_version", sa.String(100), nullable=False),
        sa.Column(
            "confidence_factors",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "reasoning_trace",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_claim_verifications_claim_created",
        "claim_verifications",
        ["claim_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("claim_verifications")
    op.drop_table("claim_evidence_links")
    op.drop_table("article_claims")
