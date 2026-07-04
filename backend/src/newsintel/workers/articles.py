import asyncio
import os
import socket

import structlog
from sqlalchemy.exc import SQLAlchemyError

from newsintel.adapters.artifacts.local_store import LocalRawArtifactStore
from newsintel.adapters.artifacts.s3_store import S3RawArtifactStore
from newsintel.adapters.extractors.article_html import extract_article_html
from newsintel.adapters.http.safe_fetcher import SafeHttpFetcher
from newsintel.application.articles.processing import (
    ArticleProcessor,
    ArticleWorker,
    RawArtifactStore,
)
from newsintel.core.config import Settings, get_settings
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.article_processing_repository import (
    SqlAlchemyArticleProcessingRepository,
)
from newsintel.infrastructure.db.session import Database


def database_retry_delay(attempt: int, maximum_seconds: float) -> float:
    return min(maximum_seconds, float(2 ** min(attempt, 10)))


def raw_artifact_store(settings: Settings) -> RawArtifactStore:
    if settings.raw_artifact_store_backend == "s3":
        return S3RawArtifactStore(
            endpoint_url=settings.object_store_endpoint,
            bucket=settings.object_store_bucket,
            access_key=settings.object_store_access_key,
            secret_key=settings.object_store_secret_key.get_secret_value(),
            prefix=settings.s3_artifact_prefix,
            server_side_encryption=settings.s3_artifact_sse,
        )
    return LocalRawArtifactStore(settings.raw_artifact_dir)


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger("article-worker")
    database = Database(settings)
    repository = SqlAlchemyArticleProcessingRepository(database.session_factory)
    fetcher = SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
    )
    processor = ArticleProcessor(
        repository=repository,
        fetcher=fetcher,
        extractor=extract_article_html,
        raw_artifact_store=raw_artifact_store(settings),
        max_attempts=settings.article_fetch_max_attempts,
        retry_base_seconds=settings.article_fetch_retry_base_seconds,
        retry_max_seconds=settings.article_fetch_retry_max_seconds,
        retry_jitter_ratio=settings.article_fetch_retry_jitter_ratio,
        recent_article_window_hours=settings.recent_article_window_hours,
    )
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    worker = ArticleWorker(
        repository=repository,
        processor=processor,
        worker_id=worker_id,
        batch_size=settings.article_worker_batch_size,
        lease_seconds=settings.article_worker_lease_seconds,
        concurrency=settings.article_worker_concurrency,
    )
    logger.info("article_worker_started", worker_id=worker_id)
    database_failure_attempt = 0
    try:
        while True:
            try:
                claimed = await worker.run_once()
                if database_failure_attempt:
                    logger.info("database_connection_restored")
                    database_failure_attempt = 0
            except (OSError, SQLAlchemyError) as exc:
                database_failure_attempt += 1
                delay = database_retry_delay(
                    database_failure_attempt,
                    settings.database_retry_max_seconds,
                )
                logger.error(
                    "database_unavailable",
                    error_type=type(exc).__name__,
                    retry_in_seconds=delay,
                    hint="Run: python -m newsintel.doctor",
                )
                await asyncio.sleep(delay)
                continue
            if claimed == 0:
                await asyncio.sleep(settings.article_worker_idle_seconds)
    finally:
        await database.dispose()


def run() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    run()
