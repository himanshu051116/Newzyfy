from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
from importlib import import_module
from typing import Any
from urllib.parse import urljoin, urlsplit

_WHITESPACE_PATTERN = re.compile(r"\s+")
_ATTRIBUTE_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_ARTICLE_TYPES = {
    "article",
    "newsarticle",
    "reportagenewsarticle",
    "analysisnewsarticle",
    "blogposting",
}
_SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "button",
    "select",
    "textarea",
}
_BLOCK_TAGS = {
    "p",
    "li",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}
_LOW_VALUE_PHRASES = (
    "account subscription benefits",
    "accept cookies",
    "active subscription",
    "all rights reserved",
    "click here",
    "continue reading",
    "enable javascript",
    "founder summit",
    "join 1,000+ founders",
    "loading...",
    "logout and login",
    "premium stories",
    "privacy policy",
    "register now",
    "sign in",
    "strictlyvc",
    "subscribed with another email",
    "subscribe now",
    "ticket savings",
    "tickets are going fast",
    "terms of use",
    "you don't have any active subscription",
)
_PAYWALL_OR_ACCOUNT_PHRASES = (
    "active subscription",
    "already a subscriber",
    "continue reading with",
    "for subscribers",
    "login with that one",
    "metered access",
    "premium stories",
    "subscribe to continue",
    "subscribe now",
    "subscriber only",
    "subscription required",
)
_SKIP_ATTRIBUTE_TOKENS = {
    "ad",
    "ads",
    "advert",
    "advertisement",
    "banner",
    "comments",
    "consent",
    "cookie",
    "footer",
    "gallery",
    "header",
    "login",
    "modal",
    "newsletter",
    "paywall",
    "promo",
    "promoted",
    "recommend",
    "related",
    "share",
    "signin",
    "social",
    "sponsor",
    "sponsored",
    "subscription",
    "video",
}
_SKIP_ATTRIBUTE_PHRASES = (
    "more from",
    "paid post",
    "read more",
    "related content",
    "share this",
    "sign in",
    "subscribe",
)


@dataclass(frozen=True, slots=True)
class _ExtractionPolicy:
    name: str
    domain_suffixes: tuple[str, ...]
    low_value_phrases: tuple[str, ...] = ()
    skip_attribute_tokens: frozenset[str] = frozenset()
    skip_attribute_phrases: tuple[str, ...] = ()
    paywall_or_partial_phrases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _OptionalExtractorResult:
    text: str
    method: str
    metadata: dict[str, object]


_PUBLISHER_POLICIES = (
    _ExtractionPolicy(
        name="techcrunch",
        domain_suffixes=("techcrunch.com",),
        low_value_phrases=(
            "strictlyvc",
            "founder summit",
            "join 1,000+ founders",
            "tickets are going fast",
        ),
        skip_attribute_tokens=frozenset({"event", "events", "promo", "sponsor"}),
    ),
    _ExtractionPolicy(
        name="the_hindu",
        domain_suffixes=("thehindu.com", "www.thehindu.com"),
        low_value_phrases=(
            "account subscription benefits",
            "active subscription",
            "premium stories",
            "subscribed with another email",
        ),
        skip_attribute_tokens=frozenset({"subscription", "paywall", "premium"}),
        paywall_or_partial_phrases=(
            "you don't have any active subscription",
            "premium stories",
        ),
    ),
    _ExtractionPolicy(
        name="indian_express",
        domain_suffixes=("indianexpress.com", "www.indianexpress.com"),
        low_value_phrases=("subscribe to continue", "premium article"),
        skip_attribute_tokens=frozenset({"premium", "subscription", "paywall"}),
    ),
    _ExtractionPolicy(
        name="ndtv",
        domain_suffixes=("ndtv.com", "www.ndtv.com"),
        skip_attribute_tokens=frozenset({"also", "related", "video"}),
        skip_attribute_phrases=("also read", "related stories"),
    ),
)


@dataclass(frozen=True, slots=True)
class ExtractedArticle:
    title: str | None
    byline: str | None
    published_at: datetime | None
    modified_at: datetime | None
    language: str | None
    canonical_url: str | None
    text_content: str
    content_sha256: str
    extraction_method: str
    metadata: dict[str, object]
    warnings: tuple[str, ...]

    @property
    def word_count(self) -> int:
        return len(self.text_content.split())


@dataclass(slots=True)
class _TextBlock:
    tag: str
    pieces: list[str]


