from typing import Annotated, Never
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status

from newsintel.api.dependencies import (
    AcquisitionServiceDependency,
    PollingRepositoryDependency,
    SourceManagerAuth,
)
from newsintel.application.acquisition.dto import (
    ChannelView,
    CreateChannelCommand,
    CreatePublisherCommand,
    DiscoveryObservationResult,
    ObserveDiscoveryCommand,
    PollScheduleResponse,
    PublisherView,
)
from newsintel.application.acquisition.service import (
    ResourceConflictError,
    ResourceNotFoundError,
)

router = APIRouter(tags=["acquisition"])


def _raise_http_error(exc: Exception) -> Never:
    if isinstance(exc, ResourceNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ResourceConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    raise exc


@router.post(
    "/admin/publishers",
    response_model=PublisherView,
    status_code=status.HTTP_201_CREATED,
)
async def create_publisher(
    command: CreatePublisherCommand,
    _auth: SourceManagerAuth,
    service: AcquisitionServiceDependency,
) -> PublisherView:
    try:
        return await service.create_publisher(command)
    except (ResourceNotFoundError, ResourceConflictError) as exc:
        _raise_http_error(exc)


@router.post(
    "/admin/discovery-channels",
    response_model=ChannelView,
    status_code=status.HTTP_201_CREATED,
)
async def create_discovery_channel(
    command: CreateChannelCommand,
    _auth: SourceManagerAuth,
    service: AcquisitionServiceDependency,
) -> ChannelView:
    try:
        return await service.create_channel(command)
    except (ResourceNotFoundError, ResourceConflictError) as exc:
        _raise_http_error(exc)


@router.post(
    "/internal/discoveries",
    response_model=DiscoveryObservationResult,
    status_code=status.HTTP_202_ACCEPTED,
)
async def observe_discovery(
    command: ObserveDiscoveryCommand,
    _auth: SourceManagerAuth,
    service: AcquisitionServiceDependency,
    correlation_id: Annotated[UUID | None, Header(alias="X-Correlation-ID")] = None,
    traceparent: Annotated[str | None, Header()] = None,
) -> DiscoveryObservationResult:
    try:
        return await service.observe_discovery(
            command,
            correlation_id=correlation_id,
            traceparent=traceparent,
        )
    except (ResourceNotFoundError, ResourceConflictError) as exc:
        _raise_http_error(exc)


@router.post(
    "/admin/discovery-channels/{channel_id}/poll",
    response_model=PollScheduleResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def schedule_channel_poll(
    channel_id: UUID,
    _auth: SourceManagerAuth,
    repository: PollingRepositoryDependency,
) -> PollScheduleResponse:
    scheduled = await repository.schedule_now(channel_id)
    if not scheduled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"active channel not found: {channel_id}",
        )
    return PollScheduleResponse(channel_id=channel_id, scheduled=True)
