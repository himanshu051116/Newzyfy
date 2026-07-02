from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

import structlog
from sqlalchemy import distinct, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.adapters.collectors.source_discovery import (
    DiscoveredEndpoint,
    ValidatedEndpoint,
    canonical_domain,
    common_discovery_endpoints,
    discover_alternate_links,
    discover_listing_endpoints,
    discover_robot_sitemaps,
    normalize_homepage_url,
    origin_for_url,
    unique_endpoints,
    validate_endpoint_payload,
)
from newsintel.adapters.http.safe_fetcher import FetchRequest, FetchResult
from newsintel.contracts.events import IntegrationEvent
from newsintel.core.ids import uuid7
from newsintel.domain.acquisition.canonicalization import (
    CanonicalizationPolicy,
    canonicalize_url,
)
from newsintel.domain.acquisition.models import DiscoveryChannelType
from newsintel.domain.acquisition.policies import normalize_domain
from newsintel.infrastructure.db.models import (
    ArticleModel,
    DiscoveryChannelModel,
    FetchJobModel,
    OutboxEventModel,
    PublisherModel,
    UrlCandidateModel,
    UrlDiscoveryModel,
)

from .dto import (
    DiscoveredChannelView,
    DiscoverPublisherCommand,
    FetchFrequency,
    FetchJobView,
    PublisherDiscoveryResult,
    PublisherSourceView,
)

DISCOVERY_STRATEGY_VERSION = "homepage-source-discovery-v1"
logger = structlog.get_logger(__name__)


class SourceDiscoveryError(RuntimeError):
    pass


class PublisherConflictError(ValueError):
    pass


class PublisherNotFoundError(LookupError):
    pass


class Fetcher(Protocol):
    async def fetch(self, request: FetchRequest) -> FetchResult: ...


@dataclass(frozen=True, slots=True)
class FrequencyPolicy:
    next_poll_at: datetime | None
    poll_min_seconds: int
    poll_max_seconds: int
    current_poll_seconds: int


