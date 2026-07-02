from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from newsintel.adapters.http.safe_fetcher import FetchResult
from newsintel.application.acquisition.dto import (
    CreateChannelCommand,
    ObserveDiscoveryCommand,
)
from newsintel.application.acquisition.polling import (
    ChannelPollService,
    PollCompletion,
    PollRun,
    PollRunStatus,
    next_interval_seconds,
)
from newsintel.core.ids import uuid7
from newsintel.domain.acquisition.entities import DiscoveryChannel
from newsintel.domain.acquisition.models import DiscoveryChannelType


@dataclass(frozen=True)
class AdmissionResult:
    candidate_created: bool
    channel_observation_created: bool


class FakeAdmission:
    def __init__(self) -> None:
        self.observations: list[ObserveDiscoveryCommand] = []
        self.channels: list[CreateChannelCommand] = []

    async def observe_discovery(
        self,
        command: ObserveDiscoveryCommand,
        *,
        correlation_id: UUID | None = None,
        traceparent: str | None = None,
    ) -> AdmissionResult:
        del correlation_id, traceparent
        self.observations.append(command)
        return AdmissionResult(
            candidate_created=True,
            channel_observation_created=True,
        )

    async def create_channel(self, command: CreateChannelCommand) -> object:
        self.channels.append(command)
        return object()


class FakeFetcher:
    def __init__(self, result: FetchResult | Exception) -> None:
        self.result = result
        self.requests: list[object] = []

    async def fetch(self, request: object) -> FetchResult:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakePollingRepository:
    def __init__(self) -> None:
        self.completions: list[PollCompletion] = []

    async def lease_due_channels(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> tuple[DiscoveryChannel, ...]:
        del worker_id, limit, lease_seconds
        return ()

    async def schedule_now(self, channel_id: UUID) -> bool:
        del channel_id
        return True

    async def start_run(
        self,
        *,
        channel_id: UUID,
        worker_id: str,
        trace_id: UUID,
        started_at: datetime,
    ) -> PollRun:
        return PollRun(
            id=uuid7(),
            channel_id=channel_id,
            worker_id=worker_id,
            trace_id=trace_id,
            started_at=started_at,
        )

    async def complete(self, completion: PollCompletion) -> None:
        self.completions.append(completion)


def channel(channel_type: DiscoveryChannelType) -> DiscoveryChannel:
    return DiscoveryChannel(
        id=uuid7(),
        publisher_id=uuid7(),
        channel_type=channel_type,
        endpoint_url="https://example.com/feed",
        strategy_version="test-v1",
        poll_min_seconds=60,
        poll_max_seconds=3_600,
        current_poll_seconds=300,
    )


def fetch_result(
    *,
    status: int = 200,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> FetchResult:
    return FetchResult(
        requested_url="https://example.com/feed",
        final_url="https://example.com/feed",
        status_code=status,
        headers=headers or {},
        body=body,
        body_sha256="0" * 64,
        retrieved_at=datetime.now(UTC),
        redirect_chain=(),
    )


@pytest.mark.asyncio
async def test_rss_poll_admits_items_and_updates_conditional_state() -> None:
    published_at = datetime.now(UTC).isoformat()
    body = f"""<rss><channel>
      <item><guid>1</guid><title>One</title>
      <link>https://example.com/news/one-important-story-today?utm_source=rss</link>
      <pubDate>{published_at}</pubDate></item>
      <item><guid>2</guid><title>Two</title>
      <link>https://example.com/business/two-market-story-today</link>
      <pubDate>{published_at}</pubDate></item>
    </channel></rss>""".encode()
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(
            fetch_result(
                body=body,
                headers={"etag": '"feed-v2"', "last-modified": "Wed, 25 Jun 2026 10:00:00 GMT"},
            )
        ),
    )

    result = await service.poll(channel(DiscoveryChannelType.RSS), "worker-1")

    assert result.status is PollRunStatus.SUCCEEDED
    assert result.discovered_count == 2
    assert result.admitted_count == 2
    assert result.observation_count == 2
    assert len(admission.observations) == 2
    assert repository.completions[0].etag == '"feed-v2"'
    assert repository.completions[0].current_poll_seconds == 60


@pytest.mark.asyncio
async def test_html_channel_poll_admits_recent_article_links_without_pubdate() -> None:
    body = b"""<html><body>
      <a href="/news/2026/07/02/one-important-story-today">One story</a>
      <a href="/topics/artificial-intelligence">Topic page</a>
      <a href="/technology">Technology section</a>
      <a href="/business/markets-rally-after-policy-update">Markets update</a>
    </body></html>"""
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(fetch_result(body=body)),
    )

    result = await service.poll(channel(DiscoveryChannelType.HOMEPAGE), "worker-1")

    assert result.status is PollRunStatus.SUCCEEDED
    assert result.discovered_count == 2
    assert result.admitted_count == 2
    assert len(admission.observations) == 2
    assert str(admission.observations[0].url) == (
        "https://example.com/news/2026/07/02/one-important-story-today"
    )
    assert admission.observations[0].title == "One story"
    assert admission.observations[0].published_at is None


@pytest.mark.asyncio
async def test_not_modified_poll_slows_schedule_without_parsing() -> None:
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(fetch_result(status=304)),
    )

    result = await service.poll(channel(DiscoveryChannelType.RSS), "worker-1")

    assert result.status is PollRunStatus.NOT_MODIFIED
    assert not admission.observations
    assert repository.completions[0].current_poll_seconds == 450


@pytest.mark.asyncio
async def test_sitemap_index_onboards_child_sitemaps() -> None:
    body = b"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.com/news-1.xml</loc></sitemap>
      <sitemap><loc>https://example.com/news-2.xml</loc></sitemap>
    </sitemapindex>"""
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(fetch_result(body=body)),
    )

    result = await service.poll(channel(DiscoveryChannelType.SITEMAP), "worker-1")

    assert result.discovered_count == 2
    assert result.admitted_count == 2
    assert len(admission.channels) == 2
    assert all(
        item.channel_type is DiscoveryChannelType.SITEMAP
        for item in admission.channels
    )


@pytest.mark.asyncio
async def test_failure_is_persisted_and_backoff_increases() -> None:
    repository = FakePollingRepository()
    service = ChannelPollService(
        polling_repository=repository,
        admission=FakeAdmission(),
        fetcher=FakeFetcher(RuntimeError("network unavailable")),
    )

    with pytest.raises(RuntimeError, match="network unavailable"):
        await service.poll(channel(DiscoveryChannelType.RSS), "worker-1")

    completion = repository.completions[0]
    assert completion.status is PollRunStatus.FAILED
    assert completion.error_type == "RuntimeError"
    assert completion.current_poll_seconds == 600


def test_interval_policy_is_bounded() -> None:
    item = channel(DiscoveryChannelType.RSS)
    item.current_poll_seconds = 3_500

    assert (
        next_interval_seconds(item, status=PollRunStatus.NOT_MODIFIED)
        == item.poll_max_seconds
    )


def test_channel_poll_intervals_must_be_consistent() -> None:
    with pytest.raises(ValidationError, match="poll_min_seconds cannot exceed"):
        CreateChannelCommand(
            publisher_id=uuid7(),
            channel_type=DiscoveryChannelType.RSS,
            endpoint_url="https://example.com/rss",
            poll_min_seconds=600,
            poll_max_seconds=300,
            current_poll_seconds=300,
        )
