from uuid import UUID

from newsintel.domain.events.assignment import (
    EventAssignmentState,
    EventCandidate,
    decide_event_assignment,
)


def _candidate(event_id: int, **overrides: float) -> EventCandidate:
    values = {
        "semantic_similarity": 0.9,
        "title_similarity": 0.8,
        "entity_overlap": 0.9,
        "identifier_overlap": 0.9,
        "claim_overlap": 0.8,
        "temporal_compatibility": 0.9,
        "geographic_compatibility": 0.8,
        "event_type_compatibility": 0.8,
    }
    values.update(overrides)
    return EventCandidate(event_id=UUID(int=event_id), **values)


def test_confirms_clear_high_scoring_event() -> None:
    decision = decide_event_assignment([_candidate(1)])

    assert decision.state is EventAssignmentState.CONFIRMED
    assert decision.selected_event_id == UUID(int=1)


def test_keeps_ambiguous_assignment_as_candidate() -> None:
    decision = decide_event_assignment(
        [
            _candidate(1),
            _candidate(2, semantic_similarity=0.89),
        ]
    )

    assert decision.state is EventAssignmentState.CANDIDATE
    assert decision.selected_event_id == UUID(int=1)


def test_creates_provisional_event_when_no_candidate_is_good_enough() -> None:
    weak = _candidate(
        1,
        semantic_similarity=0.2,
        title_similarity=0.1,
        entity_overlap=0.1,
        identifier_overlap=0,
        claim_overlap=0.1,
        temporal_compatibility=0.2,
        geographic_compatibility=0.2,
        event_type_compatibility=0.2,
    )

    decision = decide_event_assignment([weak])

    assert decision.state is EventAssignmentState.PROVISIONAL
    assert decision.selected_event_id is None

