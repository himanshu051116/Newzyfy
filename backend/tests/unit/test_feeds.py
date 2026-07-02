from newsintel.adapters.collectors.feeds import (
    discover_websub_links,
    parse_feed,
    parse_feed_datetime,
)
from newsintel.domain.acquisition.models import DiscoveryChannelType


def test_parses_rss_items() -> None:
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <guid>story-1</guid>
        <title>Story One</title>
        <link>https://example.com/story-1</link>
        <pubDate>Wed, 25 Jun 2026 10:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""

    items = parse_feed(xml, "https://example.com/rss")

    assert len(items) == 1
    assert items[0].external_id == "story-1"
    assert items[0].channel_type is DiscoveryChannelType.RSS
    assert parse_feed_datetime(items[0].published_at_raw).isoformat() == (
        "2026-06-25T10:00:00+00:00"
    )


def test_parses_atom_and_discovers_websub() -> None:
    xml = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <link rel="self" href="https://example.com/feed"/>
      <link rel="hub" href="https://hub.example.net"/>
      <entry>
        <id>tag:example.com,2026:1</id>
        <title>Atom Story</title>
        <link rel="alternate" href="https://example.com/atom-story"/>
        <updated>2026-06-25T10:00:00Z</updated>
      </entry>
    </feed>"""

    items = parse_feed(xml, "https://example.com/feed")
    hubs, self_url = discover_websub_links(xml)

    assert items[0].channel_type is DiscoveryChannelType.ATOM
    assert hubs == ("https://hub.example.net",)
    assert self_url == "https://example.com/feed"

