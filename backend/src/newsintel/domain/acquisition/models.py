from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class DiscoveryChannelType(StrEnum):
    RSS = "rss"
    ATOM = "atom"
    SITEMAP = "sitemap"
    NEWS_SITEMAP = "news_sitemap"
    HOMEPAGE = "homepage"
    CATEGORY = "category"
    TAG = "tag"
    AUTHOR = "author"
    ARCHIVE = "archive"
    INTERNAL_LINK = "internal_link"
    SEARCH = "search"
    API = "api"
    WEBSUB = "websub"
    WEBHOOK = "webhook"


@dataclass(frozen=True, slots=True)
class DiscoveredItem:
    external_id: str | None
    url: str
    title: str | None
    published_at_raw: str | None
    channel_type: DiscoveryChannelType
    channel_url: str
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FrontierPriorityInputs:
    freshness_probability: float
    channel_historical_yield: float
    expected_update_probability: float
    recall_gap_impact: float
    source_quality_and_coverage_value: float
    event_significance: float
    publication_velocity: float
    breaking_news_probability: float
    exploration_value: float
    channel_boost: float = 0.0
    host_saturation_penalty: float = 0.0
    retry_penalty: float = 0.0
    expected_cost_penalty: float = 0.0

    def __post_init__(self) -> None:
        bounded = (
            self.freshness_probability,
            self.channel_historical_yield,
            self.expected_update_probability,
            self.recall_gap_impact,
            self.source_quality_and_coverage_value,
            self.event_significance,
            self.publication_velocity,
            self.breaking_news_probability,
            self.exploration_value,
            self.host_saturation_penalty,
            self.retry_penalty,
            self.expected_cost_penalty,
        )
        if any(value < 0 or value > 1 for value in bounded):
            raise ValueError("priority factors must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class FrontierPriority:
    score: float
    components: Mapping[str, float]
    policy_version: str

