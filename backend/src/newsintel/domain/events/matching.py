import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from newsintel.domain.events.assignment import EventCandidate

POLICY_VERSION = "event-matching-lexical-v1"

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9.+_-]*")
_CAPITALIZED_PHRASE_PATTERN = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&.+-]+|[A-Z]{2,})(?:\s+(?:[A-Z][A-Za-z0-9&.+-]+|[A-Z]{2,})){0,4}"
)
_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:CVE-\d{4}-\d{4,7}|[A-Z]{2,8}-\d+|[A-Z]{2,8}|\d+(?:\.\d+)?%?)\b"
)
_LOCATION_TERMS = {
    "afghanistan",
    "africa",
    "america",
    "australia",
    "bangalore",
    "beijing",
    "bengaluru",
    "bihar",
    "brazil",
    "britain",
    "canada",
    "china",
    "delhi",
    "europe",
    "france",
    "gaza",
    "germany",
    "gujarat",
    "india",
    "iran",
    "israel",
    "japan",
    "karnataka",
    "kerala",
    "kolkata",
    "london",
    "maharashtra",
    "mumbai",
    "new york",
    "pakistan",
    "paris",
    "punjab",
    "russia",
    "tel aviv",
    "tokyo",
    "uk",
    "ukraine",
    "united kingdom",
    "united states",
    "us",
    "usa",
    "washington",
}
_STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "amid",
    "among",
    "and",
    "are",
    "around",
    "as",
    "at",
    "be",
    "been",
    "before",
    "being",
    "between",
    "but",
    "by",
    "can",
    "could",
    "during",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "more",
    "new",
    "not",
    "of",
    "on",
    "or",
    "over",
    "said",
    "says",
    "she",
    "that",
    "the",
    "their",
    "they",
    "this",
    "to",
    "up",
    "was",
    "were",
    "what",
    "when",
    "which",
    "while",
    "who",
    "will",
    "with",
}


@dataclass(frozen=True, slots=True)
class ArticleEventProfile:
    title: str
    text: str
    published_at: datetime | None = None
    observed_at: datetime | None = None
    title_tokens: frozenset[str] = field(init=False)
    content_tokens: frozenset[str] = field(init=False)
    title_shingles: frozenset[str] = field(init=False)
    content_shingles: frozenset[str] = field(init=False)
    entities: frozenset[str] = field(init=False)
    identifiers: frozenset[str] = field(init=False)
    locations: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        text = f"{self.title}\n{self.text}"
        title_token_sequence = _tokens(self.title)
        content_token_sequence = _tokens(text)
        object.__setattr__(self, "title_tokens", frozenset(title_token_sequence))
        object.__setattr__(self, "content_tokens", frozenset(content_token_sequence))
        object.__setattr__(
            self,
            "title_shingles",
            _shingles(title_token_sequence, size=2),
        )
        object.__setattr__(
            self,
            "content_shingles",
            _shingles(content_token_sequence, size=3),
        )
        object.__setattr__(self, "entities", frozenset(_entities(text)))
        object.__setattr__(self, "identifiers", frozenset(_identifiers(text)))
        object.__setattr__(self, "locations", frozenset(_locations(text)))


@dataclass(frozen=True, slots=True)
class EventReference:
    event_id: UUID
    title: str
    text: str
    first_detected_at: datetime
    latest_observed_at: datetime | None = None

    @property
    def profile(self) -> ArticleEventProfile:
        return ArticleEventProfile(
            title=self.title,
            text=self.text,
            observed_at=self.latest_observed_at or self.first_detected_at,
        )


def build_event_candidates(
    incoming: ArticleEventProfile,
    references: Sequence[EventReference],
    *,
    limit: int = 20,
) -> tuple[EventCandidate, ...]:
    candidates = [
        _candidate_for_reference(incoming, reference)
        for reference in references
    ]
    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
    return tuple(ranked[:limit])


def event_candidate_features(candidate: EventCandidate) -> dict[str, float]:
    return {
        "semantic_similarity": round(candidate.semantic_similarity, 6),
        "title_similarity": round(candidate.title_similarity, 6),
        "entity_overlap": round(candidate.entity_overlap, 6),
        "identifier_overlap": round(candidate.identifier_overlap, 6),
        "claim_overlap": round(candidate.claim_overlap, 6),
        "temporal_compatibility": round(candidate.temporal_compatibility, 6),
        "geographic_compatibility": round(candidate.geographic_compatibility, 6),
        "event_type_compatibility": round(candidate.event_type_compatibility, 6),
        "score": round(candidate.score, 6),
    }


