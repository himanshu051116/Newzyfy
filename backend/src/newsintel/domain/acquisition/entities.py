from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from newsintel.core.ids import uuid7

from .models import DiscoveryChannelType


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Publisher:
    name: str
    slug: str
    canonical_domain: str
    id: UUID = field(default_factory=uuid7)
    active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class DiscoveryChannel:
    publisher_id: UUID
    channel_type: DiscoveryChannelType
    endpoint_url: str
    strategy_version: str
    id: UUID = field(default_factory=uuid7)
    config: dict[str, object] = field(default_factory=dict)
    active: bool = True
    next_poll_at: datetime | None = None
    poll_min_seconds: int = 60
    poll_max_seconds: int = 3_600
    current_poll_seconds: int = 300
    etag: str | None = None
    last_modified: str | None = None
    last_polled_at: datetime | None = None
    last_success_at: datetime | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    consecutive_failures: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class UrlCandidate:
    publisher_id: UUID
    normalized_url: str
    url_fingerprint: bytes
    priority_score: float
    priority_components: dict[str, float]
    priority_policy_version: str
    next_fetch_at: datetime
    id: UUID = field(default_factory=uuid7)
    state: str = "ready"
    published_at: datetime | None = None
    first_discovered_at: datetime | None = None
    attempt_count: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class UrlDiscovery:
    url_candidate_id: UUID
    channel_id: UUID
    discovered_url: str
    discovered_at: datetime
    id: UUID = field(default_factory=uuid7)
    channel_position: int | None = None
    payload_hash: bytes | None = None
