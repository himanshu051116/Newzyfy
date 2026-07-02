from typing import cast
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.articles.dto import (
    ArticleClaimView,
    ArticleDetailView,
    ArticleSummaryView,
    ArticleVersionView,
    ClaimEvidenceLinkView,
    ClaimVerificationView,
    EventDetailView,
)
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleModel,
    ArticleVersionModel,
    ClaimEvidenceLinkModel,
    ClaimVerificationModel,
    EventModel,
)


class ArticleQueryService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_articles(self, *, limit: int = 50) -> list[ArticleSummaryView]:
        async with self._session_factory() as session:
            articles = (
                await session.scalars(
                    select(ArticleModel)
                    .order_by(desc(ArticleModel.first_observed_at))
                    .limit(limit)
                )
            ).all()
            return [
                await self._summary_for_article(session, article) for article in articles
            ]

    async def get_article(self, article_id: UUID) -> ArticleDetailView | None:
        async with self._session_factory() as session:
            article = await session.get(ArticleModel, article_id)
            if article is None:
                return None
            latest = await self._latest_version(session, article.id)
            return ArticleDetailView(
                id=article.id,
                event_id=article.event_id,
                publisher_id=article.publisher_id,
                canonical_url=article.canonical_url,
                title=article.title,
                language=article.language,
                published_at=article.published_at,
                first_observed_at=article.first_observed_at,
                created_at=article.created_at,
                updated_at=article.updated_at,
                latest_version=_version_view(latest) if latest else None,
            )

    async def get_event(self, event_id: UUID) -> EventDetailView | None:
        async with self._session_factory() as session:
            event = await session.get(EventModel, event_id)
            if event is None:
                return None
            articles = (
                await session.scalars(
                    select(ArticleModel)
                    .where(ArticleModel.event_id == event.id)
                    .order_by(desc(ArticleModel.first_observed_at))
                )
            ).all()
            return EventDetailView(
                id=event.id,
                slug=event.slug,
                title=event.title,
                lifecycle_status=event.lifecycle_status,
                assignment_status=event.assignment_status,
                first_detected_at=event.first_detected_at,
                last_material_change_at=event.last_material_change_at,
                metadata=event.metadata_,
                created_at=event.created_at,
                updated_at=event.updated_at,
                articles=[
                    await self._summary_for_article(session, article)
                    for article in articles
                ],
            )

    async def get_article_claims(self, article_id: UUID) -> list[ArticleClaimView] | None:
        async with self._session_factory() as session:
            article = await session.get(ArticleModel, article_id)
            if article is None:
                return None
            claims = (
                await session.scalars(
                    select(ArticleClaimModel)
                    .where(ArticleClaimModel.article_id == article_id)
                    .order_by(
                        ArticleClaimModel.created_at,
                        ArticleClaimModel.sentence_index,
                    )
                )
            ).all()
            return [
                await self._claim_view(session, claim)
                for claim in claims
            ]

    async def _summary_for_article(
        self,
        session: AsyncSession,
        article: ArticleModel,
    ) -> ArticleSummaryView:
        latest = await self._latest_version(session, article.id)
        return ArticleSummaryView(
            id=article.id,
            event_id=article.event_id,
            publisher_id=article.publisher_id,
            canonical_url=article.canonical_url,
            title=article.title,
            language=article.language,
            published_at=article.published_at,
            first_observed_at=article.first_observed_at,
            latest_version_id=latest.id if latest else None,
            latest_version_number=latest.version_number if latest else None,
            latest_extraction_method=latest.extraction_method if latest else None,
            latest_extraction_warnings=(
                list(latest.extraction_warnings) if latest else []
            ),
            latest_extraction_quality_score=(
                _extraction_quality_score(latest) if latest else None
            ),
            word_count=_word_count(latest) if latest else None,
        )

    async def _latest_version(
        self,
        session: AsyncSession,
        article_id: UUID,
    ) -> ArticleVersionModel | None:
        return cast(
            ArticleVersionModel | None,
            await session.scalar(
                select(ArticleVersionModel)
                .where(ArticleVersionModel.article_id == article_id)
                .order_by(desc(ArticleVersionModel.version_number))
                .limit(1)
            ),
        )

    async def _claim_view(
        self,
        session: AsyncSession,
        claim: ArticleClaimModel,
    ) -> ArticleClaimView:
        evidence_links = (
            await session.scalars(
                select(ClaimEvidenceLinkModel)
                .where(ClaimEvidenceLinkModel.claim_id == claim.id)
                .order_by(ClaimEvidenceLinkModel.retrieved_at)
            )
        ).all()
        verification = await session.scalar(
            select(ClaimVerificationModel)
            .where(ClaimVerificationModel.claim_id == claim.id)
            .order_by(desc(ClaimVerificationModel.created_at))
            .limit(1)
        )
        return ArticleClaimView(
            id=claim.id,
            article_id=claim.article_id,
            article_version_id=claim.article_version_id,
            claim_text=claim.claim_text,
            claim_sha256=claim.claim_sha256,
            sentence_index=claim.sentence_index,
            extractor_version=claim.extractor_version,
            extraction_features=claim.extraction_features,
            created_at=claim.created_at,
            evidence_links=[
                ClaimEvidenceLinkView(
                    id=link.id,
                    source_url=link.source_url,
                    source_type=link.source_type,
                    relationship=link.relationship,
                    retrieved_at=link.retrieved_at,
                    similarity_score=link.similarity_score,
                    independence_score=link.independence_score,
                    metadata=link.metadata_,
                )
                for link in evidence_links
            ],
            latest_verification=(
                ClaimVerificationView(
                    id=verification.id,
                    label=verification.label,
                    confidence_score=verification.confidence_score,
                    methodology_version=verification.methodology_version,
                    confidence_factors=verification.confidence_factors,
                    reasoning_trace=verification.reasoning_trace,
                    created_at=verification.created_at,
                )
                if verification
                else None
            ),
        )


def _version_view(version: ArticleVersionModel) -> ArticleVersionView:
    return ArticleVersionView(
        id=version.id,
        version_number=version.version_number,
        source_url=version.source_url,
        final_url=version.final_url,
        title=version.title,
        byline=version.byline,
        language=version.language,
        published_at=version.published_at,
        retrieved_at=version.retrieved_at,
        content_sha256=version.content_sha256,
        extraction_method=version.extraction_method,
        extraction_warnings=version.extraction_warnings,
        extraction_quality_score=_extraction_quality_score(version),
        raw_artifact_uri=_raw_artifact_uri(version),
        word_count=_word_count(version),
        text_content=version.text_content,
        created_at=version.created_at,
    )


def _word_count(version: ArticleVersionModel | None) -> int:
    if version is None:
        return 0
    metadata_word_count = version.metadata_.get("word_count")
    if isinstance(metadata_word_count, int):
        return metadata_word_count
    return len(version.text_content.split())


def _extraction_quality_score(version: ArticleVersionModel | None) -> float | None:
    if version is None:
        return None
    value = version.metadata_.get("extraction_quality_score")
    if isinstance(value, int | float):
        return float(value)
    return None


def _raw_artifact_uri(version: ArticleVersionModel) -> str | None:
    artifact = version.metadata_.get("raw_fetch_artifact")
    if not isinstance(artifact, dict):
        return None
    uri = artifact.get("artifact_uri")
    return uri if isinstance(uri, str) else None
