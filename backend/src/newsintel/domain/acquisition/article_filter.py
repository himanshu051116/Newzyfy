import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit

DEFAULT_RECENT_WINDOW_HOURS = 48
DEFAULT_MAX_NEW_URLS_PER_CHANNEL_POLL = 200

_DATE_PATH_PATTERN = re.compile(
    r"/(?:20\d{2}[/_-](?:0?[1-9]|1[0-2])[/_-](?:0?[1-9]|[12]\d|3[01])|"
    r"(?:0?[1-9]|[12]\d|3[01])[/_-](?:0?[1-9]|1[0-2])[/_-]20\d{2})/"
)
_ARTICLE_HINT_PATTERN = re.compile(
    r"(?:/news/|/article/|/articles/|/story/|/stories/|/world/|/business/|"
    r"/technology/|/tech/|/science/|/politics/|/sports/|/health/|/india/|"
    r"/opinion/|/analysis/|/markets/|/economy/)"
)
_EXCLUDED_SEGMENTS = {
    "about",
    "archive",
    "archives",
    "author",
    "authors",
    "category",
    "contact",
    "gallery",
    "live-tv",
    "multimedia",
    "newsletter",
    "photos",
    "podcast",
    "privacy",
    "search",
    "sitemap",
    "tag",
    "tags",
    "terms",
    "topic",
    "topics",
    "video",
    "videos",
    "web-stories",
}
_ARTICLE_SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){3,}")


class UrlRejectionReason(StrEnum):
    TOO_OLD = "too_old"
    FUTURE_DATED = "future_dated"
    NON_ARTICLE_PATH = "non_article_path"
    EXCLUDED_SECTION = "excluded_section"
    MISSING_PUBLICATION_DATE = "missing_publication_date"


@dataclass(frozen=True, slots=True)
class ArticleUrlDecision:
    accepted: bool
    reason: UrlRejectionReason | None
    published_at: datetime | None
    policy_version: str = "recent-article-url-filter-v1"


def should_admit_article_url(
    url: str,
    *,
    published_at: datetime | None,
    observed_at: datetime,
    recent_window_hours: int = DEFAULT_RECENT_WINDOW_HOURS,
    require_publication_date: bool = True,
) -> ArticleUrlDecision:
    normalized_published_at = _normalize_datetime(published_at)
    normalized_observed_at = _normalize_datetime(observed_at) or datetime.now(UTC)
    if require_publication_date and normalized_published_at is None:
        return ArticleUrlDecision(
            accepted=False,
            reason=UrlRejectionReason.MISSING_PUBLICATION_DATE,
            published_at=None,
        )
    if normalized_published_at is not None:
        if normalized_published_at > normalized_observed_at + timedelta(hours=2):
            return ArticleUrlDecision(
                accepted=False,
                reason=UrlRejectionReason.FUTURE_DATED,
                published_at=normalized_published_at,
            )
        cutoff = normalized_observed_at - timedelta(hours=recent_window_hours)
        if normalized_published_at < cutoff:
            return ArticleUrlDecision(
                accepted=False,
                reason=UrlRejectionReason.TOO_OLD,
                published_at=normalized_published_at,
            )

    if _has_excluded_segment(url):
        return ArticleUrlDecision(
            accepted=False,
            reason=UrlRejectionReason.EXCLUDED_SECTION,
            published_at=normalized_published_at,
        )
    if not looks_like_article_url(url):
        return ArticleUrlDecision(
            accepted=False,
            reason=UrlRejectionReason.NON_ARTICLE_PATH,
            published_at=normalized_published_at,
        )
    return ArticleUrlDecision(
        accepted=True,
        reason=None,
        published_at=normalized_published_at,
    )


def looks_like_article_url(url: str) -> bool:
    parsed = urlsplit(url)
    path = parsed.path.lower().strip("/")
    if not path:
        return False
    if path.endswith((".xml", ".rss", ".json", ".jpg", ".jpeg", ".png", ".webp", ".mp4")):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    if _has_excluded_segment(url):
        return False
    last_segment = segments[-1]
    if _ARTICLE_SLUG_PATTERN.search(last_segment):
        return True
    if _DATE_PATH_PATTERN.search(f"/{path}/"):
        return True
    if _ARTICLE_HINT_PATTERN.search(f"/{path}/") and len(segments) >= 2:
        return True
    return False


def _has_excluded_segment(url: str) -> bool:
    parsed = urlsplit(url)
    segments = {segment.lower() for segment in parsed.path.split("/") if segment}
    return bool(segments & _EXCLUDED_SEGMENTS)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
