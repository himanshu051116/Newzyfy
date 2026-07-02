from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from newsintel.adapters.collectors.feeds import parse_feed
from newsintel.adapters.collectors.sitemaps import parse_sitemap
from newsintel.domain.acquisition.article_filter import looks_like_article_url
from newsintel.domain.acquisition.canonicalization import (
    CanonicalizationPolicy,
    canonicalize_url,
)
from newsintel.domain.acquisition.models import DiscoveryChannelType

COMMON_DISCOVERY_PATHS = (
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/news-sitemap.xml",
    "/sitemap-news.xml",
    "/feed",
    "/rss",
    "/rss.xml",
    "/feed.xml",
)


@dataclass(frozen=True, slots=True)
class DiscoveredEndpoint:
    url: str
    source: str
    hinted_type: DiscoveryChannelType | None = None


@dataclass(frozen=True, slots=True)
class ValidatedEndpoint:
    url: str
    channel_type: DiscoveryChannelType
    source: str
    item_count: int


class _AlternateLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.endpoints: list[DiscoveredEndpoint] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "link":
            return
        values = {
            key.lower(): (value or "").strip()
            for key, value in attrs
        }
        rel = values.get("rel", "").lower()
        href = values.get("href")
        link_type = values.get("type", "").lower()
        if not href or "alternate" not in rel:
            return
        if link_type in {"application/rss+xml", "application/rdf+xml"}:
            hinted = DiscoveryChannelType.RSS
        elif link_type == "application/atom+xml":
            hinted = DiscoveryChannelType.ATOM
        else:
            return
        self.endpoints.append(
            DiscoveredEndpoint(
                url=urljoin(self.base_url, href),
                source="html_alternate",
                hinted_type=hinted,
            )
        )


@dataclass(frozen=True, slots=True)
class HtmlArticleLink:
    url: str
    title: str | None


