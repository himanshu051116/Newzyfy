import asyncio
import os
import socket

import structlog
from sqlalchemy.exc import SQLAlchemyError

from newsintel.adapters.http.safe_fetcher import SafeHttpFetcher
from newsintel.application.acquisition.polling import ChannelPollService, PollWorker
from newsintel.application.acquisition.service import AcquisitionService
from newsintel.core.config import get_settings
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.polling_repository import SqlAlchemyPollingRepository
from newsintel.infrastructure.db.session import Database
from newsintel.infrastructure.db.unit_of_work import SqlAlchemyAcquisitionUnitOfWork


def database_retry_delay(attempt: int, maximum_seconds: float) -> float:
    return min(maximum_seconds, float(2 ** min(attempt, 10)))


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger("acquisition-poller")
    database = Database(settings)
    repository = SqlAlchemyPollingRepository(database.session_factory)
    admission = AcquisitionService(
        lambda: SqlAlchemyAcquisitionUnitOfWork(database.session_factory)
    )
    fetcher = SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
    )
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=fetcher,
        recent_article_window_hours=settings.recent_article_window_hours,
        max_new_urls_per_channel_poll=settings.max_new_urls_per_channel_poll,
    )
    worker = PollWorker(
        repository=repository,
        service=service,
        worker_id=worker_id,
        batch_size=settings.poll_worker_batch_size,
        lease_seconds=settings.poll_worker_lease_seconds,
        concurrency=settings.poll_worker_concurrency,
    )
    logger.info("poll_worker_started", worker_id=worker_id)
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
                await asyncio.sleep(settings.poll_worker_idle_seconds)
    finally:
        await database.dispose()


def run() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    run()
