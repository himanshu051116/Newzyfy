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
    r"/opinion/|/analysis/|/markets/|/economy/|/live/|/liveblog/|"
    r"/explainers?/|/investigations?/|/fact-?check/|/press-release/|"
    r"/video/|/videos/|/photo/|/photos/|/gallery/)"
)
_NAVIGATION_SEGMENTS = {
    "about",
    "archive",
    "archives",
    "author",
    "authors",
    "category",
    "contact",
    "live-tv",
    "multimedia",
    "newsletter",
    "podcast",
    "privacy",
    "search",
    "sitemap",
    "tag",
    "tags",
    "terms",
    "topic",
    "topics",
    "web-stories",
}
_ARTICLE_SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){3,}")
_THE_HINDU_ARTICLE_PATTERN = re.compile(r"/article\d+\.ece$")
_REUTERS_ARTICLE_PATTERN = re.compile(r"/world/.+-\d{4}-\d{2}-\d{2}/?$")
_INDIAN_EXPRESS_ARTICLE_PATTERN = re.compile(r"/article/.+/\d+/?$")
_BBC_ARTICLE_ID_PATTERN = re.compile(r"/(?:news|sport|worklife|future)/[a-z0-9-]+-\d+/?$")
_AL_JAZEERA_DATE_PATTERN = re.compile(
    r"/(?:news|sports|features|opinions|economy|program)/"
    r"20\d{2}/\d{1,2}/\d{1,2}/[^/]+/?$"
)


class UrlContentType(StrEnum):
    STANDARD_ARTICLE = "standard_article"
    BREAKING_NEWS = "breaking_news"
    LIVEBLOG = "liveblog"
    EXPLAINER = "explainer"
    ANALYSIS = "analysis"
    OPINION = "opinion"
    INVESTIGATION = "investigation"
    FACT_CHECK = "fact_check"
    PRESS_RELEASE = "press_release"
    VIDEO_REPORT = "video_report"
    PHOTO_STORY = "photo_story"
    SECTION_PAGE = "section_page"
    TOPIC_PAGE = "topic_page"
    AUTHOR_PAGE = "author_page"
    TAG_PAGE = "tag_page"
    SEARCH_PAGE = "search_page"
    ARCHIVE_PAGE = "archive_page"
    HOMEPAGE = "homepage"
    INVALID_PAGE = "invalid_page"


FETCHABLE_URL_TYPES = frozenset(
    {
        UrlContentType.STANDARD_ARTICLE,
        UrlContentType.BREAKING_NEWS,
        UrlContentType.LIVEBLOG,
        UrlContentType.EXPLAINER,
        UrlContentType.ANALYSIS,
        UrlContentType.OPINION,
        UrlContentType.INVESTIGATION,
        UrlContentType.FACT_CHECK,
        UrlContentType.PRESS_RELEASE,
        UrlContentType.VIDEO_REPORT,
        UrlContentType.PHOTO_STORY,
    }
)


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
    url_type: UrlContentType = UrlContentType.INVALID_PAGE
    confidence: float = 0.0
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
    classification = classify_article_url(url)
    if require_publication_date and normalized_published_at is None:
        return ArticleUrlDecision(
            accepted=False,
            reason=UrlRejectionReason.MISSING_PUBLICATION_DATE,
            published_at=None,
            url_type=classification.url_type,
            confidence=classification.confidence,
        )
    if normalized_published_at is not None:
        if normalized_published_at > normalized_observed_at + timedelta(hours=2):
            return ArticleUrlDecision(
                accepted=False,
                reason=UrlRejectionReason.FUTURE_DATED,
                published_at=normalized_published_at,
                url_type=classification.url_type,
                confidence=classification.confidence,
            )
        cutoff = normalized_observed_at - timedelta(hours=recent_window_hours)
        if normalized_published_at < cutoff:
            return ArticleUrlDecision(
                accepted=False,
                reason=UrlRejectionReason.TOO_OLD,
                published_at=normalized_published_at,
                url_type=classification.url_type,
                confidence=classification.confidence,
            )

    if classification.url_type in _NAVIGATION_URL_TYPES:
        return ArticleUrlDecision(
            accepted=False,
            reason=UrlRejectionReason.EXCLUDED_SECTION,
            published_at=normalized_published_at,
            url_type=classification.url_type,
            confidence=classification.confidence,
        )
    if classification.url_type not in FETCHABLE_URL_TYPES:
        return ArticleUrlDecision(
            accepted=False,
            reason=UrlRejectionReason.NON_ARTICLE_PATH,
            published_at=normalized_published_at,
            url_type=classification.url_type,
            confidence=classification.confidence,
        )
    return ArticleUrlDecision(
        accepted=True,
        reason=None,
        published_at=normalized_published_at,
        url_type=classification.url_type,
        confidence=classification.confidence,
    )


