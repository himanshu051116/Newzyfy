from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from newsintel.domain.acquisition.models import DiscoveryChannelType


class CreatePublisherCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=300)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
    canonical_domain: str = Field(min_length=1, max_length=253)


class PublisherView(BaseModel):
    id: UUID
    name: str
    slug: str
    canonical_domain: str
    active: bool
    created_at: datetime


class CreateChannelCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    publisher_id: UUID
    channel_type: DiscoveryChannelType
    endpoint_url: HttpUrl
    strategy_version: str = Field(default="bootstrap-v1", min_length=1, max_length=100)
    config: dict[str, object] = Field(default_factory=dict)
    poll_min_seconds: int = Field(default=60, ge=15, le=86_400)
    poll_max_seconds: int = Field(default=3_600, ge=30, le=604_800)
    current_poll_seconds: int = Field(default=300, ge=15, le=604_800)

    @model_validator(mode="after")
    def validate_poll_intervals(self) -> "CreateChannelCommand":
        if self.poll_min_seconds > self.poll_max_seconds:
            raise ValueError("poll_min_seconds cannot exceed poll_max_seconds")
        if not self.poll_min_seconds <= self.current_poll_seconds <= self.poll_max_seconds:
            raise ValueError(
                "current_poll_seconds must be between poll_min_seconds and poll_max_seconds"
            )
        return self


class ChannelView(BaseModel):
    id: UUID
    publisher_id: UUID
    channel_type: DiscoveryChannelType
    endpoint_url: str
    strategy_version: str
    active: bool
    next_poll_at: datetime | None
    poll_min_seconds: int
    poll_max_seconds: int
    current_poll_seconds: int
    consecutive_failures: int
    created_at: datetime


class ObserveDiscoveryCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    channel_id: UUID
    url: HttpUrl
    external_id: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=1_000)
    published_at: datetime | None = None
    published_at_raw: str | None = Field(default=None, max_length=200)
    discovered_at: datetime | None = None
    channel_position: int | None = Field(default=None, ge=0)
    payload_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-fA-F0-9]{64}$",
    )


class DiscoveryObservationResult(BaseModel):
    candidate_id: UUID
    normalized_url: str
    priority_score: float
    priority_policy_version: str
    candidate_created: bool
    channel_observation_created: bool
    outbox_event_ids: tuple[UUID, ...]


class PollScheduleResponse(BaseModel):
    channel_id: UUID
    scheduled: bool
