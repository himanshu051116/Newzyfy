from typing import Never
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from newsintel.api.dependencies import InternalAuth, SourceServiceDependency
from newsintel.application.sources.dto import (
    DiscoverPublisherCommand,
    FetchJobView,
    FetchRequestAccepted,
    PublisherDiscoveryResult,
    PublisherSourceView,
)
from newsintel.application.sources.service import (
    PublisherConflictError,
    PublisherNotFoundError,
    SourceDiscoveryError,
)

router = APIRouter(tags=["sources"])


def _raise_source_error(exc: Exception) -> Never:
    if isinstance(exc, PublisherConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, PublisherNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, SourceDiscoveryError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    raise exc


@router.get("/publishers", response_model=list[PublisherSourceView])
async def list_publishers(
    service: SourceServiceDependency,
) -> list[PublisherSourceView]:
    return await service.list_publishers()


@router.post(
    "/publishers/discover",
    response_model=PublisherDiscoveryResult,
    status_code=status.HTTP_201_CREATED,
)
async def discover_publisher(
    command: DiscoverPublisherCommand,
    _auth: InternalAuth,
    service: SourceServiceDependency,
) -> PublisherDiscoveryResult:
    try:
        return await service.discover_publisher(command)
    except (PublisherConflictError, PublisherNotFoundError, SourceDiscoveryError) as exc:
        _raise_source_error(exc)


@router.post(
    "/publishers/{publisher_id}/fetch",
    response_model=FetchRequestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def fetch_publisher(
    publisher_id: UUID,
    _auth: InternalAuth,
    service: SourceServiceDependency,
) -> FetchRequestAccepted:
    try:
        job = await service.create_fetch_job(publisher_id=publisher_id)
    except (PublisherConflictError, PublisherNotFoundError, SourceDiscoveryError) as exc:
        _raise_source_error(exc)
    return FetchRequestAccepted(job_id=job.id, status=job.status)


@router.post(
    "/fetch/all",
    response_model=FetchRequestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def fetch_all(
    _auth: InternalAuth,
    service: SourceServiceDependency,
) -> FetchRequestAccepted:
    try:
        job = await service.create_fetch_job(publisher_id=None)
    except (PublisherConflictError, PublisherNotFoundError, SourceDiscoveryError) as exc:
        _raise_source_error(exc)
    return FetchRequestAccepted(job_id=job.id, status=job.status)


@router.get("/fetch-jobs/{job_id}", response_model=FetchJobView)
async def get_fetch_job(
    job_id: UUID,
    service: SourceServiceDependency,
) -> FetchJobView:
    job = await service.get_fetch_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"fetch job not found: {job_id}",
        )
    return job


@router.delete("/publishers/{publisher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_publisher(
    publisher_id: UUID,
    _auth: InternalAuth,
    service: SourceServiceDependency,
) -> None:
    deleted = await service.delete_publisher(publisher_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"publisher not found: {publisher_id}",
        )
