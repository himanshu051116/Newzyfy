from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text

from newsintel.infrastructure.db.models import (
    ArticleModel,
    OutboxEventModel,
    UrlCandidateModel,
)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str = "news-intelligence-api"


class PlatformStatusResponse(BaseModel):
    status: str
    database_revision: str | None
    article_count: int
    last_committed_article_at: datetime | None
    queue_depth: int
    oldest_pending_candidate_at: datetime | None
    candidate_stages: dict[str, int]
    pending_outbox_events: int


@router.get("/health/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
async def ready(request: Request) -> HealthResponse:
    database = request.app.state.database
    try:
        async with database.session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    return HealthResponse(status="ready")


@router.get("/status", response_model=PlatformStatusResponse)
async def platform_status(request: Request) -> PlatformStatusResponse:
    database = request.app.state.database
    async with database.session_factory() as session:
        revision = await session.scalar(
            text(
                "SELECT version_num FROM alembic_version "
                "ORDER BY version_num DESC LIMIT 1"
            )
        )
        article_count = int(
            await session.scalar(select(func.count(ArticleModel.id))) or 0
        )
        last_committed_article_at = await session.scalar(
            select(func.max(ArticleModel.created_at))
        )
        queue_depth = int(
            await session.scalar(
                select(func.count(UrlCandidateModel.id)).where(
                    UrlCandidateModel.processing_stage.in_(
                        [
                            "queued",
                            "leased",
                            "fetching",
                            "fetched",
                            "extracting",
                            "extracted",
                            "validated",
                            "persisting",
                            "retryable_failure",
                        ]
                    )
                )
            )
            or 0
        )
        oldest_pending_candidate_at = await session.scalar(
            select(func.min(UrlCandidateModel.first_discovered_at)).where(
                UrlCandidateModel.processing_stage.in_(
                    [
                        "queued",
                        "leased",
                        "fetching",
                        "fetched",
                        "extracting",
                        "extracted",
                        "validated",
                        "persisting",
                        "retryable_failure",
                    ]
                )
            )
        )
        stage_rows = (
            await session.execute(
                select(
                    UrlCandidateModel.processing_stage,
                    func.count(UrlCandidateModel.id),
                ).group_by(UrlCandidateModel.processing_stage)
            )
        ).all()
        pending_outbox_events = int(
            await session.scalar(
                select(func.count(OutboxEventModel.id)).where(
                    OutboxEventModel.published_at.is_(None)
                )
            )
            or 0
        )
    return PlatformStatusResponse(
        status="ok",
        database_revision=str(revision) if revision else None,
        article_count=article_count,
        last_committed_article_at=last_committed_article_at,
        queue_depth=queue_depth,
        oldest_pending_candidate_at=oldest_pending_candidate_at,
        candidate_stages={str(stage): int(count) for stage, count in stage_rows},
        pending_outbox_events=pending_outbox_events,
    )


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(request: Request) -> str:
    status_view = await platform_status(request)
    lines = [
        "# HELP newsintel_articles_committed_total Stored article records.",
        "# TYPE newsintel_articles_committed_total gauge",
        f"newsintel_articles_committed_total {status_view.article_count}",
        "# HELP newsintel_queue_depth URL candidates not yet terminal.",
        "# TYPE newsintel_queue_depth gauge",
        f"newsintel_queue_depth {status_view.queue_depth}",
        "# HELP newsintel_outbox_pending_events Unpublished transactional outbox events.",
        "# TYPE newsintel_outbox_pending_events gauge",
        f"newsintel_outbox_pending_events {status_view.pending_outbox_events}",
        "# HELP newsintel_candidate_stage_count URL candidates by processing stage.",
        "# TYPE newsintel_candidate_stage_count gauge",
    ]
    for stage, count in sorted(status_view.candidate_stages.items()):
        escaped_stage = stage.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'newsintel_candidate_stage_count{{stage="{escaped_stage}"}} {count}')
    return "\n".join(lines) + "\n"