def looks_like_article_url(url: str) -> bool:
    return classify_article_url(url).url_type in FETCHABLE_URL_TYPES


@dataclass(frozen=True, slots=True)
class UrlClassification:
    url_type: UrlContentType
    confidence: float
    reason: str
    policy_version: str = "url-type-classifier-v1"


_NAVIGATION_URL_TYPES = frozenset(
    {
        UrlContentType.SECTION_PAGE,
        UrlContentType.TOPIC_PAGE,
        UrlContentType.AUTHOR_PAGE,
        UrlContentType.TAG_PAGE,
        UrlContentType.SEARCH_PAGE,
        UrlContentType.ARCHIVE_PAGE,
        UrlContentType.HOMEPAGE,
    }
)


def classify_article_url(url: str) -> UrlClassification:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return UrlClassification(
            UrlContentType.INVALID_PAGE,
            0.99,
            "missing_or_unsupported_scheme_or_host",
        )
    raw_path = parsed.path.lower()
    path = raw_path.strip("/")
    if not path:
        return UrlClassification(UrlContentType.HOMEPAGE, 0.99, "empty_path")
    if path.endswith((".xml", ".rss", ".json", ".jpg", ".jpeg", ".png", ".webp", ".mp4")):
        return UrlClassification(UrlContentType.INVALID_PAGE, 0.95, "asset_or_feed_path")
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return UrlClassification(UrlContentType.HOMEPAGE, 0.99, "empty_segments")
    publisher_type = _classify_publisher_specific(
        parsed.netloc.lower(),
        path,
        segments,
        raw_path=raw_path,
    )
    if publisher_type is not None:
        return publisher_type

    navigation_type = _navigation_type_for_segments(
        segments,
        query=parsed.query,
        raw_path=raw_path,
    )
    if navigation_type is not None:
        return UrlClassification(navigation_type, 0.95, "navigation_segment")

    semantic_type = _semantic_content_type(segments)
    if semantic_type is not None and _has_article_specificity(path, segments):
        return UrlClassification(semantic_type, 0.88, "semantic_article_path")

    last_segment = segments[-1]
    if _ARTICLE_SLUG_PATTERN.search(last_segment):
        return UrlClassification(UrlContentType.STANDARD_ARTICLE, 0.82, "slug_pattern")
    if _DATE_PATH_PATTERN.search(f"/{path}/"):
        return UrlClassification(UrlContentType.STANDARD_ARTICLE, 0.78, "date_path")
    if _ARTICLE_HINT_PATTERN.search(f"/{path}/") and len(segments) >= 2:
        return UrlClassification(UrlContentType.STANDARD_ARTICLE, 0.7, "article_hint")
    return UrlClassification(UrlContentType.INVALID_PAGE, 0.7, "no_article_signal")


def _navigation_type_for_segments(
    segments: list[str],
    *,
    query: str,
    raw_path: str,
) -> UrlContentType | None:
    segment_set = set(segments)
    if query and ("search" in segment_set or segments[-1] in {"search", "find"}):
        return UrlContentType.SEARCH_PAGE
    if segment_set & {"topic", "topics"}:
        return UrlContentType.TOPIC_PAGE
    if segment_set & {"tag", "tags"}:
        return UrlContentType.TAG_PAGE
    if segment_set & {"author", "authors"}:
        return UrlContentType.AUTHOR_PAGE
    if segment_set & {"archive", "archives"}:
        return UrlContentType.ARCHIVE_PAGE
    if segment_set & _NAVIGATION_SEGMENTS:
        return UrlContentType.SECTION_PAGE
    if raw_path.endswith("/") and not _has_article_specificity(
        raw_path.strip("/"),
        segments,
    ):
        return UrlContentType.SECTION_PAGE
    if len(segments) <= 2 and not _has_article_specificity("/".join(segments), segments):
        return UrlContentType.SECTION_PAGE
    return None


