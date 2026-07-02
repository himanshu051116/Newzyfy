import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

CLAIM_EXTRACTOR_VERSION = "deterministic-claim-extractor-v1"


class ClaimVerificationLabel(StrEnum):
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    MISLEADING = "misleading"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    NOT_CHECKABLE = "not_checkable"


_SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)*(?:%|bn|billion|mn|million|crore|lakh)?\b", re.I)
_DATE_PATTERN = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}"
    r"|\b\d{4}\b"
    r"|\b(?:today|yesterday|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.I,
)
_CAPITALIZED_PATTERN = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&.+-]+|[A-Z]{2,})"
    r"(?:\s+[A-Z][A-Za-z0-9&.+-]+){0,4}"
)
_REPORTING_OR_ACTION_VERBS = {
    "accused",
    "announced",
    "approved",
    "blocked",
    "charged",
    "claimed",
    "confirmed",
    "declared",
    "denied",
    "disclosed",
    "filed",
    "found",
    "launched",
    "ordered",
    "published",
    "reported",
    "released",
    "said",
    "signed",
    "sued",
    "warned",
}
_SPECULATION_MARKERS = {
    "could",
    "may",
    "might",
    "possibly",
    "rumor",
    "rumour",
    "speculation",
    "unconfirmed",
}
_LOW_VALUE_PREFIXES = (
    "advertisement",
    "also read",
    "click here",
    "follow us",
    "read more",
    "subscribe",
)


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    text: str
    sentence_index: int
    features: dict[str, object]

    @property
    def claim_sha256(self) -> str:
        return claim_sha256(self.text)


def extract_claims(text: str, *, max_claims: int = 25) -> tuple[ExtractedClaim, ...]:
    claims: list[ExtractedClaim] = []
    for index, sentence in enumerate(split_sentences(text)):
        features = claim_features(sentence)
        if features["is_claim_candidate"]:
            claims.append(
                ExtractedClaim(
                    text=sentence,
                    sentence_index=index,
                    features=features,
                )
            )
        if len(claims) >= max_claims:
            break
    return tuple(claims)


def split_sentences(text: str) -> tuple[str, ...]:
    normalized = _normalize_text(text)
    if not normalized:
        return ()
    rough_sentences = _SENTENCE_BOUNDARY_PATTERN.split(normalized)
    return tuple(
        sentence
        for sentence in (_normalize_text(item) for item in rough_sentences)
        if sentence
    )


def claim_features(sentence: str) -> dict[str, object]:
    normalized = _normalize_text(sentence)
    lowered = normalized.lower()
    words = normalized.split()
    reporting_or_action_terms = sorted(
        term for term in _REPORTING_OR_ACTION_VERBS if re.search(rf"\b{term}\b", lowered)
    )
    speculation_terms = sorted(
        term for term in _SPECULATION_MARKERS if re.search(rf"\b{term}\b", lowered)
    )
    entities = tuple(
        entity
        for entity in {
            _normalize_text(match.group(0))
            for match in _CAPITALIZED_PATTERN.finditer(normalized)
        }
        if entity and entity.lower() not in {"the", "this", "after", "before"}
    )
    has_number = bool(_NUMBER_PATTERN.search(normalized))
    has_date = bool(_DATE_PATTERN.search(normalized))
    starts_low_value = lowered.startswith(_LOW_VALUE_PREFIXES)
    word_count = len(words)
    signal_count = sum(
        [
            bool(reporting_or_action_terms),
            bool(entities),
            has_number,
            has_date,
        ]
    )
    is_claim_candidate = (
        8 <= word_count <= 80
        and not starts_low_value
        and not normalized.endswith("?")
        and signal_count >= 2
    )
    score = min(1.0, signal_count / 4 + min(word_count, 40) / 160)
    if speculation_terms:
        score = max(0.0, score - 0.2)
    return {
        "word_count": word_count,
        "has_number": has_number,
        "has_date": has_date,
        "entities": sorted(entities),
        "entity_count": len(entities),
        "reporting_or_action_terms": reporting_or_action_terms,
        "speculation_terms": speculation_terms,
        "signal_count": signal_count,
        "score": round(score, 6),
        "is_claim_candidate": is_claim_candidate,
    }


def claim_sha256(text: str) -> str:
    return sha256(_normalize_text(text).lower().encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()
