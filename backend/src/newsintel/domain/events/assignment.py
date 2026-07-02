from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class EventAssignmentState(StrEnum):
    PROVISIONAL = "provisional"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"


@dataclass(frozen=True, slots=True)
class EventCandidate:
    event_id: UUID
    semantic_similarity: float
    title_similarity: float
    entity_overlap: float
    identifier_overlap: float
    claim_overlap: float
    temporal_compatibility: float
    geographic_compatibility: float
    event_type_compatibility: float

    def __post_init__(self) -> None:
        values = (
            self.semantic_similarity,
            self.title_similarity,
            self.entity_overlap,
            self.identifier_overlap,
            self.claim_overlap,
            self.temporal_compatibility,
            self.geographic_compatibility,
            self.event_type_compatibility,
        )
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("event candidate features must be between 0 and 1")

    @property
    def score(self) -> float:
        return (
            0.35 * self.semantic_similarity
            + 0.10 * self.title_similarity
            + 0.15 * self.entity_overlap
            + 0.15 * self.identifier_overlap
            + 0.10 * self.claim_overlap
            + 0.07 * self.temporal_compatibility
            + 0.05 * self.geographic_compatibility
            + 0.03 * self.event_type_compatibility
        )


@dataclass(frozen=True, slots=True)
class EventAssignmentDecision:
    state: EventAssignmentState
    selected_event_id: UUID | None
    selected_score: float | None
    candidates: tuple[EventCandidate, ...]
    policy_version: str = "event-assignment-v1"


def decide_event_assignment(
    candidates: Sequence[EventCandidate],
    *,
    confirmed_threshold: float = 0.78,
    candidate_threshold: float = 0.62,
    ambiguity_margin: float = 0.05,
) -> EventAssignmentDecision:
    ranked = tuple(sorted(candidates, key=lambda item: item.score, reverse=True))
    if not ranked or ranked[0].score < candidate_threshold:
        return EventAssignmentDecision(
            state=EventAssignmentState.PROVISIONAL,
            selected_event_id=None,
            selected_score=None,
            candidates=ranked,
        )

    best = ranked[0]
    ambiguous = len(ranked) > 1 and (best.score - ranked[1].score) < ambiguity_margin
    state = (
        EventAssignmentState.CONFIRMED
        if best.score >= confirmed_threshold and not ambiguous
        else EventAssignmentState.CANDIDATE
    )
    return EventAssignmentDecision(
        state=state,
        selected_event_id=best.event_id,
        selected_score=best.score,
        candidates=ranked,
    )

