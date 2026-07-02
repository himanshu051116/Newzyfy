from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from newsintel.adapters.extractors.article_html import ExtractedArticle
from newsintel.adapters.http.safe_fetcher import FetchResult
from newsintel.application.articles.processing import (
    ArticleAccessBlockedError,
    ArticleFetchRun,
    ArticleJobRejectedError,
    ArticleProcessingResult,
    ArticleProcessingStage,
    ArticleProcessor,
    ExtractionQualityError,
    InsufficientArticleContentError,
    LeasedUrlCandidate,
    retry_at_for_attempt,
)
from newsintel.core.ids import uuid7


class FakeRepository:
    def __init__(self) -> None:
        self.failures: list[dict[str, object]] = []
        self.rejections: list[dict[str, object]] = []
        self.stages: list[ArticleProcessingStage] = []
        self.successes: list[tuple[LeasedUrlCandidate, ExtractedArticle]] = []
        self.success_error: Exception | None = None

    async def lease_due_candidates(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> tuple[LeasedUrlCandidate, ...]:
        del worker_id, limit, lease_seconds
        return ()

    async def start_fetch(
        self,
        *,
        candidate_id: UUID,
        worker_id: str,
        trace_id: UUID,
        started_at: datetime,
    ) -> ArticleFetchRun:
        return ArticleFetchRun(
            id=uuid7(),
            candidate_id=candidate_id,
            worker_id=worker_id,
            trace_id=trace_id,
            started_at=started_at,
        )

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
    ) -> None:
        del (
            candidate,
            occurred_at,
            worker_id,
            run_id,
            content_type,
            failure_code,
            failure_message,
            processing_duration_ms,
        )
        self.stages.append(stage)

    async def complete_success(
        self,
        *,
        candidate: LeasedUrlCandidate,
        run: ArticleFetchRun,
        fetched: FetchResult,
        extracted: ExtractedArticle,
        raw_artifact: object | None,
        completed_at: datetime,
    ) -> ArticleProcessingResult:
        del run, fetched, raw_artifact, completed_at
        if self.success_error is not None:
            raise self.success_error
        self.successes.append((candidate, extracted))
        return ArticleProcessingResult(
            candidate_id=candidate.id,
            article_id=uuid7(),
            event_id=uuid7(),
            version_id=uuid7(),
            created_article=True,
            created_event=True,
            created_version=True,
        )

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
    ) -> None:
        del run, completed_at
        self.failures.append(
            {
                "candidate_id": candidate.id,
                "error_type": error_type,
                "error_message": error_message,
                "retry_at": retry_at,
                "terminal": terminal,
            }
        )

    async def reject_before_fetch(
        self,
        *,
        candidate: LeasedUrlCandidate,
        worker_id: str,
        trace_id: UUID,
        rejected_at: datetime,
        reason: str,
        message: str,
    ) -> None:
        del worker_id, trace_id, rejected_at
        self.rejections.append(
            {
                "candidate_id": candidate.id,
                "reason": reason,
                "message": message,
            }
        )


class FakeFetcher:
    def __init__(self, result: FetchResult) -> None:
        self.result = result
        self.requests: list[object] = []

    async def fetch(self, request: object) -> FetchResult:
        self.requests.append(request)
        return self.result


def candidate(
    *,
    attempts: int = 1,
    published_at: datetime | None = None,
    url: str = "https://example.com/news/one-important-story-today",
) -> LeasedUrlCandidate:
    return LeasedUrlCandidate(
        id=uuid7(),
        publisher_id=uuid7(),
        normalized_url=url,
        attempt_count=attempts,
        published_at=published_at,
        first_discovered_at=datetime.now(UTC),
    )


def fetched(*, status: int = 200) -> FetchResult:
    return FetchResult(
        requested_url="https://example.com/story",
        final_url="https://example.com/story",
        status_code=status,
        headers={},
        body=b"<html></html>",
        body_sha256="0" * 64,
        retrieved_at=datetime.now(UTC),
        redirect_chain=(),
    )


def extracted(
    *,
    text: str = "A real article body with enough recovered source text.",
    warnings: tuple[str, ...] = (),
) -> ExtractedArticle:
    return ExtractedArticle(
        title="Story",
        byline="Reporter",
        published_at=datetime.now(UTC),
        modified_at=None,
        language="en",
        canonical_url="https://example.com/story",
        text_content=text,
        content_sha256="a" * 64,
        extraction_method="test",
        metadata={
            "word_count": len(text.split()),
            "extraction_quality_score": 0.8,
        },
        warnings=warnings,
    )


