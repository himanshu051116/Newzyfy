from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from newsintel.core.ids import uuid7


class IntegrationEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid7)
    event_type: str
    event_version: int = 1
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, Any]
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    producer: str
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    traceparent: str | None = None
    idempotency_key: str