@dataclass(frozen=True, slots=True)
class _ParagraphExtractionResult:
    text: str
    accepted_block_count: int
    rejected_block_count: int
    rejected_boilerplate_count: int
    rejected_short_count: int


class _ArticleHTMLParser(HTMLParser):
    def __init__(self, base_url: str, *, policy: _ExtractionPolicy | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.policy = policy
        self.title_parts: list[str] = []
        self.blocks: list[str] = []
        self.meta: dict[str, list[str]] = {}
        self.links: dict[str, str] = {}
        self.json_ld_scripts: list[str] = []
        self.html_language: str | None = None

        self._skip_depth = 0
        self._skip_stack: list[str] = []
        self._in_title = False
        self._capture_json_ld = False
        self._script_parts: list[str] = []
        self._block_stack: list[_TextBlock] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag_name = tag.lower()
        attr_map = {
            key.lower(): value.strip() if value is not None else ""
            for key, value in attrs
        }

        if tag_name == "html":
            language = attr_map.get("lang") or attr_map.get("xml:lang")
            if language:
                self.html_language = language

        if tag_name == "title":
            self._in_title = True

        if tag_name == "meta":
            content = attr_map.get("content")
            key = (
                attr_map.get("property")
                or attr_map.get("name")
                or attr_map.get("itemprop")
                or attr_map.get("http-equiv")
            )
            if key and content:
                self.meta.setdefault(key.lower(), []).append(content)

        if tag_name == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href")
            if href:
                for relation in rel.split():
                    self.links[relation] = urljoin(self.base_url, href)

        if tag_name == "script":
            script_type = attr_map.get("type", "").lower()
            if "ld+json" in script_type:
                self._capture_json_ld = True
                self._script_parts = []

        if tag_name in _SKIP_TAGS or _should_skip_by_attributes(
            tag_name,
            attr_map,
            policy=self.policy,
        ):
            self._skip_depth += 1
            self._skip_stack.append(tag_name)
            return

        if self._skip_depth == 0 and tag_name in _BLOCK_TAGS:
            self._block_stack.append(_TextBlock(tag=tag_name, pieces=[]))

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()

        if tag_name == "title":
            self._in_title = False

        if tag_name == "script" and self._capture_json_ld:
            script = "".join(self._script_parts).strip()
            if script:
                self.json_ld_scripts.append(script)
            self._capture_json_ld = False
            self._script_parts = []

        if self._skip_depth > 0 and tag_name in self._skip_stack:
            while self._skip_stack:
                skipped_tag = self._skip_stack.pop()
                self._skip_depth -= 1
                if skipped_tag == tag_name:
                    break
            return

        if tag_name in _BLOCK_TAGS and self._block_stack:
            index = next(
                (
                    position
                    for position in range(len(self._block_stack) - 1, -1, -1)
                    if self._block_stack[position].tag == tag_name
                ),
                None,
            )
            if index is None:
                return
            block = self._block_stack.pop(index)
            text = _normalize_text(" ".join(block.pieces))
            if text:
                self.blocks.append(text)
                if self._block_stack:
                    self._block_stack[-1].pieces.append(text)

    def handle_data(self, data: str) -> None:
        if self._capture_json_ld:
            self._script_parts.append(data)
            return
        if self._in_title:
            self.title_parts.append(data)
            return
        if self._skip_depth > 0:
            return
        if self._block_stack:
            self._block_stack[-1].pieces.append(data)


def extract_article_html(html: bytes, *, base_url: str) -> ExtractedArticle:
    policy = _policy_for_url(base_url)
    parser = _ArticleHTMLParser(base_url, policy=policy)
    decoded = _decode_html(html)
    parser.feed(decoded)
    parser.close()

    json_ld_objects = tuple(_iter_json_ld_objects(parser.json_ld_scripts))
    json_ld_article = _select_article_json_ld(json_ld_objects)
    json_ld_body = _string_value(json_ld_article.get("articleBody")) if json_ld_article else None

    title = _first_present(
        _string_value(json_ld_article.get("headline")) if json_ld_article else None,
        _first_meta(
            parser.meta,
            "og:title",
            "twitter:title",
            "parsely-title",
            "dc.title",
            "title",
        ),
        _normalize_text(" ".join(parser.title_parts)),
    )
    byline = _first_present(
        _author_value(json_ld_article.get("author")) if json_ld_article else None,
        _first_meta(parser.meta, "author", "article:author", "parsely-author", "byl"),
    )
    published_at = _first_datetime(
        _string_value(json_ld_article.get("datePublished")) if json_ld_article else None,
        _first_meta(
            parser.meta,
            "article:published_time",
            "datepublished",
            "date",
            "dc.date",
            "pubdate",
            "sailthru.date",
            "parsely-pub-date",
        ),
    )
    modified_at = _first_datetime(
        _string_value(json_ld_article.get("dateModified")) if json_ld_article else None,
        _first_meta(
            parser.meta,
            "article:modified_time",
            "datemodified",
            "lastmod",
            "parsely-post-date",
        ),
    )
    language = _normalize_language(
        _first_present(
            _string_value(json_ld_article.get("inLanguage")) if json_ld_article else None,
            parser.html_language,
            _first_meta(parser.meta, "og:locale", "language", "content-language"),
        )
    )
    canonical_url = _first_present(
        parser.links.get("canonical"),
        _first_meta(parser.meta, "og:url", "twitter:url"),
    )

    paragraph_result = _extract_paragraph_text(parser.blocks, policy=policy)
    optional_result = _extract_with_trafilatura(decoded, base_url=base_url)
    trafilatura_available = optional_result is not None
    if json_ld_body and len(json_ld_body) >= 200:
        text_content = _normalize_multiline(json_ld_body)
        extraction_method = "json_ld_article_body"
        accepted_block_count = len([block for block in text_content.split("\n\n") if block])
        rejected_block_count = 0
        rejected_boilerplate_count = 0
        rejected_short_count = 0
    else:
        text_content = paragraph_result.text
        extraction_method = "visible_text_blocks"
        accepted_block_count = paragraph_result.accepted_block_count
        rejected_block_count = paragraph_result.rejected_block_count
        rejected_boilerplate_count = paragraph_result.rejected_boilerplate_count
        rejected_short_count = paragraph_result.rejected_short_count

        visible_quality_score = _extraction_quality_score(
            text_content,
            accepted_block_count=accepted_block_count,
            rejected_block_count=rejected_block_count,
            json_ld_article_detected=json_ld_article is not None,
        )
        if optional_result and _should_use_optional_extraction(
            current_text=text_content,
            current_quality_score=visible_quality_score,
            optional_text=optional_result.text,
        ):
            text_content = optional_result.text
            extraction_method = optional_result.method
            accepted_block_count = len(
                [block for block in text_content.split("\n\n") if block]
            )

    quality_score = _extraction_quality_score(
        text_content,
        accepted_block_count=accepted_block_count,
        rejected_block_count=rejected_block_count,
        json_ld_article_detected=json_ld_article is not None,
    )

    warnings: list[str] = []
    if not title:
        warnings.append("missing_title")
    if not text_content:
        warnings.append("missing_text_content")
    elif len(text_content.split()) < 50:
        warnings.append("short_text_content")
    if not published_at:
        warnings.append("missing_published_at")
    if not canonical_url:
        warnings.append("missing_canonical_url")
    if rejected_boilerplate_count:
        warnings.append("boilerplate_removed")
    paywall_indicators = _matching_phrases(
        decoded,
        _paywall_or_partial_phrases(policy),
    )
    text_paywall_indicators = _matching_phrases(
        text_content,
        _paywall_or_partial_phrases(policy),
    )
    if text_paywall_indicators:
        warnings.append("possible_subscription_boilerplate")
    if _looks_partial_or_paywalled(
        word_count=len(text_content.split()),
        raw_indicators=paywall_indicators,
        text_indicators=text_paywall_indicators,
    ):
        warnings.append("possible_paywall_or_partial_content")
    if text_content and quality_score < 0.45:
        warnings.append("low_extraction_quality")

    raw_html_sha256 = sha256(html).hexdigest()
    metadata: dict[str, object] = {
        "html_title": _normalize_text(" ".join(parser.title_parts)) or None,
        "json_ld_object_count": len(json_ld_objects),
        "json_ld_article_detected": json_ld_article is not None,
        "publisher_extraction_policy": policy.name if policy else "generic",
        "meta_keys": sorted(parser.meta.keys()),
        "block_count": len(parser.blocks),
        "accepted_block_count": accepted_block_count,
        "rejected_block_count": rejected_block_count,
        "rejected_boilerplate_count": rejected_boilerplate_count,
        "rejected_short_count": rejected_short_count,
        "extraction_quality_score": quality_score,
        "optional_trafilatura_available": trafilatura_available,
        "raw_html_sha256": raw_html_sha256,
        "raw_html_bytes": len(html),
        "paywall_indicator_count": len(paywall_indicators),
        "paywall_indicators": list(paywall_indicators[:10]),
        "word_count": len(text_content.split()),
    }
    if optional_result:
        metadata["optional_trafilatura"] = optional_result.metadata
    if modified_at:
        metadata["modified_at"] = modified_at.isoformat()

    return ExtractedArticle(
        title=title,
        byline=byline,
        published_at=published_at,
        modified_at=modified_at,
        language=language,
        canonical_url=canonical_url,
        text_content=text_content,
        content_sha256=sha256(text_content.encode("utf-8")).hexdigest(),
        extraction_method=extraction_method,
        metadata=metadata,
        warnings=tuple(warnings),
    )


def _decode_html(html: bytes) -> str:
    for encoding in ("utf-8", "windows-1252", "iso-8859-1"):
        try:
            return html.decode(encoding)
        except UnicodeDecodeError:
            continue
    return html.decode("utf-8", errors="replace")


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_PATTERN.sub(" ", value).strip()


def _normalize_multiline(value: str) -> str:
    lines = [_normalize_text(line) for line in value.splitlines()]
    return "\n\n".join(line for line in lines if line)


def _first_meta(meta: Mapping[str, list[str]], *keys: str) -> str | None:
    for key in keys:
        values = meta.get(key.lower(), [])
        for value in values:
            normalized = _normalize_text(value)
            if normalized:
                return normalized
    return None


def _first_present(*values: str | None) -> str | None:
    for value in values:
        normalized = _normalize_text(value)
        if normalized:
            return normalized
    return None


def _first_datetime(*values: str | None) -> datetime | None:
    for value in values:
        parsed = _parse_datetime(value)
        if parsed:
            return parsed
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None

    iso_value = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _normalize_language(value: str | None) -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    return normalized.replace("_", "-").split(",", maxsplit=1)[0][:35]


def _iter_json_ld_objects(scripts: Iterable[str]) -> Iterable[dict[str, Any]]:
    for script in scripts:
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        yield from _walk_json_ld(payload)


def _walk_json_ld(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _walk_json_ld(item)
        return
    if not isinstance(value, dict):
        return
    yield value
    graph = value.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            yield from _walk_json_ld(item)


def _select_article_json_ld(objects: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    candidates: list[Mapping[str, Any]] = []
    for item in objects:
        types = item.get("@type")
        if isinstance(types, str):
            normalized_types = {types.lower()}
        elif isinstance(types, list):
            normalized_types = {str(type_name).lower() for type_name in types}
        else:
            normalized_types = set()
        if normalized_types & _ARTICLE_TYPES:
            candidates.append(item)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: len(_string_value(item.get("articleBody")) or "")
        + len(_string_value(item.get("headline")) or ""),
    )


def _string_value(value: object) -> str | None:
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, int | float):
        return str(value)
    return None


def _author_value(value: object) -> str | None:
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, Mapping):
        return _string_value(value.get("name"))
    if isinstance(value, list):
        authors = [_author_value(item) for item in value]
        joined = ", ".join(author for author in authors if author)
        return joined or None
    return None


