import pytest

from newsintel.adapters.collectors.source_discovery import (
    common_discovery_endpoints,
    discover_alternate_links,
    discover_html_article_links,
    discover_listing_endpoints,
    discover_robot_sitemaps,
    normalize_homepage_url,
    unique_endpoints,
    validate_endpoint_payload,
)
from newsintel.domain.acquisition.models import DiscoveryChannelType


def test_homepage_url_is_normalized_with_scheme() -> None:
    assert normalize_homepage_url("example.com/news") == "https://example.com/news"


def test_html_alternate_feed_links_are_discovered() -> None:
    html = b"""
    <html><head>
      <link rel="alternate" type="application/rss+xml" href="/rss.xml" />
      <link rel="alternate" type="application/atom+xml" href="https://example.com/atom.xml" />
      <link rel="stylesheet" href="/style.css" />
    </head></html>
    """

    endpoints = discover_alternate_links(html, homepage_url="https://example.com/news")

    assert [item.url for item in endpoints] == [
        "https://example.com/rss.xml",
        "https://example.com/atom.xml",
    ]
    assert endpoints[0].hinted_type is DiscoveryChannelType.RSS
    assert endpoints[1].hinted_type is DiscoveryChannelType.ATOM


def test_robots_sitemaps_are_discovered() -> None:
    robots = b"""
    User-agent: *
    Disallow: /admin
    Sitemap: https://example.com/news-sitemap.xml
    Sitemap: /sitemap.xml
    """

    endpoints = discover_robot_sitemaps(robots, homepage_url="https://example.com")

    assert [item.url for item in endpoints] == [
        "https://example.com/news-sitemap.xml",
        "https://example.com/sitemap.xml",
    ]


def test_common_discovery_endpoints_are_deduplicated() -> None:
    endpoints = common_discovery_endpoints("https://example.com/news")
    deduped = unique_endpoints(endpoints + endpoints)

    assert len(deduped) == len(endpoints)
    assert "https://example.com/sitemap.xml" in {item.url for item in deduped}
    assert "https://example.com/feed" in {item.url for item in deduped}


def test_html_article_links_are_extracted_from_listing_pages() -> None:
    html = b"""
    <html><body>
      <a href="/news/2026/07/02/one-important-story-today?utm_source=home">One story</a>
      <a href="/news/2026/07/02/one-important-story-today?utm_campaign=dup">Duplicate</a>
      <a href="https://external.example/news/2026/07/02/external-story">External</a>
      <a href="/topics/artificial-intelligence">Topic page</a>
      <a href="/video/2026/07/02/story-video">Video</a>
    </body></html>
    """

    links = discover_html_article_links(html, page_url="https://example.com")

    assert len(links) == 1
    assert links[0].url == "https://example.com/news/2026/07/02/one-important-story-today"
    assert links[0].title == "One story"


def test_listing_endpoints_are_discovered_from_homepage_navigation() -> None:
    html = b"""
    <html><body>
      <a href="/technology">Tech</a>
      <a href="/world">World</a>
      <a href="/about">About</a>
      <a href="/news/2026/07/02/one-important-story-today">Article</a>
    </body></html>
    """

    endpoints = discover_listing_endpoints(html, homepage_url="https://example.com")

    assert [item.url for item in endpoints] == [
        "https://example.com/technology",
        "https://example.com/world",
    ]
    assert all(item.hinted_type is DiscoveryChannelType.CATEGORY for item in endpoints)


def test_validates_rss_payload() -> None:
    payload = b"""<rss><channel>
      <item><title>One</title><link>https://example.com/one</link></item>
    </channel></rss>"""

    validated = validate_endpoint_payload(
        payload,
        endpoint_url="https://example.com/rss.xml",
        source="test",
    )

    assert validated.channel_type is DiscoveryChannelType.RSS
    assert validated.item_count == 1


def test_validates_html_discovery_payload_when_channel_type_is_hinted() -> None:
    payload = b"""<html><body>
      <a href="/news/2026/07/02/one-important-story-today">One story</a>
    </body></html>"""

    validated = validate_endpoint_payload(
        payload,
        endpoint_url="https://example.com",
        source="homepage",
        hinted_type=DiscoveryChannelType.HOMEPAGE,
    )

    assert validated.channel_type is DiscoveryChannelType.HOMEPAGE
    assert validated.item_count == 1


def test_rejects_non_feed_or_sitemap_payload() -> None:
    with pytest.raises(ValueError, match="neither valid feed nor sitemap"):
        validate_endpoint_payload(
            b"<html><body>No feed here</body></html>",
            endpoint_url="https://example.com",
            source="test",
        )
