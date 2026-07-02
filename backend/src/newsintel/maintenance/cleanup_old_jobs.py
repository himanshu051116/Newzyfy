import argparse
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.sql.elements import ColumnElement

from newsintel.application.articles.processing import (
    ArticleProcessingStage,
    UrlCandidateState,
)
from newsintel.core.config import get_settings
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.models import (
    FetchJobModel,
    PublisherModel,
    UrlCandidateModel,
)
from newsintel.infrastructure.db.session import Database

logger = structlog.get_logger(__name__)

PENDING_CANDIDATE_STATES = (
    UrlCandidateState.READY.value,
    UrlCandidateState.RETRY.value,
    UrlCandidateState.LEASED.value,
)
PENDING_FETCH_JOB_STATUSES = ("scheduled", "running")


@dataclass(frozen=True, slots=True)
class CleanupResult:
    publisher_match: str
    older_than_hours: int
    cutoff: datetime
    applied: bool
    action: str
    invalid_only: bool
    stale_candidate_count: int
    stale_fetch_job_count: int


async def cleanup_old_jobs(
    *,
    database: Database,
    publisher_match: str,
    older_than_hours: int,
    action: str,
    invalid_only: bool,
    apply: bool,
) -> CleanupResult:
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=older_than_hours)
    match_pattern = f"%{publisher_match.lower()}%"
    stage = (
        ArticleProcessingStage.PERMANENT_FAILURE
        if action == "permanent-failure"
        else ArticleProcessingStage.REJECTED
    )
    state = (
        UrlCandidateState.FAILED.value
        if action == "permanent-failure"
        else UrlCandidateState.REJECTED.value
    )
    stale_reason = (
        "old_job_rejected: development cleanup marked stale invalid URL candidate "
        f"older than {older_than_hours}h; action={action}; "
        f"invalid_only={invalid_only}; cutoff={cutoff.isoformat()}"
    )

    async with database.session_factory() as session, session.begin():
        publisher_scope = or_(
            func.lower(PublisherModel.name).like(match_pattern),
            func.lower(PublisherModel.canonical_domain).like(match_pattern),
        )
        bbc_url_scope = _url_matches_publisher(publisher_match)
        age_reference = func.coalesce(
            UrlCandidateModel.published_at,
            UrlCandidateModel.first_discovered_at,
            UrlCandidateModel.created_at,
        )
        stale_candidate_filter = and_(
            UrlCandidateModel.state.in_(PENDING_CANDIDATE_STATES),
            age_reference < cutoff,
            or_(publisher_scope, bbc_url_scope),
        )
        if invalid_only:
            stale_candidate_filter = and_(
                stale_candidate_filter,
                _invalid_backlog_url_scope(),
            )
        candidate_scope = (
            select(UrlCandidateModel.id)
            .join(PublisherModel, PublisherModel.id == UrlCandidateModel.publisher_id)
            .where(stale_candidate_filter)
        )
        stale_candidate_count = int(
            await session.scalar(
                select(func.count()).select_from(candidate_scope.subquery())
            )
            or 0
        )

        publisher_ids_scope = select(PublisherModel.id).where(publisher_scope)
        stale_fetch_job_filter = and_(
            FetchJobModel.publisher_id.in_(publisher_ids_scope),
            FetchJobModel.status.in_(PENDING_FETCH_JOB_STATUSES),
            FetchJobModel.created_at < cutoff,
        )
        stale_fetch_job_count = int(
            await session.scalar(
                select(func.count(FetchJobModel.id)).where(stale_fetch_job_filter)
            )
            or 0
        )

        if apply:
            await session.execute(
                update(UrlCandidateModel)
                .where(UrlCandidateModel.id.in_(candidate_scope))
                .values(
                    state=state,
                    processing_stage=stage.value,
                    lease_owner=None,
                    lease_expires_at=None,
                    current_worker=None,
                    last_fetch_at=now,
                    last_error=stale_reason,
                    last_failure_code="development_cleanup",
                    last_failure_message=stale_reason,
                    processing_completed_at=now,
                    updated_at=now,
                )
            )
            await session.execute(
                update(FetchJobModel)
                .where(stale_fetch_job_filter)
                .values(
                    status="completed",
                    completed_at=now,
                    updated_at=now,
                    message=(
                        "Development cleanup completed this stale fetch job without "
                        "deleting publishers, channels, articles, versions, events, "
                        "or claims."
                    ),
                )
            )

    result = CleanupResult(
        publisher_match=publisher_match,
        older_than_hours=older_than_hours,
        cutoff=cutoff,
        applied=apply,
        action=action,
        invalid_only=invalid_only,
        stale_candidate_count=stale_candidate_count,
        stale_fetch_job_count=stale_fetch_job_count,
    )
    logger.info(
        "old_job_cleanup_completed" if apply else "old_job_cleanup_dry_run",
        publisher_match=publisher_match,
        older_than_hours=older_than_hours,
        action=action,
        invalid_only=invalid_only,
        cutoff=cutoff.isoformat(),
        stale_candidate_count=stale_candidate_count,
        stale_fetch_job_count=stale_fetch_job_count,
    )
    return result


