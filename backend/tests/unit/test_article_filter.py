from datetime import UTC, datetime, timedelta

from newsintel.domain.acquisition.article_filter import (
    UrlContentType,
    UrlRejectionReason,
    classify_article_url,
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
    assert decision.url_type is UrlContentType.STANDARD_ARTICLE


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


def test_admits_special_story_formats_instead_of_blindly_rejecting_them() -> None:
    now = datetime(2026, 6, 27, 10, tzinfo=UTC)
    expected = {
        "https://example.com/live/election-results-update": UrlContentType.LIVEBLOG,
        "https://example.com/explainer/why-satellite-imaging-matters": UrlContentType.EXPLAINER,
        "https://example.com/investigation/inside-ai-chip-supply-chain": (
            UrlContentType.INVESTIGATION
        ),
        "https://example.com/fact-check/claim-about-new-policy-reviewed": UrlContentType.FACT_CHECK,
        "https://example.com/video/breaking-news-update": UrlContentType.VIDEO_REPORT,
        "https://example.com/gallery/photos-from-today": UrlContentType.PHOTO_STORY,
    }

    for url, url_type in expected.items():
        decision = should_admit_article_url(url, published_at=now, observed_at=now)
        assert decision.accepted
        assert decision.url_type is url_type


def test_looks_like_article_url_uses_slug_and_date_hints() -> None:
    assert looks_like_article_url(
        "https://example.com/2026/06/27/company-launches-ai-platform"
    )
    assert looks_like_article_url(
        "https://example.com/news/company-launches-new-ai-platform"
    )
    assert not looks_like_article_url("https://example.com/business")


def test_classifier_rejects_two_segment_section_pages() -> None:
    classification = classify_article_url("https://example.com/news/national")

    assert classification.url_type is UrlContentType.SECTION_PAGE
    assert not looks_like_article_url("https://example.com/news/national")


def test_the_hindu_article_rule_prefers_article_id_and_rejects_sections() -> None:
    article = classify_article_url(
        "https://www.thehindu.com/news/national/example-story/article68393123.ece"
    )
    section = classify_article_url("https://www.thehindu.com/news/national/")

    assert article.url_type is UrlContentType.STANDARD_ARTICLE
    assert article.reason == "the_hindu_article_id"
    assert section.url_type is UrlContentType.SECTION_PAGE


def test_publisher_specific_rules_cover_major_sources() -> None:
    assert (
        classify_article_url(
            "https://www.aljazeera.com/news/2026/7/3/example-story-title"
        ).url_type
        is UrlContentType.STANDARD_ARTICLE
    )
    assert (
        classify_article_url(
            "https://www.reuters.com/world/us/example-story-title-2026-07-03/"
        ).url_type
        is UrlContentType.STANDARD_ARTICLE
    )
    assert (
        classify_article_url(
            "https://indianexpress.com/article/india/example-story-title-1234567/"
        ).url_type
        is UrlContentType.STANDARD_ARTICLE
    )
    assert (
        classify_article_url(
            "https://www.bbc.com/news/world-asia-12345678"
        ).url_type
        is UrlContentType.STANDARD_ARTICLE
    )
