from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.acquisition.polling import (
    PollCompletion,
    PollingRepository,
    PollRun,
    PollRunStatus,
)
from newsintel.contracts.events import IntegrationEvent
from newsintel.core.ids import uuid7
from newsintel.domain.acquisition.entities import DiscoveryChannel
from newsintel.domain.acquisition.models import DiscoveryChannelType
from newsintel.infrastructure.db.models import (
    ChannelPollRunModel,
    DiscoveryChannelModel,
    OutboxEventModel,
)


def _channel_from_model(row: DiscoveryChannelModel) -> DiscoveryChannel:
    return DiscoveryChannel(
        id=row.id,
        publisher_id=row.publisher_id,
        channel_type=DiscoveryChannelType(row.channel_type),
        endpoint_url=row.endpoint_url,
        strategy_version=row.strategy_version,
        config=row.config,
        active=row.active,
        next_poll_at=row.next_poll_at,
        poll_min_seconds=row.poll_min_seconds,
        poll_max_seconds=row.poll_max_seconds,
        current_poll_seconds=row.current_poll_seconds,
        etag=row.etag,
        last_modified=row.last_modified,
        last_polled_at=row.last_polled_at,
        last_success_at=row.last_success_at,
        lease_owner=row.lease_owner,
        lease_expires_at=row.lease_expires_at,
        consecutive_failures=row.consecutive_failures,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyPollingRepository(PollingRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def lease_due_channels(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> tuple[DiscoveryChannel, ...]:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            rows = (
                await session.scalars(
                    select(DiscoveryChannelModel)
                    .where(
                        DiscoveryChannelModel.active.is_(True),
                        DiscoveryChannelModel.next_poll_at <= now,
                        or_(
                            DiscoveryChannelModel.lease_expires_at.is_(None),
                            DiscoveryChannelModel.lease_expires_at < now,
                        ),
                    )
                    .order_by(DiscoveryChannelModel.next_poll_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            lease_expires_at = now + timedelta(seconds=lease_seconds)
            for row in rows:
                row.lease_owner = worker_id
                row.lease_expires_at = lease_expires_at
            return tuple(_channel_from_model(row) for row in rows)

    async def schedule_now(self, channel_id: UUID) -> bool:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            updated_id = await session.scalar(
                update(DiscoveryChannelModel)
                .where(
                    DiscoveryChannelModel.id == channel_id,
                    DiscoveryChannelModel.active.is_(True),
                )
                .values(
                    next_poll_at=now,
                    updated_at=now,
                )
                .returning(DiscoveryChannelModel.id)
            )
            return updated_id is not None

    async def start_run(
        self,
        *,
        channel_id: UUID,
        worker_id: str,
        trace_id: UUID,
        started_at: datetime,
    ) -> PollRun:
        run = PollRun(
            id=uuid7(),
            channel_id=channel_id,
            worker_id=worker_id,
            trace_id=trace_id,
            started_at=started_at,
        )
        async with self._session_factory() as session, session.begin():
            session.add(
                ChannelPollRunModel(
                    id=run.id,
                    channel_id=run.channel_id,
                    worker_id=run.worker_id,
                    status=PollRunStatus.RUNNING.value,
                    started_at=run.started_at,
                    trace_id=run.trace_id,
                )
            )
        return run

    async def complete(self, completion: PollCompletion) -> None:
        succeeded = completion.status in {
            PollRunStatus.SUCCEEDED,
            PollRunStatus.NOT_MODIFIED,
        }
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(ChannelPollRunModel)
                .where(ChannelPollRunModel.id == completion.run_id)
                .values(
                    status=completion.status.value,
                    completed_at=completion.completed_at,
                    http_status=completion.http_status,
                    not_modified=completion.not_modified,
                    discovered_count=completion.discovered_count,
                    admitted_count=completion.admitted_count,
                    observation_count=completion.observation_count,
                    response_bytes=completion.response_bytes,
                    error_type=completion.error_type,
                    error_message=completion.error_message,
                )
            )
            channel_values: dict[str, object] = {
                "next_poll_at": completion.next_poll_at,
                "current_poll_seconds": completion.current_poll_seconds,
                "last_polled_at": completion.completed_at,
                "lease_owner": None,
                "lease_expires_at": None,
                "updated_at": completion.completed_at,
            }
            if succeeded:
                channel_values.update(
                    {
                        "last_success_at": completion.completed_at,
                        "consecutive_failures": 0,
                    }
                )
                if completion.etag is not None:
                    channel_values["etag"] = completion.etag
                if completion.last_modified is not None:
                    channel_values["last_modified"] = completion.last_modified
            else:
                channel_values["consecutive_failures"] = (
                    DiscoveryChannelModel.consecutive_failures + 1
                )
            await session.execute(
                update(DiscoveryChannelModel)
                .where(DiscoveryChannelModel.id == completion.channel_id)
                .values(**channel_values)
            )
            event_type = (
                "source.poll.completed" if succeeded else "source.poll.failed"
            )
            event = IntegrationEvent(
                event_type=event_type,
                aggregate_type="discovery_channel",
                aggregate_id=completion.channel_id,
                payload={
                    "poll_run_id": str(completion.run_id),
                    "channel_id": str(completion.channel_id),
                    "status": completion.status.value,
                    "http_status": completion.http_status,
                    "not_modified": completion.not_modified,
                    "discovered_count": completion.discovered_count,
                    "admitted_count": completion.admitted_count,
                    "observation_count": completion.observation_count,
                    "response_bytes": completion.response_bytes,
                    "next_poll_at": completion.next_poll_at.isoformat(),
                    "error_type": completion.error_type,
                },
                producer="acquisition-poller",
                correlation_id=completion.trace_id,
                idempotency_key=f"{event_type}:{completion.run_id}",
            )
            await session.execute(
                insert(OutboxEventModel)
                .values(
                    id=event.event_id,
                    event_type=event.event_type,
                    event_version=event.event_version,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    payload=event.payload,
                    occurred_at=event.occurred_at,
                    producer=event.producer,
                    correlation_id=event.correlation_id,
                    causation_id=event.causation_id,
                    traceparent=event.traceparent,
                    idempotency_key=event.idempotency_key,
                )
                .on_conflict_do_nothing(
                    constraint="uq_outbox_events_idempotency_key",
                )
            )
