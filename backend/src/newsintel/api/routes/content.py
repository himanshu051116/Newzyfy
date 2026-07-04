from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from newsintel.api.dependencies import AnalystAuth, ArticleQueryServiceDependency, ViewerAuth
from newsintel.application.articles.dto import (
    ArticleClaimView,
    ArticleDetailView,
    ArticleSummaryView,
    EventDetailView,
)

router = APIRouter(tags=["content"])


@router.get("/articles", response_model=list[ArticleSummaryView])
async def list_articles(
    _auth: ViewerAuth,
    service: ArticleQueryServiceDependency,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ArticleSummaryView]:
    return await service.list_articles(limit=limit)


@router.get("/articles/{article_id}", response_model=ArticleDetailView)
async def get_article(
    article_id: UUID,
    _auth: ViewerAuth,
    service: ArticleQueryServiceDependency,
) -> ArticleDetailView:
    article = await service.get_article(article_id)
    if article is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"article not found: {article_id}",
        )
    return article


@router.get("/articles/{article_id}/claims", response_model=list[ArticleClaimView])
async def get_article_claims(
    article_id: UUID,
    _auth: AnalystAuth,
    service: ArticleQueryServiceDependency,
) -> list[ArticleClaimView]:
    claims = await service.get_article_claims(article_id)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"article not found: {article_id}",
        )
    return claims


@router.get("/events/{event_id}", response_model=EventDetailView)
async def get_event(
    event_id: UUID,
    _auth: ViewerAuth,
    service: ArticleQueryServiceDependency,
) -> EventDetailView:
    event = await service.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"event not found: {event_id}",
        )
    return event
