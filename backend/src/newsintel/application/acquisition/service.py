from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from newsintel.contracts.events import IntegrationEvent
from newsintel.domain.acquisition.canonicalization import (
    CanonicalizationPolicy,
    canonicalize_url,
)
from newsintel.domain.acquisition.entities import (
    DiscoveryChannel,
    Publisher,
    UrlCandidate,
    UrlDiscovery,
)
from newsintel.domain.acquisition.frontier import calculate_frontier_priority
from newsintel.domain.acquisition.policies import (
    bootstrap_priority_inputs,
    normalize_domain,
)

from .dto import (
    ChannelView,
    CreateChannelCommand,
    CreatePublisherCommand,
    DiscoveryObservationResult,
    ObserveDiscoveryCommand,
    PublisherView,
)
from .ports import UnitOfWorkFactory


class ResourceNotFoundError(LookupError):
    pass


class ResourceConflictError(ValueError):
    pass


class AcquisitionService:
    def __init__(self, unit_of_work_factory: UnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def create_publisher(self, command: CreatePublisherCommand) -> PublisherView:
        async with self._unit_of_work_factory() as uow:
            if await uow.publishers.get_by_slug(command.slug):
                raise ResourceConflictError(f"publisher slug already exists: {command.slug}")
            publisher = Publisher(
                name=command.name,
                slug=command.slug,
                canonical_domain=normalize_domain(command.canonical_domain),
            )
            await uow.publishers.add(publisher)
            await uow.outbox.add(
                IntegrationEvent(
                    event_type="publisher.created",
                    aggregate_type="publisher",
                    aggregate_id=publisher.id,
                    payload={
                        "publisher_id": str(publisher.id),
                        "slug": publisher.slug,
                        "canonical_domain": publisher.canonical_domain,
                    },
                    producer="acquisition-api",
                    idempotency_key=f"publisher.created:{publisher.id}",
                )
            )
            await uow.commit()
            return PublisherView.model_validate(publisher, from_attributes=True)

    async def create_channel(self, command: CreateChannelCommand) -> ChannelView:
        endpoint_url = canonicalize_url(
            str(command.endpoint_url),
            CanonicalizationPolicy(drop_parameters=frozenset()),
        ).normalized
        async with self._unit_of_work_factory() as uow:
            if not await uow.publishers.get(command.publisher_id):
                raise ResourceNotFoundError(f"publisher not found: {command.publisher_id}")
            if await uow.channels.get_by_endpoint(command.publisher_id, endpoint_url):
                raise ResourceConflictError("discovery channel already exists")
            channel = DiscoveryChannel(
                publisher_id=command.publisher_id,
                channel_type=command.channel_type,
                endpoint_url=endpoint_url,
                strategy_version=command.strategy_version,
                config=command.config,
                next_poll_at=datetime.now(UTC),
                poll_min_seconds=command.poll_min_seconds,
                poll_max_seconds=command.poll_max_seconds,
                current_poll_seconds=command.current_poll_seconds,
            )
            await uow.channels.add(channel)
            await uow.outbox.add(
                IntegrationEvent(
                    event_type="discovery.channel_created",
                    aggregate_type="discovery_channel",
                    aggregate_id=channel.id,
                    payload={
                        "channel_id": str(channel.id),
                        "publisher_id": str(channel.publisher_id),
                        "channel_type": channel.channel_type.value,
                        "endpoint_url": channel.endpoint_url,
                    },
                    producer="acquisition-api",
                    idempotency_key=f"discovery.channel_created:{channel.id}",
                )
            )
            await uow.commit()
            return ChannelView.model_validate(channel, from_attributes=True)

    async def observe_discovery(
        self,
        command: ObserveDiscoveryCommand,
        *,
        correlation_id: UUID | None = None,
        traceparent: str | None = None,
    ) -> DiscoveryObservationResult:
        observed_at = command.discovered_at or datetime.now(UTC)
        canonical = canonicalize_url(str(command.url))
        fingerprint = bytes.fromhex(canonical.fingerprint)
        payload_hash = (
            bytes.fromhex(command.payload_sha256) if command.payload_sha256 else None
        )

        async with self._unit_of_work_factory() as uow:
            channel = await uow.channels.get(command.channel_id)
            if not channel or not channel.active:
                raise ResourceNotFoundError(f"active channel not found: {command.channel_id}")

            priority = calculate_frontier_priority(
                bootstrap_priority_inputs(channel.channel_type)
            )
            candidate = await uow.frontier.get_by_fingerprint(fingerprint)
            candidate_created = candidate is None
            if candidate is None:
                candidate = UrlCandidate(
                    publisher_id=channel.publisher_id,
                    normalized_url=canonical.normalized,
                    url_fingerprint=fingerprint,
                    priority_score=priority.score,
                    priority_components=dict(priority.components),
                    priority_policy_version=priority.policy_version,
                    next_fetch_at=observed_at,
                    published_at=command.published_at,
                    first_discovered_at=observed_at,
                )
                await uow.frontier.add_candidate(candidate)
            else:
                updated = await uow.frontier.update_candidate_job_metadata(
                    candidate_id=candidate.id,
                    published_at=command.published_at,
                    discovered_at=observed_at,
                )
                if updated is not None:
                    candidate = updated

            observation = UrlDiscovery(
                url_candidate_id=candidate.id,
                channel_id=channel.id,
                discovered_url=str(command.url),
                discovered_at=observed_at,
                channel_position=command.channel_position,
                payload_hash=payload_hash,
            )
            observation_created = await uow.frontier.add_discovery_if_absent(observation)
            event_ids: list[UUID] = []

            if observation_created:
                event = IntegrationEvent(
                    event_type="discovery.item_observed",
                    aggregate_type="url_candidate",
                    aggregate_id=candidate.id,
                    payload={
                        "candidate_id": str(candidate.id),
                        "channel_id": str(channel.id),
                        "publisher_id": str(channel.publisher_id),
                        "url": str(command.url),
                        "normalized_url": candidate.normalized_url,
                        "external_id": command.external_id,
                        "title": command.title,
                        "published_at": (
                            command.published_at.isoformat()
                            if command.published_at
                            else None
                        ),
                        "published_at_raw": command.published_at_raw,
                        "discovered_at": observed_at.isoformat(),
                    },
                    producer="acquisition-api",
                    correlation_id=correlation_id,
                    traceparent=traceparent,
                    idempotency_key=(
                        f"discovery.item_observed:{candidate.id}:{channel.id}"
                    ),
                )
                await uow.outbox.add(event)
                event_ids.append(event.event_id)

            if candidate_created:
                event = IntegrationEvent(
                    event_type="frontier.url_admitted",
                    aggregate_type="url_candidate",
                    aggregate_id=candidate.id,
                    payload={
                        "candidate_id": str(candidate.id),
                        "publisher_id": str(channel.publisher_id),
                        "normalized_url": candidate.normalized_url,
                        "priority_score": candidate.priority_score,
                        "priority_components": candidate.priority_components,
                        "priority_policy_version": candidate.priority_policy_version,
                        "published_at": (
                            candidate.published_at.isoformat()
                            if candidate.published_at
                            else None
                        ),
                        "first_discovered_at": (
                            candidate.first_discovered_at.isoformat()
                            if candidate.first_discovered_at
                            else None
                        ),
                        "next_fetch_at": candidate.next_fetch_at.isoformat(),
                    },
                    producer="acquisition-api",
                    correlation_id=correlation_id,
                    traceparent=traceparent,
                    idempotency_key=f"frontier.url_admitted:{candidate.id}",
                )
                await uow.outbox.add(event)
                event_ids.append(event.event_id)

            await uow.commit()
            return DiscoveryObservationResult(
                candidate_id=candidate.id,
                normalized_url=candidate.normalized_url,
                priority_score=candidate.priority_score,
                priority_policy_version=candidate.priority_policy_version,
                candidate_created=candidate_created,
                channel_observation_created=observation_created,
                outbox_event_ids=tuple(event_ids),
            )


def payload_sha256(payload: bytes) -> str:
    return sha256(payload).hexdigest()
