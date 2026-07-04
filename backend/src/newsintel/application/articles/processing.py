import asyncio
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError

from newsintel.adapters.artifacts.local_store import RawFetchArtifact
from newsintel.adapters.extractors.article_html import ExtractedArticle
from newsintel.adapters.http.safe_fetcher import FetchRequest, FetchResult
from newsintel.core.ids import uuid7
from newsintel.domain.acquisition.article_filter import (
    DEFAULT_RECENT_WINDOW_HOURS,
    should_admit_article_url,
)

logger = structlog.get_logger(__name__)


class UrlCandidateState(StrEnum):
    READY = "ready"
    LEASED = "leased"
    RETRY = "retry"
    PROCESSED = "processed"
    FAILED = "failed"
    REJECTED = "rejected"


class ArticleProcessingStage(StrEnum):
    DISCOVERED = "discovered"
    ADMITTED = "admitted"
    QUEUED = "queued"
    LEASED = "leased"
    FETCHING = "fetching"
    FETCHED = "fetched"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    PARTIAL = "partial"
    VALIDATED = "validated"
    PERSISTING = "persisting"
    PERSISTED = "persisted"
    ENRICHING = "enriching"
    COMPLETED = "completed"
    REJECTED = "rejected"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"


class ArticleFetchRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class ArticleProcessingError(RuntimeError):
    pass


class NonRetryableArticleProcessingError(ArticleProcessingError):
    pass


class InsufficientArticleContentError(ArticleProcessingError):
    pass


class ArticleJobRejectedError(ArticleProcessingError):
    pass


class ArticleAccessBlockedError(NonRetryableArticleProcessingError):
    pass


class ExtractionQualityError(NonRetryableArticleProcessingError):
    pass


class ArticleNotFoundError(NonRetryableArticleProcessingError):
    pass


_NON_RETRYABLE_HTTP_STATUSES = {401, 402, 403, 451}
_PERMANENT_HTTP_STATUSES = {400, 404, 410}
_FATAL_EXTRACTION_WARNINGS = {
    "low_extraction_quality",
    "missing_text_content",
    "possible_paywall_or_partial_content",
    "possible_subscription_boilerplate",
}


@dataclass(frozen=True, slots=True)
class LeasedUrlCandidate:
    id: UUID
    publisher_id: UUID
    normalized_url: str
    attempt_count: int
    published_at: datetime | None = None
    first_discovered_at: datetime | None = None
    url_type: str | None = None


@dataclass(frozen=True, slots=True)
class ArticleFetchRun:
    id: UUID
    candidate_id: UUID
    worker_id: str
    trace_id: UUID
    started_at: datetime


@dataclass(frozen=True, slots=True)
class ArticleProcessingResult:
    candidate_id: UUID
    article_id: UUID
    event_id: UUID
    version_id: UUID | None
    created_article: bool
    created_event: bool
    created_version: bool
    claim_count: int = 0


