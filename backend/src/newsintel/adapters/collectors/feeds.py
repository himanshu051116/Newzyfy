from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from newsintel.domain.acquisition.models import (
    DiscoveredItem,
    DiscoveryChannelType,
)

ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: Element, names: set[str]) -> str | None:
    for child in element:
        if _local_name(child.tag) in names and child.text:
            value = str(child.text).strip()
            if value:
                return value
    return None


def _atom_link(entry: Element) -> str | None:
    fallback: str | None = None
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href_value = child.attrib.get("href")
        href = str(href_value) if href_value is not None else None
        if not href:
            continue
        rel = child.attrib.get("rel", "alternate")
        if rel == "alternate":
            return href
        fallback = fallback or href
    return fallback


def parse_feed(xml: str | bytes, channel_url: str) -> list[DiscoveredItem]:
    root = ElementTree.fromstring(xml)
    root_name = _local_name(root.tag)
    discovered_at = datetime.now(UTC)

    if root_name in {"rss", "rdf"}:
        items = [element for element in root.iter() if _local_name(element.tag) == "item"]
        return [
            DiscoveredItem(
                external_id=_child_text(item, {"guid", "id"}),
                url=_child_text(item, {"link"}) or "",
                title=_child_text(item, {"title"}),
                published_at_raw=_child_text(
                    item,
                    {"pubdate", "published", "updated", "date"},
                ),
                channel_type=DiscoveryChannelType.RSS,
                channel_url=channel_url,
                discovered_at=discovered_at,
            )
            for item in items
            if _child_text(item, {"link"})
        ]

    if root_name == "feed" or root.tag == f"{{{ATOM_NAMESPACE}}}feed":
        entries = [element for element in root if _local_name(element.tag) == "entry"]
        output: list[DiscoveredItem] = []
        for entry in entries:
            link = _atom_link(entry)
            if not link:
                continue
            output.append(
                DiscoveredItem(
                    external_id=_child_text(entry, {"id"}),
                    url=link,
                    title=_child_text(entry, {"title"}),
                    published_at_raw=_child_text(entry, {"published", "updated"}),
                    channel_type=DiscoveryChannelType.ATOM,
                    channel_url=channel_url,
                    discovered_at=discovered_at,
                )
            )
        return output

    raise ValueError(f"unsupported feed root element: {root_name}")


def parse_feed_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def discover_websub_links(xml: str | bytes) -> tuple[tuple[str, ...], str | None]:
    root = ElementTree.fromstring(xml)
    hubs: list[str] = []
    self_url: str | None = None
    for element in root.iter():
        if _local_name(element.tag) != "link":
            continue
        rel = element.attrib.get("rel", "").lower()
        href = element.attrib.get("href")
        if not href:
            continue
        if rel == "hub":
            hubs.append(href)
        elif rel == "self":
            self_url = href
    return tuple(dict.fromkeys(hubs)), self_url