def _extract_paragraph_text(
    blocks: Iterable[str],
    *,
    policy: _ExtractionPolicy | None,
) -> _ParagraphExtractionResult:
    accepted: list[str] = []
    seen: set[str] = set()
    rejected = 0
    rejected_boilerplate = 0
    rejected_short = 0
    for block in blocks:
        text = _normalize_text(block)
        lowered = text.lower()
        if not text or lowered in seen:
            rejected += 1
            continue
        if _contains_any_phrase(text, _low_value_phrases(policy)):
            rejected += 1
            rejected_boilerplate += 1
            continue
        if len(text) < 40 and not text.endswith((".", "!", "?", '"', "'")):
            rejected += 1
            rejected_short += 1
            continue
        accepted.append(text)
        seen.add(lowered)
    return _ParagraphExtractionResult(
        text="\n\n".join(accepted),
        accepted_block_count=len(accepted),
        rejected_block_count=rejected,
        rejected_boilerplate_count=rejected_boilerplate,
        rejected_short_count=rejected_short,
    )


def _should_skip_by_attributes(
    tag_name: str,
    attr_map: Mapping[str, str],
    *,
    policy: _ExtractionPolicy | None,
) -> bool:
    if tag_name in {"article", "main", "body", "html"}:
        return False

    relevant_values: list[str] = []
    for key, value in attr_map.items():
        if key in {
            "aria-label",
            "class",
            "data-component",
            "data-testid",
            "data-type",
            "id",
            "role",
        }:
            relevant_values.append(value)
    if not relevant_values:
        return False

    joined = " ".join(relevant_values).lower()
    tokens = set(_ATTRIBUTE_TOKEN_PATTERN.findall(joined.replace("-", " ")))
    if tokens & _skip_attribute_tokens(policy):
        return True
    return any(phrase in joined for phrase in _skip_attribute_phrases(policy))