def provisional_event_features(candidates: Sequence[EventCandidate]) -> dict[str, float]:
    if not candidates:
        return {"candidate_count": 0.0}
    best = candidates[0]
    return {
        "candidate_count": float(len(candidates)),
        "best_rejected_score": round(best.score, 6),
        "best_rejected_semantic_similarity": round(best.semantic_similarity, 6),
        "best_rejected_title_similarity": round(best.title_similarity, 6),
    }


def _candidate_for_reference(
    incoming: ArticleEventProfile,
    reference: EventReference,
) -> EventCandidate:
    existing = reference.profile
    semantic_similarity = _weighted_similarity(
        incoming.content_tokens,
        existing.content_tokens,
        incoming.content_shingles,
        existing.content_shingles,
    )
    title_similarity = _weighted_similarity(
        incoming.title_tokens,
        existing.title_tokens,
        incoming.title_shingles,
        existing.title_shingles,
        token_weight=0.7,
        shingle_weight=0.3,
    )
    return EventCandidate(
        event_id=reference.event_id,
        semantic_similarity=semantic_similarity,
        title_similarity=title_similarity,
        entity_overlap=_overlap_or_unknown(incoming.entities, existing.entities),
        identifier_overlap=_overlap_or_unknown(
            incoming.identifiers,
            existing.identifiers,
        ),
        claim_overlap=_jaccard(incoming.content_shingles, existing.content_shingles),
        temporal_compatibility=_temporal_compatibility(
            incoming.published_at or incoming.observed_at,
            existing.observed_at or reference.first_detected_at,
        ),
        geographic_compatibility=_geographic_compatibility(
            incoming.locations,
            existing.locations,
        ),
        event_type_compatibility=0.5,
    )


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in _TOKEN_PATTERN.findall(text.lower())
        if len(token) >= 3 and token not in _STOPWORDS
    )


def _shingles(tokens: Sequence[str], *, size: int) -> frozenset[str]:
    if len(tokens) < size:
        return frozenset()
    return frozenset(
        " ".join(tokens[index : index + size])
        for index in range(len(tokens) - size + 1)
    )


def _entities(text: str) -> Iterable[str]:
    ignored = {"The", "A", "An", "In", "On", "At", "By", "After", "Before", "This"}
    for match in _CAPITALIZED_PHRASE_PATTERN.finditer(text):
        entity = " ".join(match.group(0).split())
        if entity in ignored:
            continue
        if len(entity) < 3:
            continue
        if entity.split()[0] in ignored and len(entity.split()) == 1:
            continue
        yield entity.lower()


def _identifiers(text: str) -> Iterable[str]:
    for match in _IDENTIFIER_PATTERN.finditer(text):
        value = match.group(0)
        if value in {"The", "This", "After", "Before"}:
            continue
        yield value.lower()


def _locations(text: str) -> Iterable[str]:
    lowered = text.lower()
    for term in _LOCATION_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", lowered):
            yield term


def _weighted_similarity(
    left_tokens: frozenset[str],
    right_tokens: frozenset[str],
    left_shingles: frozenset[str],
    right_shingles: frozenset[str],
    *,
    token_weight: float = 0.45,
    shingle_weight: float = 0.55,
) -> float:
    return (
        token_weight * _jaccard(left_tokens, right_tokens)
        + shingle_weight * _jaccard(left_shingles, right_shingles)
    )


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _overlap_or_unknown(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 0.5
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _geographic_compatibility(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 0.5
    if not left or not right:
        return 0.2
    return _overlap_or_unknown(left, right)


def _temporal_compatibility(
    left: datetime | None,
    right: datetime | None,
) -> float:
    if left is None or right is None:
        return 0.5
    left_utc = left.astimezone(UTC) if left.tzinfo else left.replace(tzinfo=UTC)
    right_utc = right.astimezone(UTC) if right.tzinfo else right.replace(tzinfo=UTC)
    days = abs((left_utc - right_utc).total_seconds()) / 86_400
    if days <= 1:
        return 1.0
    if days <= 3:
        return 0.85
    if days <= 7:
        return 0.65
    if days <= 14:
        return 0.4
    if days <= 30:
        return 0.2
    return 0.05


def top_terms(text: str, *, limit: int = 12) -> tuple[str, ...]:
    counts = Counter(_tokens(text))
    return tuple(term for term, _count in counts.most_common(limit))
