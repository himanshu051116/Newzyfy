from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from xml.etree.ElementTree import Element

from defusedxml import ElementTree


class SitemapDocumentType(StrEnum):
    URL_SET = "urlset"
    INDEX = "sitemapindex"


@dataclass(frozen=True, slots=True)
class SitemapEntry:
    location: str
    last_modified_raw: str | None
    publication_date_raw: str | None = None
    news_title: str | None = None


@dataclass(frozen=True, slots=True)
class SitemapDocument:
    document_type: SitemapDocumentType
    entries: tuple[SitemapEntry, ...]
    parsed_at: datetime


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _first_descendant_text(
    element: Element,
    local_name: str,
) -> str | None:
    for descendant in element.iter():
        if _local_name(descendant.tag) == local_name and descendant.text:
            value = str(descendant.text).strip()
            if value:
                return value
    return None


def parse_sitemap(xml: str | bytes) -> SitemapDocument:
    root = ElementTree.fromstring(xml)
    root_name = _local_name(root.tag)
    if root_name not in {"urlset", "sitemapindex"}:
        raise ValueError(f"unsupported sitemap root element: {root_name}")

    child_name = "url" if root_name == "urlset" else "sitemap"
    entries: list[SitemapEntry] = []
    for element in root:
        if _local_name(element.tag) != child_name:
            continue
        location = _first_descendant_text(element, "loc")
        if not location:
            continue
        entries.append(
            SitemapEntry(
                location=location,
                last_modified_raw=_first_descendant_text(element, "lastmod"),
                publication_date_raw=_first_descendant_text(element, "publication_date"),
                news_title=_first_descendant_text(element, "title"),
            )
        )
    return SitemapDocument(
        document_type=(
            SitemapDocumentType.URL_SET
            if root_name == "urlset"
            else SitemapDocumentType.INDEX
        ),
        entries=tuple(entries),
        parsed_at=datetime.now(UTC),
    )