def _contains_any_phrase(value: str, phrases: Iterable[str]) -> bool:
    lowered = value.lower()
    return any(phrase in lowered for phrase in phrases)


def _matching_phrases(value: str, phrases: Iterable[str]) -> tuple[str, ...]:
    lowered = value.lower()
    return tuple(phrase for phrase in phrases if phrase in lowered)


def _policy_for_url(url: str) -> _ExtractionPolicy | None:
    hostname = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    for policy in _PUBLISHER_POLICIES:
        if any(
            hostname == suffix.removeprefix("www.")
            or hostname.endswith(f".{suffix.removeprefix('www.')}")
            for suffix in policy.domain_suffixes
        ):
            return policy
    return None


def _low_value_phrases(policy: _ExtractionPolicy | None) -> tuple[str, ...]:
    return _LOW_VALUE_PHRASES + (policy.low_value_phrases if policy else ())


def _paywall_or_partial_phrases(policy: _ExtractionPolicy | None) -> tuple[str, ...]:
    return _PAYWALL_OR_ACCOUNT_PHRASES + (
        policy.paywall_or_partial_phrases if policy else ()
    )


def _skip_attribute_tokens(policy: _ExtractionPolicy | None) -> set[str]:
    if policy is None:
        return _SKIP_ATTRIBUTE_TOKENS
    return _SKIP_ATTRIBUTE_TOKENS | policy.skip_attribute_tokens