def _classify_publisher_specific(
    host: str,
    path: str,
    segments: list[str],
    *,
    raw_path: str,
) -> UrlClassification | None:
    del segments
    if "thehindu.com" in host:
        if _THE_HINDU_ARTICLE_PATTERN.search(f"/{path}"):
            return UrlClassification(
                _semantic_content_type(path.split("/")) or UrlContentType.STANDARD_ARTICLE,
                0.98,
                "the_hindu_article_id",
            )
        if raw_path.endswith("/"):
            return UrlClassification(UrlContentType.SECTION_PAGE, 0.92, "the_hindu_section")
    if "aljazeera.com" in host and _AL_JAZEERA_DATE_PATTERN.search(f"/{path}"):
        return UrlClassification(
            _semantic_content_type(path.split("/")) or UrlContentType.STANDARD_ARTICLE,
            0.95,
            "al_jazeera_dated_article",
        )
    if "reuters.com" in host and _REUTERS_ARTICLE_PATTERN.search(f"/{path}"):
        return UrlClassification(
            _semantic_content_type(path.split("/")) or UrlContentType.STANDARD_ARTICLE,
            0.94,
            "reuters_dated_article",
        )
    if "indianexpress.com" in host and _INDIAN_EXPRESS_ARTICLE_PATTERN.search(f"/{path}"):
        return UrlClassification(
            _semantic_content_type(path.split("/")) or UrlContentType.STANDARD_ARTICLE,
            0.95,
            "indian_express_article_id",
        )
    if "bbc." in host and _BBC_ARTICLE_ID_PATTERN.search(f"/{path}"):
        return UrlClassification(
            _semantic_content_type(path.split("/")) or UrlContentType.STANDARD_ARTICLE,
            0.9,
            "bbc_article_id",
        )
    return None


def _semantic_content_type(segments: list[str]) -> UrlContentType | None:
    segment_set = set(segments)
    if segment_set & {"live", "liveblog", "live-blog"}:
        return UrlContentType.LIVEBLOG
    if segment_set & {"breaking", "breaking-news"}:
        return UrlContentType.BREAKING_NEWS
    if segment_set & {"explainer", "explainers", "explained"}:
        return UrlContentType.EXPLAINER
    if segment_set & {"analysis", "analyses"}:
        return UrlContentType.ANALYSIS
    if segment_set & {"opinion", "opinions", "comment", "columns"}:
        return UrlContentType.OPINION
    if segment_set & {"investigation", "investigations", "investigative"}:
        return UrlContentType.INVESTIGATION
    if segment_set & {"fact-check", "factcheck", "fact-checks"}:
        return UrlContentType.FACT_CHECK
    if segment_set & {"press-release", "press-releases", "news-release"}:
        return UrlContentType.PRESS_RELEASE
    if segment_set & {"video", "videos"}:
        return UrlContentType.VIDEO_REPORT
    if segment_set & {"photo", "photos", "gallery", "galleries"}:
        return UrlContentType.PHOTO_STORY
    return None


def _has_article_specificity(path: str, segments: list[str]) -> bool:
    return (
        len(segments) >= 2
        and (
            bool(_ARTICLE_SLUG_PATTERN.search(segments[-1]))
            or bool(_DATE_PATH_PATTERN.search(f"/{path}/"))
            or any(segment.startswith("article") for segment in segments)
            or _has_special_format_story_hint(segments)
        )
    )


def _has_special_format_story_hint(segments: list[str]) -> bool:
    if len(segments) < 2:
        return False
    special_format_segments = {
        "analysis",
        "analyses",
        "breaking",
        "breaking-news",
        "explainer",
        "explainers",
        "explained",
        "fact-check",
        "factcheck",
        "fact-checks",
        "gallery",
        "galleries",
        "investigation",
        "investigations",
        "live",
        "liveblog",
        "live-blog",
        "opinion",
        "opinions",
        "photo",
        "photos",
        "press-release",
        "press-releases",
        "video",
        "videos",
    }
    return bool(set(segments[:-1]) & special_format_segments) and len(segments[-1]) >= 8


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
