from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import urljoin

from .canonicalization import canonicalize_url


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: set[str] = set()

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "a":
            return
        href = next((value for key, value in attrs if key.lower() == "href"), None)
        if not href:
            return
        absolute = urljoin(self.base_url, href)
        try:
            self.links.add(canonicalize_url(absolute).normalized)
        except ValueError:
            return


@dataclass(frozen=True, slots=True)
class LinkSetSnapshot:
    base_url: str
    content_hash: str
    link_set_hash: str
    links: frozenset[str]


@dataclass(frozen=True, slots=True)
class LinkSetDiff:
    inserted: frozenset[str]
    removed: frozenset[str]
    unchanged: frozenset[str]

    @property
    def materially_changed(self) -> bool:
        return bool(self.inserted or self.removed)


def create_link_set_snapshot(base_url: str, html: str) -> LinkSetSnapshot:
    parser = _LinkParser(base_url)
    parser.feed(html)
    links = frozenset(parser.links)
    joined = "\n".join(sorted(links))
    return LinkSetSnapshot(
        base_url=base_url,
        content_hash=sha256(html.encode("utf-8")).hexdigest(),
        link_set_hash=sha256(joined.encode("utf-8")).hexdigest(),
        links=links,
    )


def compare_link_sets(previous: LinkSetSnapshot, current: LinkSetSnapshot) -> LinkSetDiff:
    if previous.base_url != current.base_url:
        raise ValueError("snapshots must describe the same monitored page")
    return LinkSetDiff(
        inserted=current.links - previous.links,
        removed=previous.links - current.links,
        unchanged=previous.links & current.links,
    )

