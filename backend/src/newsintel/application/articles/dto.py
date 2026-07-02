from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ArticleVersionView(BaseModel):
    id: UUID
    version_number: int
    source_url: str
    final_url: str
    title: str
    byline: str | None
    language: str | None
    published_at: datetime | None
    retrieved_at: datetime
    content_sha256: str
    extraction_method: str
    extraction_warnings: list[str]
    extraction_quality_score: float | None
    raw_artifact_uri: str | None
    word_count: int
    text_content: str
    created_at: datetime


class ArticleSummaryView(BaseModel):
    id: UUID
    event_id: UUID
    publisher_id: UUID
    canonical_url: str
    title: str
    language: str | None
    published_at: datetime | None
    first_observed_at: datetime
    latest_version_id: UUID | None
    latest_version_number: int | None
    latest_extraction_method: str | None
    latest_extraction_warnings: list[str]
    latest_extraction_quality_score: float | None
    word_count: int | None


class ArticleDetailView(BaseModel):
    id: UUID
    event_id: UUID
    publisher_id: UUID
    canonical_url: str
    title: str
    language: str | None
    published_at: datetime | None
    first_observed_at: datetime
    created_at: datetime
    updated_at: datetime
    latest_version: ArticleVersionView | None


class EventDetailView(BaseModel):
    id: UUID
    slug: str
    title: str
    lifecycle_status: str
    assignment_status: str
    first_detected_at: datetime
    last_material_change_at: datetime
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime
    articles: list[ArticleSummaryView]


class ClaimEvidenceLinkView(BaseModel):
    id: UUID
    source_url: str
    source_type: str
    relationship: str
    retrieved_at: datetime
    similarity_score: float | None
    independence_score: float
    metadata: dict[str, object]


class ClaimVerificationView(BaseModel):
    id: UUID
    label: str
    confidence_score: float | None
    methodology_version: str
    confidence_factors: dict[str, object]
    reasoning_trace: dict[str, object]
    created_at: datetime


class ArticleClaimView(BaseModel):
    id: UUID
    article_id: UUID
    article_version_id: UUID
    claim_text: str
    claim_sha256: str
    sentence_index: int
    extractor_version: str
    extraction_features: dict[str, object]
    created_at: datetime
    evidence_links: list[ClaimEvidenceLinkView]
    latest_verification: ClaimVerificationView | None
