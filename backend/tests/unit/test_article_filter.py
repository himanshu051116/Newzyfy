from datetime import UTC, datetime, timedelta

from newsintel.domain.acquisition.article_filter import (
    UrlRejectionReason,
    looks_like_article_url,
    should_admit_article_url,
)


def test_accepts_recent_article_url() -> None:
    now = datetime(2026, 6, 27, 10, tzinfo=UTC)

    decision = should_admit_article_url(
        "https://example.com/news/company-launches-new-ai-platform",
        published_at=now - timedelta(hours=3),
        observed_at=now,
    )

    assert decision.accepted
    assert decision.reason is None


def test_rejects_old_article_url() -> None:
    now = datetime(2026, 6, 27, 10, tzinfo=UTC)

    decision = should_admit_article_url(
        "https://example.com/news/company-launches-new-ai-platform",
        published_at=now - timedelta(days=5),
        observed_at=now,
    )

    assert not decision.accepted
    assert decision.reason is UrlRejectionReason.TOO_OLD


def test_rejects_category_tag_video_and_archive_urls() -> None:
    now = datetime(2026, 6, 27, 10, tzinfo=UTC)
    rejected = [
        "https://example.com/category/business",
        "https://example.com/topics/artificial-intelligence",
        "https://example.com/tag/artificial-intelligence",
        "https://example.com/multimedia/breaking-news",
        "https://example.com/video/breaking-news",
        "https://example.com/gallery/photos-from-today",
        "https://example.com/search?q=ai",
        "https://example.com/archive/2026/06",
    ]

    for url in rejected:
        decision = should_admit_article_url(
            url,
            published_at=now,
            observed_at=now,
        )
        assert not decision.accepted
        assert decision.reason is UrlRejectionReason.EXCLUDED_SECTION


def test_looks_like_article_url_uses_slug_and_date_hints() -> None:
    assert looks_like_article_url(
        "https://example.com/2026/06/27/company-launches-ai-platform"
    )
    assert looks_like_article_url(
        "https://example.com/news/company-launches-new-ai-platform"
    )
    assert not looks_like_article_url("https://example.com/business")
