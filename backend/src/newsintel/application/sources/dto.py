from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FetchFrequency(StrEnum):
    MANUAL = "manual"
    EVERY_15_MINUTES = "every_15_minutes"
    HOURLY = "hourly"
    EVERY_6_HOURS = "every_6_hours"
    DAILY = "daily"


class DiscoverPublisherCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    publisher_name: str = Field(min_length=1, max_length=300)
    website_url: str = Field(min_length=1, max_length=2_000)
    fetch_frequency: FetchFrequency = FetchFrequency.HOURLY
    manual_endpoints: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("manual_endpoints")
    @classmethod
    def strip_manual_endpoints(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class DiscoveredChannelView(BaseModel):
    id: UUID
    endpoint_url: str
    channel_type: str
    source: str
    item_count: int
    created: bool


class PublisherSourceView(BaseModel):
    id: UUID
    name: str
    slug: str
    canonical_domain: str
    homepage_url: str | None
    fetch_frequency: FetchFrequency
    discovery_status: str
    discovery_message: str | None
    rss_feed_count: int
    sitemap_count: int
    last_fetched_at: datetime | None
    articles_discovered: int
    articles_extracted: int
    duplicates_skipped: int
    failed_articles: int
    current_status: str
    created_at: datetime
    updated_at: datetime


class PublisherDiscoveryResult(BaseModel):
    publisher: PublisherSourceView
    channels: list[DiscoveredChannelView]
    attempted_endpoint_count: int
    valid_endpoint_count: int
    invalid_endpoint_count: int
    manual_fallback_available: bool


class FetchJobView(BaseModel):
    id: UUID
    publisher_id: UUID | None
    job_type: str
    status: str
    publishers_total: int
    publishers_processed: int
    urls_discovered: int
    articles_queued: int
    articles_extracted: int
    duplicates_skipped: int
    failed_articles: int
    message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class FetchRequestAccepted(BaseModel):
    job_id: UUID
    status: str
