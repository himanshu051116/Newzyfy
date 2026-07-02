import asyncio
import os
import socket
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from newsintel.core.config import get_settings
from newsintel.core.ids import uuid7
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.models import ConsumerInboxModel, OutboxEventModel
from newsintel.infrastructure.db.session import Database

CONSUMER_NAME = "local-outbox-relay"
HANDLER_VERSION = "local-outbox-relay-v1"


def database_retry_delay(attempt: int, maximum_seconds: float) -> float:
    return min(maximum_seconds, float(2 ** min(attempt, 10)))


async def publish_pending_outbox_once(
    *,
    database: Database,
    worker_id: str,
    batch_size: int,
) -> int:
    now = datetime.now(UTC)
    async with database.session_factory() as session, session.begin():
        events = (
            await session.scalars(
                select(OutboxEventModel)
                .where(OutboxEventModel.published_at.is_(None))
                .order_by(OutboxEventModel.occurred_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for event in events:
            await session.execute(
                insert(ConsumerInboxModel)
                .values(
                    id=uuid7(),
                    consumer_name=CONSUMER_NAME,
                    event_id=event.id,
                    event_type=event.event_type,
                    processed_at=now,
                    handler_version=HANDLER_VERSION,
                )
                .on_conflict_do_nothing(
                    constraint="uq_consumer_inbox_consumer_event",
                )
            )
            await session.execute(
                update(OutboxEventModel)
                .where(OutboxEventModel.id == event.id)
                .values(published_at=now)
            )
    if events:
        structlog.get_logger("outbox-worker").info(
            "outbox_events_published",
            worker_id=worker_id,
            event_count=len(events),
            consumer_name=CONSUMER_NAME,
        )
    return len(events)


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger("outbox-worker")
    database = Database(settings)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info("outbox_worker_started", worker_id=worker_id)
    database_failure_attempt = 0
    try:
        while True:
            try:
                count = await publish_pending_outbox_once(
                    database=database,
                    worker_id=worker_id,
                    batch_size=settings.outbox_worker_batch_size,
                )
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
            if count == 0:
                await asyncio.sleep(settings.outbox_worker_idle_seconds)
    finally:
        await database.dispose()


def run() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    run()