def _invalid_backlog_url_scope() -> ColumnElement[bool]:
    lowered = func.lower(UrlCandidateModel.normalized_url)
    return or_(
        lowered.like("%/archive/%"),
        lowered.like("%/archives/%"),
        lowered.like("%/topics/%"),
        lowered.like("%/topic/%"),
        lowered.like("%/multimedia/%"),
        lowered.like("%/video/%"),
        lowered.like("%/videos/%"),
        lowered.like("%/gallery/%"),
        lowered.like("%/search/%"),
        lowered.like("%/tag/%"),
        lowered.like("%/tags/%"),
        lowered.like("%/author/%"),
        lowered.like("%/authors/%"),
    )


def _url_matches_publisher(publisher_match: str) -> ColumnElement[bool]:
    lowered = publisher_match.lower()
    if lowered == "bbc":
        return or_(
            func.lower(UrlCandidateModel.normalized_url).like("%://bbc.%"),
            func.lower(UrlCandidateModel.normalized_url).like("%://www.bbc.%"),
            func.lower(UrlCandidateModel.normalized_url).like("%://news.bbc.%"),
            func.lower(UrlCandidateModel.normalized_url).like("%://%.bbc.%"),
            func.lower(UrlCandidateModel.normalized_url).like("%://%.bbci.%"),
        )
    return func.lower(UrlCandidateModel.normalized_url).like(f"%{lowered}%")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Safely clean stale development article/discovery jobs without deleting "
            "publishers, channels, articles, versions, events, or claims."
        )
    )
    parser.add_argument(
        "--publisher",
        default="BBC",
        help="Publisher name/domain/URL token to target. Defaults to BBC.",
    )
    parser.add_argument(
        "--older-than-hours",
        type=int,
        default=48,
        help="Only clean pending jobs older than this many hours. Defaults to 48.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually mark stale jobs. Omit for a dry run.",
    )
    parser.add_argument(
        "--action",
        choices=("reject", "permanent-failure"),
        default="reject",
        help="How to mark stale candidates. Defaults to reject.",
    )
    parser.add_argument(
        "--invalid-only",
        action="store_true",
        help=(
            "Only clean likely invalid backlog URLs such as archive, topic, tag, "
            "author, search, video, multimedia, and gallery pages."
        ),
    )
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.older_than_hours < 1:
        parser.error("--older-than-hours must be at least 1")

    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    try:
        result = await cleanup_old_jobs(
            database=database,
            publisher_match=str(args.publisher),
            older_than_hours=int(args.older_than_hours),
            action=str(args.action),
            invalid_only=bool(args.invalid_only),
            apply=bool(args.apply),
        )
    finally:
        await database.dispose()

    mode = "APPLIED" if result.applied else "DRY RUN"
    print(
        "\n".join(
            [
                f"{mode}: stale {result.publisher_match} cleanup",
                f"Cutoff: {result.cutoff.isoformat()}",
                f"Action: {result.action}",
                f"Invalid-only: {result.invalid_only}",
                f"URL candidates to reject: {result.stale_candidate_count}",
                f"Fetch jobs to mark completed: {result.stale_fetch_job_count}",
                (
                    "No database rows were changed. Re-run with --apply to clean."
                    if not result.applied
                    else "Cleanup applied. No publisher/content/evidence records were deleted."
                ),
            ]
        )
    )
    return 0


def run() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    run()