class SourceService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        fetcher: Fetcher,
    ) -> None:
        self._session_factory = session_factory
        self._fetcher = fetcher

    async def discover_publisher(
        self,
        command: DiscoverPublisherCommand,
    ) -> PublisherDiscoveryResult:
        now = datetime.now(UTC)
        homepage_url = normalize_homepage_url(command.website_url)
        domain = normalize_domain(canonical_domain(homepage_url))
        slug = _slugify(command.publisher_name)
        homepage = await self._fetcher.fetch(FetchRequest(url=homepage_url))
        if homepage.status_code < 200 or homepage.status_code >= 300:
            raise SourceDiscoveryError(
                f"homepage returned HTTP {homepage.status_code}"
            )

        endpoints: list[DiscoveredEndpoint] = []
        endpoints.append(
            DiscoveredEndpoint(
                url=homepage.final_url,
                source="homepage",
                hinted_type=DiscoveryChannelType.HOMEPAGE,
            )
        )
        endpoints.extend(
            discover_alternate_links(homepage.body, homepage_url=homepage.final_url)
        )
        endpoints.extend(
            discover_listing_endpoints(homepage.body, homepage_url=homepage.final_url)
        )

        robots_url = f"{origin_for_url(homepage.final_url)}/robots.txt"
        try:
            robots = await self._fetcher.fetch(FetchRequest(url=robots_url))
            if 200 <= robots.status_code < 300:
                endpoints.extend(
                    discover_robot_sitemaps(robots.body, homepage_url=homepage.final_url)
                )
        except Exception as exc:
            logger.debug(
                "robots_txt_discovery_failed",
                homepage_url=homepage.final_url,
                error_type=type(exc).__name__,
            )

        endpoints.extend(common_discovery_endpoints(homepage.final_url))
        endpoints.extend(
            DiscoveredEndpoint(url=item, source="manual_fallback")
            for item in command.manual_endpoints
        )
        unique = unique_endpoints(tuple(endpoints))
        validated = await self._validate_endpoints(unique)

        async with self._session_factory() as session, session.begin():
            existing = await session.scalar(
                select(PublisherModel).where(PublisherModel.canonical_domain == domain)
            )
            if existing is not None:
                raise PublisherConflictError(
                    f"publisher already exists for domain: {domain}"
                )

            publisher = PublisherModel(
                id=uuid7(),
                name=command.publisher_name,
                slug=await _unique_slug(session, slug),
                canonical_domain=domain,
                homepage_url=homepage_url,
                fetch_frequency=command.fetch_frequency.value,
                discovery_status="ready" if validated else "no_channels_found",
                discovery_message=(
                    None
                    if validated
                    else (
                        "No valid RSS, Atom, sitemap, homepage, or listing-page "
                        "endpoint was discovered. Add a manual endpoint."
                    )
                ),
                active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(publisher)
            await session.flush()

            channels: list[DiscoveredChannelView] = []
            for endpoint in validated:
                created, channel_id = await _create_channel_if_absent(
                    session,
                    publisher_id=publisher.id,
                    endpoint=endpoint,
                    frequency=command.fetch_frequency,
                    now=now,
                )
                channels.append(
                    DiscoveredChannelView(
                        id=channel_id,
                        endpoint_url=endpoint.url,
                        channel_type=endpoint.channel_type.value,
                        source=endpoint.source,
                        item_count=endpoint.item_count,
                        created=created,
                    )
                )

            await _add_outbox(
                session,
                IntegrationEvent(
                    event_type="publisher.source_discovered",
                    aggregate_type="publisher",
                    aggregate_id=publisher.id,
                    payload={
                        "publisher_id": str(publisher.id),
                        "homepage_url": homepage_url,
                        "attempted_endpoint_count": len(unique),
                        "valid_endpoint_count": len(validated),
                        "fetch_frequency": command.fetch_frequency.value,
                    },
                    producer="source-api",
                    idempotency_key=f"publisher.source_discovered:{publisher.id}",
                ),
            )

            source_view = await _publisher_source_view(session, publisher)
            return PublisherDiscoveryResult(
                publisher=source_view,
                channels=channels,
                attempted_endpoint_count=len(unique),
                valid_endpoint_count=len(validated),
                invalid_endpoint_count=max(0, len(unique) - len(validated)),
                manual_fallback_available=not validated,
            )

    async def list_publishers(self) -> list[PublisherSourceView]:
        async with self._session_factory() as session:
            publishers = (
                await session.scalars(
                    select(PublisherModel)
                    .where(PublisherModel.active.is_(True))
                    .order_by(PublisherModel.name)
                )
            ).all()
            return [
                await _publisher_source_view(session, publisher)
                for publisher in publishers
            ]

    async def create_fetch_job(
        self,
        *,
        publisher_id: UUID | None,
    ) -> FetchJobView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            publisher_ids = await _fetch_target_publishers(session, publisher_id)
            if publisher_id is not None and not publisher_ids:
                raise PublisherNotFoundError(f"publisher not found: {publisher_id}")
            if not publisher_ids:
                raise PublisherNotFoundError("no active publishers are configured")

            job = FetchJobModel(
                id=uuid7(),
                publisher_id=publisher_id,
                job_type="publisher" if publisher_id else "all",
                status="scheduled",
                publishers_total=len(publisher_ids),
                publishers_processed=0,
                urls_discovered=0,
                articles_queued=0,
                articles_extracted=0,
                duplicates_skipped=0,
                failed_articles=0,
                message=(
                    "Discovery channels scheduled. Poller and article worker "
                    "will process asynchronously."
                ),
                metadata_={"publisher_ids": [str(item) for item in publisher_ids]},
                created_at=now,
                started_at=now,
                updated_at=now,
            )
            session.add(job)
            await session.execute(
                update(DiscoveryChannelModel)
                .where(
                    DiscoveryChannelModel.publisher_id.in_(publisher_ids),
                    DiscoveryChannelModel.active.is_(True),
                )
                .values(next_poll_at=now, updated_at=now)
            )
            await session.execute(
                update(PublisherModel)
                .where(PublisherModel.id.in_(publisher_ids))
                .values(last_fetched_at=now, updated_at=now)
            )
            await _add_outbox(
                session,
                IntegrationEvent(
                    event_type="fetch.job_scheduled",
                    aggregate_type="fetch_job",
                    aggregate_id=job.id,
                    payload={
                        "job_id": str(job.id),
                        "publisher_id": str(publisher_id) if publisher_id else None,
                        "publisher_ids": [str(item) for item in publisher_ids],
                    },
                    producer="source-api",
                    idempotency_key=f"fetch.job_scheduled:{job.id}",
                ),
            )
            return await _fetch_job_view(session, job)

    async def get_fetch_job(self, job_id: UUID) -> FetchJobView | None:
        async with self._session_factory() as session:
            job = await session.get(FetchJobModel, job_id)
            if job is None:
                return None
            return await _fetch_job_view(session, job)

    async def delete_publisher(self, publisher_id: UUID) -> bool:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await session.get(PublisherModel, publisher_id)
            if row is None:
                return False
            row.active = False
            row.updated_at = now
            await session.execute(
                update(DiscoveryChannelModel)
                .where(DiscoveryChannelModel.publisher_id == publisher_id)
                .values(active=False, updated_at=now)
            )
            return True

    async def _validate_endpoints(
        self,
        endpoints: Sequence[DiscoveredEndpoint],
    ) -> tuple[ValidatedEndpoint, ...]:
        validated: list[ValidatedEndpoint] = []
        for endpoint in endpoints:
            try:
                fetched = await self._fetcher.fetch(FetchRequest(url=endpoint.url))
                if fetched.status_code < 200 or fetched.status_code >= 300:
                    continue
                validated.append(
                    validate_endpoint_payload(
                        fetched.body,
                        endpoint_url=fetched.final_url,
                        source=endpoint.source,
                        hinted_type=endpoint.hinted_type,
                    )
                )
            except Exception as exc:
                logger.debug(
                    "discovery_endpoint_validation_failed",
                    endpoint_url=endpoint.url,
                    source=endpoint.source,
                    error_type=type(exc).__name__,
                )
        return tuple(validated)


async def _fetch_target_publishers(
    session: AsyncSession,
    publisher_id: UUID | None,
) -> list[UUID]:
    statement = select(PublisherModel.id).where(PublisherModel.active.is_(True))
    if publisher_id is not None:
        statement = statement.where(PublisherModel.id == publisher_id)
    return list((await session.scalars(statement)).all())


async def _create_channel_if_absent(
    session: AsyncSession,
    *,
    publisher_id: UUID,
    endpoint: ValidatedEndpoint,
    frequency: FetchFrequency,
    now: datetime,
) -> tuple[bool, UUID]:
    normalized = canonicalize_url(
        endpoint.url,
        CanonicalizationPolicy(drop_parameters=frozenset()),
    ).normalized
    existing = await session.scalar(
        select(DiscoveryChannelModel).where(
            DiscoveryChannelModel.publisher_id == publisher_id,
            DiscoveryChannelModel.endpoint_url == normalized,
        )
    )
    if existing is not None:
        return False, existing.id

    policy = _frequency_policy(frequency, now=now)
    channel = DiscoveryChannelModel(
        id=uuid7(),
        publisher_id=publisher_id,
        channel_type=endpoint.channel_type.value,
        endpoint_url=normalized,
        config={
            "discovered_by": DISCOVERY_STRATEGY_VERSION,
            "discovery_source": endpoint.source,
            "validated_item_count": endpoint.item_count,
        },
        strategy_version=DISCOVERY_STRATEGY_VERSION,
        active=True,
        next_poll_at=policy.next_poll_at,
        poll_min_seconds=policy.poll_min_seconds,
        poll_max_seconds=policy.poll_max_seconds,
        current_poll_seconds=policy.current_poll_seconds,
        consecutive_failures=0,
        created_at=now,
        updated_at=now,
    )
    session.add(channel)
    return True, channel.id


async def _publisher_source_view(
    session: AsyncSession,
    publisher: PublisherModel,
) -> PublisherSourceView:
    channel_counts = (
        await session.execute(
            select(DiscoveryChannelModel.channel_type, func.count(DiscoveryChannelModel.id))
            .where(
                DiscoveryChannelModel.publisher_id == publisher.id,
                DiscoveryChannelModel.active.is_(True),
            )
            .group_by(DiscoveryChannelModel.channel_type)
        )
    ).all()
    count_by_type = {str(channel_type): int(count) for channel_type, count in channel_counts}
    rss_count = count_by_type.get(DiscoveryChannelType.RSS.value, 0) + count_by_type.get(
        DiscoveryChannelType.ATOM.value,
        0,
    )
    sitemap_count = count_by_type.get(DiscoveryChannelType.SITEMAP.value, 0) + count_by_type.get(
        DiscoveryChannelType.NEWS_SITEMAP.value,
        0,
    )
    articles_discovered = await _publisher_discovered_count(session, publisher.id)
    articles_extracted = await session.scalar(
        select(func.count(ArticleModel.id)).where(ArticleModel.publisher_id == publisher.id)
    )
    failed_articles = await session.scalar(
        select(func.count(UrlCandidateModel.id)).where(
            UrlCandidateModel.publisher_id == publisher.id,
            UrlCandidateModel.state.in_(["failed", "rejected"]),
        )
    )
    observations = await _publisher_observation_count(session, publisher.id)
    duplicates_skipped = max(0, observations - articles_discovered)
    return PublisherSourceView(
        id=publisher.id,
        name=publisher.name,
        slug=publisher.slug,
        canonical_domain=publisher.canonical_domain,
        homepage_url=publisher.homepage_url,
        fetch_frequency=FetchFrequency(publisher.fetch_frequency),
        discovery_status=publisher.discovery_status,
        discovery_message=publisher.discovery_message,
        rss_feed_count=rss_count,
        sitemap_count=sitemap_count,
        last_fetched_at=publisher.last_fetched_at,
        articles_discovered=articles_discovered,
        articles_extracted=int(articles_extracted or 0),
        duplicates_skipped=duplicates_skipped,
        failed_articles=int(failed_articles or 0),
        current_status="active" if publisher.active else "disabled",
        created_at=publisher.created_at,
        updated_at=publisher.updated_at,
    )


async def _fetch_job_view(session: AsyncSession, job: FetchJobModel) -> FetchJobView:
    raw_publisher_ids = job.metadata_.get("publisher_ids", [])
    publisher_id_items = raw_publisher_ids if isinstance(raw_publisher_ids, list) else []
    publisher_ids = [
        UUID(str(item))
        for item in publisher_id_items
        if isinstance(item, str)
    ]
    stats = await _job_stats(session, publisher_ids, since=job.created_at)
    return FetchJobView(
        id=job.id,
        publisher_id=job.publisher_id,
        job_type=job.job_type,
        status=job.status,
        publishers_total=job.publishers_total,
        publishers_processed=stats["publishers_processed"],
        urls_discovered=stats["urls_discovered"],
        articles_queued=stats["articles_queued"],
        articles_extracted=stats["articles_extracted"],
        duplicates_skipped=stats["duplicates_skipped"],
        failed_articles=stats["failed_articles"],
        message=job.message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        updated_at=job.updated_at,
    )


async def _job_stats(
    session: AsyncSession,
    publisher_ids: Sequence[UUID],
    *,
    since: datetime,
) -> dict[str, int]:
    if not publisher_ids:
        return {
            "publishers_processed": 0,
            "urls_discovered": 0,
            "articles_queued": 0,
            "articles_extracted": 0,
            "duplicates_skipped": 0,
            "failed_articles": 0,
        }
    urls_discovered = await session.scalar(
        select(func.count(distinct(UrlCandidateModel.id))).where(
            UrlCandidateModel.publisher_id.in_(publisher_ids),
            UrlCandidateModel.created_at >= since,
        )
    )
    observations = await session.scalar(
        select(func.count(UrlDiscoveryModel.id))
        .join(UrlCandidateModel, UrlCandidateModel.id == UrlDiscoveryModel.url_candidate_id)
        .where(
            UrlCandidateModel.publisher_id.in_(publisher_ids),
            UrlDiscoveryModel.discovered_at >= since,
        )
    )
    articles_extracted = await session.scalar(
        select(func.count(ArticleModel.id)).where(
            ArticleModel.publisher_id.in_(publisher_ids),
            ArticleModel.first_observed_at >= since,
        )
    )
    failed_articles = await session.scalar(
        select(func.count(UrlCandidateModel.id)).where(
            UrlCandidateModel.publisher_id.in_(publisher_ids),
            UrlCandidateModel.state.in_(["failed", "rejected"]),
            UrlCandidateModel.last_fetch_at >= since,
        )
    )
    publishers_processed = await session.scalar(
        select(func.count(distinct(DiscoveryChannelModel.publisher_id))).where(
            DiscoveryChannelModel.publisher_id.in_(publisher_ids),
            DiscoveryChannelModel.last_polled_at >= since,
        )
    )
    discovered_count = int(urls_discovered or 0)
    observation_count = int(observations or 0)
    return {
        "publishers_processed": int(publishers_processed or 0),
        "urls_discovered": discovered_count,
        "articles_queued": discovered_count,
        "articles_extracted": int(articles_extracted or 0),
        "duplicates_skipped": max(0, observation_count - discovered_count),
        "failed_articles": int(failed_articles or 0),
    }


async def _publisher_discovered_count(session: AsyncSession, publisher_id: UUID) -> int:
    value = await session.scalar(
        select(func.count(UrlCandidateModel.id)).where(
            UrlCandidateModel.publisher_id == publisher_id
        )
    )
    return int(value or 0)


async def _publisher_observation_count(session: AsyncSession, publisher_id: UUID) -> int:
    value = await session.scalar(
        select(func.count(UrlDiscoveryModel.id))
        .join(UrlCandidateModel, UrlCandidateModel.id == UrlDiscoveryModel.url_candidate_id)
        .where(UrlCandidateModel.publisher_id == publisher_id)
    )
    return int(value or 0)


def _frequency_policy(frequency: FetchFrequency, *, now: datetime) -> FrequencyPolicy:
    seconds = {
        FetchFrequency.MANUAL: 3_600,
        FetchFrequency.EVERY_15_MINUTES: 900,
        FetchFrequency.HOURLY: 3_600,
        FetchFrequency.EVERY_6_HOURS: 21_600,
        FetchFrequency.DAILY: 86_400,
    }[frequency]
    return FrequencyPolicy(
        next_poll_at=None if frequency is FetchFrequency.MANUAL else now,
        poll_min_seconds=seconds,
        poll_max_seconds=seconds,
        current_poll_seconds=seconds,
    )


def _slugify(value: str) -> str:
    slug = "".join(
        character.lower() if character.isalnum() else "-"
        for character in value.strip()
    ).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "publisher"


async def _unique_slug(session: AsyncSession, slug: str) -> str:
    existing = set(
        (
            await session.scalars(
                select(PublisherModel.slug).where(PublisherModel.slug.like(f"{slug}%"))
            )
        ).all()
    )
    if slug not in existing:
        return slug
    suffix = 2
    while f"{slug}-{suffix}" in existing:
        suffix += 1
    return f"{slug}-{suffix}"


async def _add_outbox(session: AsyncSession, event: IntegrationEvent) -> None:
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
