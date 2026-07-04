from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from newsintel.core.ids import uuid7
from newsintel.infrastructure.db.base import Base


class PublisherModel(Base):
    __tablename__ = "publishers"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(300))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    canonical_domain: Mapped[str] = mapped_column(String(253), unique=True)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    fetch_frequency: Mapped[str] = mapped_column(String(40), default="hourly")
    discovery_status: Mapped[str] = mapped_column(String(40), default="pending")
    discovery_message: Mapped[str | None] = mapped_column(Text)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DiscoveryChannelModel(Base):
    __tablename__ = "discovery_channels"
    __table_args__ = (
        UniqueConstraint("publisher_id", "endpoint_url", name="publisher_endpoint"),
        Index("ix_discovery_channels_next_poll", "active", "next_poll_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    channel_type: Mapped[str] = mapped_column(String(40))
    endpoint_url: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    strategy_version: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    poll_min_seconds: Mapped[int] = mapped_column(Integer, default=60)
    poll_max_seconds: Mapped[int] = mapped_column(Integer, default=3_600)
    current_poll_seconds: Mapped[int] = mapped_column(Integer, default=300)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UrlCandidateModel(Base):
    __tablename__ = "url_candidates"
    __table_args__ = (
        Index("ix_url_candidates_frontier", "state", "next_fetch_at", "priority_score"),
        Index(
            "ix_url_candidates_freshness_queue",
            "state",
            "published_at",
            "first_discovered_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    normalized_url: Mapped[str] = mapped_column(Text)
    url_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    state: Mapped[str] = mapped_column(String(40))
    processing_stage: Mapped[str] = mapped_column(String(60), default="queued")
    priority_score: Mapped[float] = mapped_column(Float)
    priority_components: Mapped[dict[str, float]] = mapped_column(JSONB)
    priority_policy_version: Mapped[str] = mapped_column(String(100))
    next_fetch_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    url_type: Mapped[str | None] = mapped_column(String(60))
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_worker: Mapped[str | None] = mapped_column(String(200))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    article_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_failure_code: Mapped[str | None] = mapped_column(String(160))
    last_failure_message: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(160))
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_duration_ms: Mapped[int | None] = mapped_column(Integer)
    stage_timestamps: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UrlDiscoveryModel(Base):
    __tablename__ = "url_discoveries"
    __table_args__ = (
        UniqueConstraint("url_candidate_id", "channel_id", name="candidate_channel"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    url_candidate_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("url_candidates.id"),
    )
    channel_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("discovery_channels.id"),
    )
    discovered_url: Mapped[str] = mapped_column(Text)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channel_position: Mapped[int | None] = mapped_column(Integer)
    payload_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))


class EventModel(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    slug: Mapped[str] = mapped_column(String(240), unique=True)
    title: Mapped[str] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(String(40))
    assignment_status: Mapped[str] = mapped_column(String(40))
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_material_change_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleModel(Base):
    __tablename__ = "articles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    canonical_url: Mapped[str] = mapped_column(Text)
    normalized_url_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    title: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(35))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleVersionModel(Base):
    __tablename__ = "article_versions"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "version_number",
            name="uq_article_versions_article_number",
        ),
        UniqueConstraint(
            "article_id",
            "content_sha256",
            name="uq_article_versions_content",
        ),
        Index("ix_article_versions_article_created", "article_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    byline: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(35))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_sha256: Mapped[str] = mapped_column(String(64))
    text_content: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(100))
    extraction_warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleClaimModel(Base):
    __tablename__ = "article_claims"
    __table_args__ = (
        UniqueConstraint("article_version_id", "claim_sha256", name="article_version_claim"),
        Index("ix_article_claims_article_created", "article_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    article_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("article_versions.id"),
    )
    claim_text: Mapped[str] = mapped_column(Text)
    claim_sha256: Mapped[str] = mapped_column(String(64))
    sentence_index: Mapped[int] = mapped_column(Integer)
    extractor_version: Mapped[str] = mapped_column(String(100))
    extraction_features: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClaimEvidenceLinkModel(Base):
    __tablename__ = "claim_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "claim_id",
            "evidence_article_version_id",
            "relationship",
            name="claim_evidence_relationship",
        ),
        Index("ix_claim_evidence_links_claim", "claim_id", "retrieved_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    evidence_article_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("articles.id"),
    )
    evidence_article_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("article_versions.id"),
    )
    source_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(80))
    relationship: Mapped[str] = mapped_column(String(80))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    similarity_score: Mapped[float | None] = mapped_column(Float)
    independence_score: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClaimVerificationModel(Base):
    __tablename__ = "claim_verifications"
    __table_args__ = (
        Index("ix_claim_verifications_claim_created", "claim_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    label: Mapped[str] = mapped_column(String(40))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    methodology_version: Mapped[str] = mapped_column(String(100))
    confidence_factors: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    reasoning_trace: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleFetchRunModel(Base):
    __tablename__ = "article_fetch_runs"
    __table_args__ = (
        Index("ix_article_fetch_runs_candidate_started", "candidate_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    candidate_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("url_candidates.id"),
    )
    worker_id: Mapped[str] = mapped_column(String(200))
    trace_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_bytes: Mapped[int] = mapped_column(Integer, default=0)
    final_url: Mapped[str | None] = mapped_column(Text)
    body_sha256: Mapped[str | None] = mapped_column(String(64))
    error_type: Mapped[str | None] = mapped_column(String(200))
    error_message: Mapped[str | None] = mapped_column(Text)


class EventAssignmentModel(Base):
    __tablename__ = "event_assignments"
    __table_args__ = (
        Index("ix_event_assignments_article_current", "article_id", "is_current"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    state: Mapped[str] = mapped_column(String(40))
    score: Mapped[float | None] = mapped_column(Float)
    candidate_features: Mapped[dict[str, float]] = mapped_column(JSONB)
    policy_version: Mapped[str] = mapped_column(String(100))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_unpublished", "published_at", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    event_type: Mapped[str] = mapped_column(String(200))
    event_version: Mapped[int] = mapped_column(Integer, default=1)
    aggregate_type: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    producer: Mapped[str] = mapped_column(String(200))
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    causation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    traceparent: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(500), unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsumerInboxModel(Base):
    __tablename__ = "consumer_inbox"
    __table_args__ = (
        UniqueConstraint("consumer_name", "event_id", name="consumer_event"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    consumer_name: Mapped[str] = mapped_column(String(200))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(200))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handler_version: Mapped[str] = mapped_column(String(100))


class ChannelPollRunModel(Base):
    __tablename__ = "channel_poll_runs"
    __table_args__ = (
        Index("ix_channel_poll_runs_channel_started", "channel_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    channel_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("discovery_channels.id"),
    )
    worker_id: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    not_modified: Mapped[bool] = mapped_column(Boolean, default=False)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    admitted_count: Mapped[int] = mapped_column(Integer, default=0)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    response_bytes: Mapped[int] = mapped_column(Integer, default=0)
    error_type: Mapped[str | None] = mapped_column(String(200))
    error_message: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))


class FetchJobModel(Base):
    __tablename__ = "fetch_jobs"
    __table_args__ = (
        Index("ix_fetch_jobs_status_created", "status", "created_at"),
        Index("ix_fetch_jobs_publisher_created", "publisher_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    job_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))
    publishers_total: Mapped[int] = mapped_column(Integer, default=0)
    publishers_processed: Mapped[int] = mapped_column(Integer, default=0)
    urls_discovered: Mapped[int] = mapped_column(Integer, default=0)
    articles_queued: Mapped[int] = mapped_column(Integer, default=0)
    articles_extracted: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0)
    failed_articles: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlatformUserModel(Base):
    __tablename__ = "platform_users"
    __table_args__ = (
        UniqueConstraint(
            "auth_provider",
            "auth_provider_user_id",
            name="uq_platform_users_provider_subject",
        ),
        Index("ix_platform_users_access_status", "access_status", "requested_at"),
        Index("ix_platform_users_email", "verified_email"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    auth_provider: Mapped[str] = mapped_column(String(80))
    auth_provider_user_id: Mapped[str] = mapped_column(String(255))
    verified_email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(300))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    access_status: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(40))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_admin_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_users.id"),
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccessRequestModel(Base):
    __tablename__ = "access_requests"
    __table_args__ = (
        Index("ix_access_requests_status_requested", "status", "requested_at"),
        Index("ix_access_requests_user", "user_id", "requested_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_users.id"),
    )
    status: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str | None] = mapped_column(String(500))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_admin_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_users.id"),
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccessAuditLogModel(Base):
    __tablename__ = "access_audit_log"
    __table_args__ = (
        Index("ix_access_audit_affected_created", "affected_user_id", "created_at"),
        Index("ix_access_audit_actor_created", "actor_user_id", "created_at"),
        Index("ix_access_audit_action_created", "action", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    action: Mapped[str] = mapped_column(String(80))
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_users.id"),
    )
    affected_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_users.id"),
    )
    previous_status: Mapped[str | None] = mapped_column(String(40))
    new_status: Mapped[str | None] = mapped_column(String(40))
    previous_role: Mapped[str | None] = mapped_column(String(40))
    new_role: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    request_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