class ArticleProcessingRepository(Protocol):
    async def lease_due_candidates(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> Sequence[LeasedUrlCandidate]: ...

    async def start_fetch(
        self,
        *,
        candidate_id: UUID,
        worker_id: str,
        trace_id: UUID,
        started_at: datetime,
    ) -> ArticleFetchRun: ...

    async def update_processing_stage(
        self,
        *,
        candidate: LeasedUrlCandidate,
        stage: ArticleProcessingStage,
        occurred_at: datetime,
        worker_id: str | None = None,
        run_id: UUID | None = None,
        content_type: str | None = None,
        failure_code: str | None = None,
        failure_message: str | None = None,
        processing_duration_ms: int | None = None,
    ) -> None: ...

    async def complete_success(
        self,
        *,
        candidate: LeasedUrlCandidate,
        run: ArticleFetchRun,
        fetched: FetchResult,
        extracted: ExtractedArticle,
        raw_artifact: RawFetchArtifact | None,
        completed_at: datetime,
    ) -> ArticleProcessingResult: ...

    async def complete_failure(
        self,
        *,
        candidate: LeasedUrlCandidate,
        run: ArticleFetchRun,
        completed_at: datetime,
        error_type: str,
        error_message: str,
        retry_at: datetime | None,
        terminal: bool,
    ) -> None: ...

    async def reject_before_fetch(
        self,
        *,
        candidate: LeasedUrlCandidate,
        worker_id: str,
        trace_id: UUID,
        rejected_at: datetime,
        reason: str,
        message: str,
    ) -> None: ...


class Fetcher(Protocol):
    async def fetch(self, request: FetchRequest) -> FetchResult: ...


class RawArtifactStore(Protocol):
    async def save_raw_html(
        self,
        *,
        candidate_id: UUID,
        body: bytes,
        body_sha256: str,
        retrieved_at: datetime,
    ) -> RawFetchArtifact: ...


class ArticleExtractor(Protocol):
    def __call__(self, html: bytes, *, base_url: str) -> ExtractedArticle: ...


def retry_at_for_attempt(
    attempt_count: int,
    *,
    base_seconds: int,
    max_seconds: int,
    jitter_ratio: float = 0.0,
    now: datetime | None = None,
) -> datetime:
    if attempt_count < 1:
        raise ValueError("attempt_count must be positive")
    current_time = now or datetime.now(UTC)
    delay = min(max_seconds, base_seconds * (2 ** min(attempt_count - 1, 10)))
    if jitter_ratio > 0:
        jitter = delay * min(max(jitter_ratio, 0.0), 1.0)
        delay = max(1.0, delay + random.uniform(-jitter, jitter))  # noqa: S311
    return current_time + timedelta(seconds=delay)


class ArticleProcessor:
    def __init__(
        self,
        *,
        repository: ArticleProcessingRepository,
        fetcher: Fetcher,
        extractor: ArticleExtractor,
        raw_artifact_store: RawArtifactStore | None = None,
        max_attempts: int = 3,
        retry_base_seconds: int = 120,
        retry_max_seconds: int = 3_600,
        retry_jitter_ratio: float = 0.15,
        recent_article_window_hours: int = DEFAULT_RECENT_WINDOW_HOURS,
    ) -> None:
        self._repository = repository
        self._fetcher = fetcher
        self._extractor = extractor
        self._raw_artifact_store = raw_artifact_store
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds
        self._retry_max_seconds = retry_max_seconds
        self._retry_jitter_ratio = retry_jitter_ratio
        self._recent_article_window_hours = recent_article_window_hours

    async def process(
        self,
        candidate: LeasedUrlCandidate,
        *,
        worker_id: str,
    ) -> ArticleProcessingResult:
        started_at = datetime.now(UTC)
        trace_id = uuid7()
        context = _candidate_log_context(
            candidate,
            worker_id=worker_id,
            correlation_id=trace_id,
            started_at=started_at,
        )
        logger.info(
            "article_job_claimed",
            **context,
        )
        rejection = should_admit_article_url(
            candidate.normalized_url,
            published_at=candidate.published_at,
            observed_at=started_at,
            recent_window_hours=self._recent_article_window_hours,
            require_publication_date=False,
        )
        if not rejection.accepted:
            reason = rejection.reason.value if rejection.reason else "prefetch_rejected"
            message = f"queued URL rejected before HTTP fetch: {reason}"
            await self._repository.reject_before_fetch(
                candidate=candidate,
                worker_id=worker_id,
                trace_id=trace_id,
                rejected_at=started_at,
                reason=reason,
                message=message,
            )
            logger.info(
                "old_job_rejected",
                **context,
                reason=reason,
                classified_url_type=rejection.url_type.value,
                url_type_confidence=rejection.confidence,
                recent_article_window_hours=self._recent_article_window_hours,
            )
            raise ArticleJobRejectedError(message)

        run = await self._repository.start_fetch(
            candidate_id=candidate.id,
            worker_id=worker_id,
            trace_id=trace_id,
            started_at=started_at,
        )
        context = {**context, "fetch_run_id": str(run.id)}
        try:
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.FETCHING,
                occurred_at=datetime.now(UTC),
                worker_id=worker_id,
                run_id=run.id,
            )
            logger.info("page_fetch_started", **context)
            fetched = await self._fetcher.fetch(FetchRequest(url=candidate.normalized_url))
            content_type = fetched.headers.get("content-type")
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.FETCHED,
                occurred_at=fetched.retrieved_at,
                worker_id=worker_id,
                run_id=run.id,
                content_type=content_type,
            )
            logger.info(
                "page_fetched",
                **context,
                final_url=fetched.final_url,
                http_status=fetched.status_code,
                content_type=content_type,
                response_bytes=len(fetched.body),
                body_sha256=fetched.body_sha256,
                redirect_chain=list(fetched.redirect_chain),
            )
            if fetched.status_code < 200 or fetched.status_code >= 300:
                if fetched.status_code in _NON_RETRYABLE_HTTP_STATUSES:
                    raise ArticleAccessBlockedError(
                        f"article access blocked HTTP {fetched.status_code}"
                    )
                if fetched.status_code in _PERMANENT_HTTP_STATUSES:
                    raise ArticleNotFoundError(
                        f"article returned permanent HTTP {fetched.status_code}"
                    )
                raise ArticleProcessingError(
                    f"article returned HTTP {fetched.status_code}"
                )
            raw_artifact = None
            if self._raw_artifact_store is not None:
                raw_artifact = await self._raw_artifact_store.save_raw_html(
                    candidate_id=candidate.id,
                    body=fetched.body,
                    body_sha256=fetched.body_sha256,
                    retrieved_at=fetched.retrieved_at,
                )
                logger.info(
                    "raw_snapshot_saved",
                    **context,
                    raw_artifact_uri=raw_artifact.artifact_uri,
                    raw_artifact_sha256=raw_artifact.sha256,
                    raw_artifact_bytes=raw_artifact.byte_size,
                )
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.EXTRACTING,
                occurred_at=datetime.now(UTC),
                worker_id=worker_id,
                run_id=run.id,
            )
            logger.info("extraction_started", **context, final_url=fetched.final_url)
            extracted = self._extractor(fetched.body, base_url=fetched.final_url)
            if not extracted.text_content:
                raise InsufficientArticleContentError("article text could not be extracted")
            _raise_for_unacceptable_extraction(extracted)
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.EXTRACTED,
                occurred_at=datetime.now(UTC),
                worker_id=worker_id,
                run_id=run.id,
            )
            logger.info(
                "extraction_succeeded",
                **context,
                final_url=fetched.final_url,
                status_code=fetched.status_code,
                canonical_url=extracted.canonical_url,
                content_sha256=extracted.content_sha256,
                extraction_method=extracted.extraction_method,
                warnings=list(extracted.warnings),
                word_count=extracted.word_count,
                extraction_quality_score=extracted.metadata.get(
                    "extraction_quality_score"
                ),
            )
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.VALIDATED,
                occurred_at=datetime.now(UTC),
                worker_id=worker_id,
                run_id=run.id,
            )
            logger.info(
                "article_validation_succeeded",
                **context,
                canonical_url=extracted.canonical_url or fetched.final_url,
                content_sha256=extracted.content_sha256,
                word_count=extracted.word_count,
            )
        except Exception as exc:
            event_name = (
                "extraction_rejected"
                if isinstance(exc, NonRetryableArticleProcessingError)
                else "extraction_failed"
            )
            logger.exception(
                event_name,
                **context,
                error_type=type(exc).__name__,
                error_message=str(exc)[:500],
                failure_class=_failure_class(exc),
                failure_reason=_failure_code(exc),
            )
            await self._record_failure(candidate, run, exc)
            raise

        try:
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.PERSISTING,
                occurred_at=datetime.now(UTC),
                worker_id=worker_id,
                run_id=run.id,
            )
            logger.info(
                "article_insert_started",
                **context,
                canonical_url=extracted.canonical_url or fetched.final_url,
                content_sha256=extracted.content_sha256,
            )
            result = await self._repository.complete_success(
                candidate=candidate,
                run=run,
                fetched=fetched,
                extracted=extracted,
                raw_artifact=raw_artifact,
                completed_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception(
                "database_commit_failed",
                **context,
                error_type=type(exc).__name__,
                error_message=str(exc)[:500],
                failure_class=_failure_class(exc),
                failure_reason=_failure_code(exc),
            )
            await self._record_failure(candidate, run, exc)
            raise

        logger.info(
            "article_saved",
            **context,
            article_id=str(result.article_id),
            event_id=str(result.event_id),
            version_id=str(result.version_id) if result.version_id else None,
            created_article=result.created_article,
            created_event=result.created_event,
            created_version=result.created_version,
        )
        if result.version_id:
            logger.info(
                "article_version_saved",
                **context,
                article_id=str(result.article_id),
                version_id=str(result.version_id),
                created_version=result.created_version,
            )
        logger.info(
            "claims_saved",
            **context,
            article_id=str(result.article_id),
            version_id=str(result.version_id) if result.version_id else None,
            claim_count=result.claim_count,
        )
        logger.info(
            "evidence_saved",
            **context,
            article_id=str(result.article_id),
            version_id=str(result.version_id) if result.version_id else None,
            evidence_count=result.claim_count,
        )
        logger.info(
            "article_job_completed",
            **context,
            article_id=str(result.article_id),
            event_id=str(result.event_id),
            version_id=str(result.version_id) if result.version_id else None,
            processing_duration_ms=_duration_ms(started_at, datetime.now(UTC)),
        )
        return result

    async def _record_failure(
        self,
        candidate: LeasedUrlCandidate,
        run: ArticleFetchRun,
        exc: Exception,
    ) -> None:
        now = datetime.now(UTC)
        terminal = candidate.attempt_count >= self._max_attempts or isinstance(
            exc,
            NonRetryableArticleProcessingError,
        )
        retry_at = (
            None
            if terminal
            else retry_at_for_attempt(
                candidate.attempt_count,
                base_seconds=self._retry_base_seconds,
                max_seconds=self._retry_max_seconds,
                jitter_ratio=self._retry_jitter_ratio,
                now=now,
            )
        )
        await self._repository.complete_failure(
            candidate=candidate,
            run=run,
            completed_at=now,
            error_type=type(exc).__name__,
            error_message=str(exc)[:2_000],
            retry_at=retry_at,
            terminal=terminal,
        )
        event_name = "article_job_dead_lettered" if terminal else "article_job_retry_scheduled"
        logger.info(
            event_name,
            candidate_id=str(candidate.id),
            publisher_id=str(candidate.publisher_id),
            normalized_url=candidate.normalized_url,
            attempt_count=candidate.attempt_count,
            retry_at=_isoformat(retry_at),
            terminal=terminal,
            failure_class=_failure_class(exc),
            failure_reason=_failure_code(exc),
            error_type=type(exc).__name__,
        )


class ArticleWorker:
    def __init__(
        self,
        *,
        repository: ArticleProcessingRepository,
        processor: ArticleProcessor,
        worker_id: str,
        batch_size: int = 20,
        lease_seconds: int = 120,
        concurrency: int = 5,
    ) -> None:
        self._repository = repository
        self._processor = processor
        self._worker_id = worker_id
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._concurrency = concurrency

    async def run_once(self) -> int:
        candidates = await self._repository.lease_due_candidates(
            worker_id=self._worker_id,
            limit=self._batch_size,
            lease_seconds=self._lease_seconds,
        )
        semaphore = asyncio.Semaphore(self._concurrency)

        async def run(candidate: LeasedUrlCandidate) -> None:
            async with semaphore:
                try:
                    await self._processor.process(candidate, worker_id=self._worker_id)
                except (OSError, SQLAlchemyError):
                    raise
                except Exception:
                    return

        await asyncio.gather(*(run(candidate) for candidate in candidates))
        return len(candidates)


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _raise_for_unacceptable_extraction(extracted: ExtractedArticle) -> None:
    fatal_warnings = sorted(set(extracted.warnings) & _FATAL_EXTRACTION_WARNINGS)
    if not fatal_warnings:
        return
    quality_score = extracted.metadata.get("extraction_quality_score")
    raise ExtractionQualityError(
        "article extraction rejected: "
        f"fatal_warnings={fatal_warnings}; "
        f"quality_score={quality_score}; "
        f"word_count={extracted.word_count}"
    )


def _duration_ms(started_at: datetime, completed_at: datetime) -> int:
    return max(0, round((completed_at - started_at).total_seconds() * 1_000))


def _candidate_log_context(
    candidate: LeasedUrlCandidate,
    *,
    worker_id: str,
    correlation_id: UUID,
    started_at: datetime,
) -> dict[str, object]:
    return {
        "candidate_id": str(candidate.id),
        "publisher_id": str(candidate.publisher_id),
        "normalized_url": candidate.normalized_url,
        "url": candidate.normalized_url,
        "worker_id": worker_id,
        "attempt_count": candidate.attempt_count,
        "attempt_number": candidate.attempt_count,
        "published_at": _isoformat(candidate.published_at),
        "first_discovered_at": _isoformat(candidate.first_discovered_at),
        "url_type": candidate.url_type,
        "processing_started_at": started_at.isoformat(),
        "correlation_id": str(correlation_id),
    }


def _failure_class(exc: Exception) -> str:
    if isinstance(exc, NonRetryableArticleProcessingError):
        return "permanent"
    return "retryable"


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, ArticleAccessBlockedError):
        return "access_blocked"
    if isinstance(exc, ArticleNotFoundError):
        return "http_permanent"
    if isinstance(exc, ExtractionQualityError):
        return "extraction_quality_rejected"
    if isinstance(exc, InsufficientArticleContentError):
        return "missing_body"
    if isinstance(exc, SQLAlchemyError):
        return "database_error"
    return type(exc).__name__