class _AnchorLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[HtmlArticleLink] = []
        self._href_stack: list[str | None] = []
        self._text_stack: list[list[str]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "a":
            return
        values = {
            key.lower(): (value or "").strip()
            for key, value in attrs
        }
        href = values.get("href")
        if not href:
            return
        self._href_stack.append(urljoin(self.base_url, href))
        self._text_stack.append([])

    def handle_data(self, data: str) -> None:
        if self._text_stack:
            self._text_stack[-1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href_stack:
            return
        href = self._href_stack.pop()
        text_parts = self._text_stack.pop() if self._text_stack else []
        if not href:
            return
        title = _normalize_text(" ".join(text_parts)) or None
        self.links.append(HtmlArticleLink(url=href, title=title))


def normalize_homepage_url(url: str) -> str:
    candidate = url.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    canonical = canonicalize_url(
        candidate,
        CanonicalizationPolicy(
            drop_parameters=frozenset(),
            strip_www=False,
        ),
    )
    return canonical.normalized


def canonical_domain(url: str) -> str:
    normalized = normalize_homepage_url(url)
    host = urlsplit(normalized).hostname
    if not host:
        raise ValueError("website URL must include a hostname")
    return host.lower()


def origin_for_url(url: str) -> str:
    parsed = urlsplit(normalize_homepage_url(url))
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def discover_alternate_links(html: bytes, *, homepage_url: str) -> tuple[DiscoveredEndpoint, ...]:
    parser = _AlternateLinkParser(homepage_url)
    parser.feed(_decode_html(html))
    parser.close()
    return tuple(parser.endpoints)


def discover_robot_sitemaps(
    robots_txt: bytes,
    *,
    homepage_url: str,
) -> tuple[DiscoveredEndpoint, ...]:
    endpoints: list[DiscoveredEndpoint] = []
    for raw_line in _decode_html(robots_txt).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        if key.strip().lower() != "sitemap":
            continue
        sitemap_url = value.strip()
        if sitemap_url:
            endpoints.append(
                DiscoveredEndpoint(
                    url=urljoin(homepage_url, sitemap_url),
                    source="robots_txt",
                    hinted_type=DiscoveryChannelType.SITEMAP,
                )
            )
    return tuple(endpoints)


def common_discovery_endpoints(homepage_url: str) -> tuple[DiscoveredEndpoint, ...]:
    origin = origin_for_url(homepage_url)
    endpoints: list[DiscoveredEndpoint] = []
    for path in COMMON_DISCOVERY_PATHS:
        hinted = (
            DiscoveryChannelType.SITEMAP
            if "sitemap" in path
            else DiscoveryChannelType.RSS
        )
        endpoints.append(
            DiscoveredEndpoint(
                url=urljoin(origin, path),
                source="common_path",
                hinted_type=hinted,
            )
        )
    return tuple(endpoints)


def discover_html_article_links(
    html: bytes,
    *,
    page_url: str,
    same_origin_only: bool = True,
) -> tuple[HtmlArticleLink, ...]:
    parser = _AnchorLinkParser(page_url)
    parser.feed(_decode_html(html))
    parser.close()
    page_origin = origin_for_url(page_url)
    seen: set[str] = set()
    article_links: list[HtmlArticleLink] = []
    for link in parser.links:
        try:
            if same_origin_only and origin_for_url(link.url) != page_origin:
                continue
            if not looks_like_article_url(link.url):
                continue
            normalized = canonicalize_url(link.url).normalized
        except ValueError:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        article_links.append(HtmlArticleLink(url=normalized, title=link.title))
    return tuple(article_links)


def discover_listing_endpoints(
    html: bytes,
    *,
    homepage_url: str,
    max_endpoints: int = 12,
) -> tuple[DiscoveredEndpoint, ...]:
    parser = _AnchorLinkParser(homepage_url)
    parser.feed(_decode_html(html))
    parser.close()
    page_origin = origin_for_url(homepage_url)
    seen: set[str] = set()
    endpoints: list[DiscoveredEndpoint] = []
    for link in parser.links:
        if len(endpoints) >= max_endpoints:
            break
        try:
            if origin_for_url(link.url) != page_origin:
                continue
            if not _looks_like_listing_page(link.url):
                continue
            normalized = canonicalize_url(
                link.url,
                CanonicalizationPolicy(drop_parameters=frozenset()),
            ).normalized
        except ValueError:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        endpoints.append(
            DiscoveredEndpoint(
                url=normalized,
                source="homepage_listing_link",
                hinted_type=DiscoveryChannelType.CATEGORY,
            )
        )
    return tuple(endpoints)


def unique_endpoints(
    endpoints: tuple[DiscoveredEndpoint, ...],
) -> tuple[DiscoveredEndpoint, ...]:
    seen: set[str] = set()
    output: list[DiscoveredEndpoint] = []
    for endpoint in endpoints:
        try:
            normalized = canonicalize_url(
                endpoint.url,
                CanonicalizationPolicy(drop_parameters=frozenset()),
            ).normalized
        except ValueError:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(
            DiscoveredEndpoint(
                url=normalized,
                source=endpoint.source,
                hinted_type=endpoint.hinted_type,
            )
        )
    return tuple(output)


def validate_endpoint_payload(
    payload: bytes,
    *,
    endpoint_url: str,
    source: str,
    hinted_type: DiscoveryChannelType | None = None,
) -> ValidatedEndpoint:
    if hinted_type in _HTML_DISCOVERY_CHANNEL_TYPES:
        article_links = discover_html_article_links(payload, page_url=endpoint_url)
        if article_links:
            return ValidatedEndpoint(
                url=endpoint_url,
                channel_type=hinted_type,
                source=source,
                item_count=len(article_links),
            )

    feed_error: Exception | None = None
    try:
        feed_items = parse_feed(payload, endpoint_url)
        if feed_items:
            channel_type = (
                DiscoveryChannelType.ATOM
                if feed_items[0].channel_type is DiscoveryChannelType.ATOM
                else DiscoveryChannelType.RSS
            )
            return ValidatedEndpoint(
                url=endpoint_url,
                channel_type=channel_type,
                source=source,
                item_count=len(feed_items),
            )
    except Exception as exc:
        feed_error = exc

    try:
        sitemap = parse_sitemap(payload)
        if sitemap.entries:
            return ValidatedEndpoint(
                url=endpoint_url,
                channel_type=DiscoveryChannelType.SITEMAP,
                source=source,
                item_count=len(sitemap.entries),
            )
    except Exception as sitemap_error:
        if feed_error is not None:
            raise ValueError(
                f"endpoint is neither valid feed nor sitemap: {feed_error}; {sitemap_error}"
            ) from sitemap_error
        raise

    raise ValueError("endpoint parsed but did not contain items")


def _decode_html(payload: bytes) -> str:
    for encoding in ("utf-8", "windows-1252", "iso-8859-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


_HTML_DISCOVERY_CHANNEL_TYPES = {
    DiscoveryChannelType.HOMEPAGE,
    DiscoveryChannelType.CATEGORY,
    DiscoveryChannelType.TAG,
    DiscoveryChannelType.AUTHOR,
    DiscoveryChannelType.ARCHIVE,
    DiscoveryChannelType.INTERNAL_LINK,
    DiscoveryChannelType.SEARCH,
}

_LISTING_HINT_SEGMENTS = {
    "ai",
    "artificial-intelligence",
    "business",
    "climate",
    "economy",
    "health",
    "healthcare",
    "india",
    "markets",
    "news",
    "politics",
    "science",
    "space",
    "sport",
    "sports",
    "tech",
    "technology",
    "world",
}
_LISTING_EXCLUDED_SEGMENTS = {
    "about",
    "account",
    "advertise",
    "author",
    "contact",
    "login",
    "privacy",
    "search",
    "signin",
    "subscribe",
    "tag",
    "terms",
    "video",
}


def _looks_like_listing_page(url: str) -> bool:
    if looks_like_article_url(url):
        return False
    parsed = urlsplit(url)
    path = parsed.path.lower().strip("/")
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments or len(segments) > 3:
        return False
    if set(segments) & _LISTING_EXCLUDED_SEGMENTS:
        return False
    return bool(set(segments) & _LISTING_HINT_SEGMENTS)


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split()).strip()