def _skip_attribute_phrases(policy: _ExtractionPolicy | None) -> tuple[str, ...]:
    return _SKIP_ATTRIBUTE_PHRASES + (policy.skip_attribute_phrases if policy else ())


def _extract_with_trafilatura(
    decoded_html: str,
    *,
    base_url: str,
) -> _OptionalExtractorResult | None:
    try:
        trafilatura = import_module("trafilatura")
    except ImportError:
        return None
    extract = getattr(trafilatura, "extract", None)
    if not callable(extract):
        return None
    try:
        extracted = extract(
            decoded_html,
            url=base_url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
    except Exception:
        return None
    if not isinstance(extracted, str):
        return None
    text = _normalize_multiline(extracted)
    if len(text.split()) < 50:
        return None
    return _OptionalExtractorResult(
        text=text,
        method="trafilatura_fallback",
        metadata={
            "word_count": len(text.split()),
            "available": True,
        },
    )


def _should_use_optional_extraction(
    *,
    current_text: str,
    current_quality_score: float,
    optional_text: str,
) -> bool:
    current_word_count = len(current_text.split())
    optional_word_count = len(optional_text.split())
    if current_word_count == 0:
        return True
    if current_quality_score < 0.55 and optional_word_count >= current_word_count:
        return True
    return optional_word_count >= round(current_word_count * 1.35)


def _looks_partial_or_paywalled(
    *,
    word_count: int,
    raw_indicators: tuple[str, ...],
    text_indicators: tuple[str, ...],
) -> bool:
    if text_indicators:
        return True
    return bool(raw_indicators) and word_count < 300


def _extraction_quality_score(
    text_content: str,
    *,
    accepted_block_count: int,
    rejected_block_count: int,
    json_ld_article_detected: bool,
) -> float:
    word_count = len(text_content.split())
    if word_count == 0:
        return 0.0

    score = 0.0
    score += min(0.35, word_count / 1_000)
    score += min(0.25, accepted_block_count / 10)
    if json_ld_article_detected:
        score += 0.15

    total_blocks = accepted_block_count + rejected_block_count
    if total_blocks:
        score += 0.25 * (accepted_block_count / total_blocks)
    else:
        score += 0.10

    return round(max(0.0, min(1.0, score)), 4)
