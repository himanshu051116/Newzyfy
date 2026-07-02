from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest

from newsintel.application.acquisition.dto import (
    CreateChannelCommand,
    CreatePublisherCommand,
    ObserveDiscoveryCommand,
)
from newsintel.application.acquisition.service import AcquisitionService
from newsintel.contracts.events import IntegrationEvent
from newsintel.domain.acquisition.entities import (
    DiscoveryChannel,
    Publisher,
    UrlCandidate,
    UrlDiscovery,
)
from newsintel.domain.acquisition.models import DiscoveryChannelType


class MemoryPublishers:
    def __init__(self) -> None:
        self.items: dict[UUID, Publisher] = {}

    async def get(self, publisher_id: UUID) -> Publisher | None:
        return self.items.get(publisher_id)

    async def get_by_slug(self, slug: str) -> Publisher | None:
        return next((item for item in self.items.values() if item.slug == slug), None)

    async def add(self, publisher: Publisher) -> None:
        self.items[publisher.id] = publisher


class MemoryChannels:
    def __init__(self) -> None:
        self.items: dict[UUID, DiscoveryChannel] = {}

    async def get(self, channel_id: UUID) -> DiscoveryChannel | None:
        return self.items.get(channel_id)

    async def get_by_endpoint(
        self,
        publisher_id: UUID,
        endpoint_url: str,
    ) -> DiscoveryChannel | None:
        return next(
            (
                item
                for item in self.items.values()
                if item.publisher_id == publisher_id
                and item.endpoint_url == endpoint_url
            ),
            None,
        )

    async def add(self, channel: DiscoveryChannel) -> None:
        self.items[channel.id] = channel


class MemoryFrontier:
    def __init__(self) -> None:
        self.candidates: dict[bytes, UrlCandidate] = {}
        self.discoveries: dict[tuple[UUID, UUID], UrlDiscovery] = {}

    async def get_by_fingerprint(self, fingerprint: bytes) -> UrlCandidate | None:
        return self.candidates.get(fingerprint)

    async def add_candidate(self, candidate: UrlCandidate) -> None:
        self.candidates[candidate.url_fingerprint] = candidate

    async def update_candidate_job_metadata(
        self,
        *,
        candidate_id: UUID,
        published_at: datetime | None,
        discovered_at: datetime,
    ) -> UrlCandidate | None:
        del discovered_at
        candidate = next(
            (
                item
                for item in self.candidates.values()
                if item.id == candidate_id
            ),
            None,
        )
        if candidate is None:
            return None
        if published_at is not None:
            candidate.published_at = published_at.astimezone(UTC)
        return candidate

    async def add_discovery_if_absent(self, discovery: UrlDiscovery) -> bool:
        key = (discovery.url_candidate_id, discovery.channel_id)
        if key in self.discoveries:
            return False
        self.discoveries[key] = discovery
        return True


class MemoryOutbox:
    def __init__(self) -> None:
        self.events: dict[str, IntegrationEvent] = {}

    async def add(self, event: IntegrationEvent) -> None:
        self.events.setdefault(event.idempotency_key, event)


class MemoryUnitOfWork:
    def __init__(self) -> None:
        self.publishers = MemoryPublishers()
        self.channels = MemoryChannels()
        self.frontier = MemoryFrontier()
        self.outbox = MemoryOutbox()
        self.commit_count = 0
        self.rollback_count = 0

    async def __aenter__(self) -> "MemoryUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        if exc:
            await self.rollback()

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


def service_for(uow: MemoryUnitOfWork) -> AcquisitionService:
    @asynccontextmanager
    async def factory() -> AsyncIterator[MemoryUnitOfWork]:
        async with uow:
            yield uow

    return AcquisitionService(factory)


@pytest.mark.asyncio
async def test_discovery_is_idempotent_for_same_channel() -> None:
    uow = MemoryUnitOfWork()
    service = service_for(uow)
    publisher = await service.create_publisher(
        CreatePublisherCommand(
            name="Example News",
            slug="example-news",
            canonical_domain="www.example.com",
        )
    )
    channel = await service.create_channel(
        CreateChannelCommand(
            publisher_id=publisher.id,
            channel_type=DiscoveryChannelType.NEWS_SITEMAP,
            endpoint_url="https://example.com/news.xml",
        )
    )
    command = ObserveDiscoveryCommand(
        channel_id=channel.id,
        url="https://example.com/story?id=42&utm_source=news",
        title="Story",
    )

    first = await service.observe_discovery(command)
    second = await service.observe_discovery(command)

    assert first.candidate_created
    assert first.channel_observation_created
    assert len(first.outbox_event_ids) == 2
    assert not second.candidate_created
    assert not second.channel_observation_created
    assert second.outbox_event_ids == ()
    assert len(uow.frontier.candidates) == 1
    assert len(uow.frontier.discoveries) == 1


@pytest.mark.asyncio
async def test_second_channel_cross_validates_existing_candidate() -> None:
    uow = MemoryUnitOfWork()
    service = service_for(uow)
    publisher = await service.create_publisher(
        CreatePublisherCommand(
            name="Example News",
            slug="example-news",
            canonical_domain="example.com",
        )
    )
    rss = await service.create_channel(
        CreateChannelCommand(
            publisher_id=publisher.id,
            channel_type=DiscoveryChannelType.RSS,
            endpoint_url="https://example.com/rss",
        )
    )
    sitemap = await service.create_channel(
        CreateChannelCommand(
            publisher_id=publisher.id,
            channel_type=DiscoveryChannelType.NEWS_SITEMAP,
            endpoint_url="https://example.com/news.xml",
        )
    )

    await service.observe_discovery(
        ObserveDiscoveryCommand(channel_id=rss.id, url="https://example.com/story")
    )
    result = await service.observe_discovery(
        ObserveDiscoveryCommand(channel_id=sitemap.id, url="https://example.com/story")
    )

    assert not result.candidate_created
    assert result.channel_observation_created
    assert len(result.outbox_event_ids) == 1
    assert len(uow.frontier.discoveries) == 2