@pytest.mark.asyncio
async def test_article_processor_records_success_from_real_extraction_result() -> None:
    repository = FakeRepository()
    fetcher = FakeFetcher(fetched())
    processor = ArticleProcessor(
        repository=repository,
        fetcher=fetcher,
        extractor=lambda html, *, base_url: extracted(),
    )

    result = await processor.process(candidate(), worker_id="worker-1")

    assert result.created_article
    assert len(repository.successes) == 1
    assert len(fetcher.requests) == 1
    assert repository.failures == []


@pytest.mark.asyncio
async def test_article_processor_retries_insufficient_content() -> None:
    repository = FakeRepository()
    processor = ArticleProcessor(
        repository=repository,
        fetcher=FakeFetcher(fetched()),
        extractor=lambda html, *, base_url: extracted(text=""),
    )

    with pytest.raises(InsufficientArticleContentError):
        await processor.process(candidate(attempts=2), worker_id="worker-1")

    failure = repository.failures[0]
    assert failure["error_type"] == "InsufficientArticleContentError"
    assert failure["retry_at"] is not None
    assert failure["terminal"] is False


@pytest.mark.asyncio
async def test_article_processor_marks_blocked_access_as_terminal_failure() -> None:
    repository = FakeRepository()
    processor = ArticleProcessor(
        repository=repository,
        fetcher=FakeFetcher(fetched(status=403)),
        extractor=lambda html, *, base_url: extracted(),
    )

    with pytest.raises(ArticleAccessBlockedError):
        await processor.process(candidate(), worker_id="worker-1")

    failure = repository.failures[0]
    assert failure["error_type"] == "ArticleAccessBlockedError"
    assert failure["retry_at"] is None
    assert failure["terminal"] is True


@pytest.mark.asyncio
async def test_article_processor_marks_paywall_quality_warning_as_terminal_failure() -> None:
    repository = FakeRepository()
    processor = ArticleProcessor(
        repository=repository,
        fetcher=FakeFetcher(fetched()),
        extractor=lambda html, *, base_url: extracted(
            warnings=("possible_paywall_or_partial_content",)
        ),
    )

    with pytest.raises(ExtractionQualityError):
        await processor.process(candidate(), worker_id="worker-1")

    failure = repository.failures[0]
    assert failure["error_type"] == "ExtractionQualityError"
    assert failure["retry_at"] is None
    assert failure["terminal"] is True
    assert repository.successes == []


@pytest.mark.asyncio
async def test_article_processor_records_persistence_failure_after_extraction() -> None:
    repository = FakeRepository()
    repository.success_error = RuntimeError("database commit failed")
    processor = ArticleProcessor(
        repository=repository,
        fetcher=FakeFetcher(fetched()),
        extractor=lambda html, *, base_url: extracted(),
        retry_jitter_ratio=0,
    )

    with pytest.raises(RuntimeError, match="database commit failed"):
        await processor.process(candidate(attempts=1), worker_id="worker-1")

    assert ArticleProcessingStage.EXTRACTED in repository.stages
    assert ArticleProcessingStage.PERSISTING in repository.stages
    failure = repository.failures[0]
    assert failure["error_type"] == "RuntimeError"
    assert failure["retry_at"] is not None
    assert failure["terminal"] is False
    assert repository.successes == []


@pytest.mark.asyncio
async def test_article_processor_rejects_stale_candidate_before_fetch() -> None:
    repository = FakeRepository()
    fetcher = FakeFetcher(fetched())
    processor = ArticleProcessor(
        repository=repository,
        fetcher=fetcher,
        extractor=lambda html, *, base_url: extracted(),
        recent_article_window_hours=48,
    )

    with pytest.raises(ArticleJobRejectedError):
        await processor.process(
            candidate(published_at=datetime.now(UTC) - timedelta(days=5)),
            worker_id="worker-1",
        )

    assert fetcher.requests == []
    assert repository.failures == []
    assert repository.rejections[0]["reason"] == "too_old"


@pytest.mark.asyncio
async def test_article_processor_rejects_non_article_url_before_fetch() -> None:
    repository = FakeRepository()
    fetcher = FakeFetcher(fetched())
    processor = ArticleProcessor(
        repository=repository,
        fetcher=fetcher,
        extractor=lambda html, *, base_url: extracted(),
    )

    with pytest.raises(ArticleJobRejectedError):
        await processor.process(
            candidate(url="https://example.com/topics/artificial-intelligence"),
            worker_id="worker-1",
        )

    assert fetcher.requests == []
    assert repository.rejections[0]["reason"] == "excluded_section"


def test_retry_backoff_uses_attempt_count() -> None:
    now = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)

    retry_at = retry_at_for_attempt(
        3,
        base_seconds=60,
        max_seconds=1_000,
        now=now,
    )

    assert (retry_at - now).total_seconds() == 240
