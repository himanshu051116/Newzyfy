from datetime import UTC, datetime, timedelta
from uuid import UUID

from newsintel.domain.events.assignment import EventAssignmentState, decide_event_assignment
from newsintel.domain.events.matching import (
    ArticleEventProfile,
    EventReference,
    build_event_candidates,
    event_candidate_features,
)


def test_matching_links_same_real_world_event() -> None:
    observed_at = datetime(2026, 6, 26, 9, tzinfo=UTC)
    incoming = ArticleEventProfile(
        title="ISRO launches new satellite imaging mission from Sriharikota",
        text=(
            "ISRO launched a satellite imaging mission from Sriharikota to improve "
            "earth observation and disaster monitoring coverage across India."
        ),
        published_at=observed_at,
        observed_at=observed_at,
    )
    reference = EventReference(
        event_id=UUID(int=1),
        title="ISRO launches satellite imaging mission from Sriharikota",
        text=(
            "India's space agency ISRO launched a new satellite imaging mission "
            "from Sriharikota for earth observation and disaster monitoring."
        ),
        first_detected_at=observed_at - timedelta(hours=1),
        latest_observed_at=observed_at - timedelta(minutes=30),
    )

    candidates = build_event_candidates(incoming, [reference])
    decision = decide_event_assignment(candidates)

    assert decision.selected_event_id == UUID(int=1)
    assert decision.state in {
        EventAssignmentState.CANDIDATE,
        EventAssignmentState.CONFIRMED,
    }
    assert decision.selected_score is not None
    assert decision.selected_score >= 0.62
    assert event_candidate_features(candidates[0])["score"] >= 0.62


def test_matching_rejects_unrelated_story() -> None:
    observed_at = datetime(2026, 6, 26, 9, tzinfo=UTC)
    incoming = ArticleEventProfile(
        title="Cybersecurity firm discloses critical router vulnerability",
        text=(
            "Researchers disclosed a CVE affecting enterprise routers and urged "
            "administrators to patch exposed devices."
        ),
        published_at=observed_at,
        observed_at=observed_at,
    )
    reference = EventReference(
        event_id=UUID(int=2),
        title="India announces new monsoon crop procurement policy",
        text=(
            "The agriculture ministry announced procurement rules for rice and "
            "pulses after monsoon forecasts improved."
        ),
        first_detected_at=observed_at,
        latest_observed_at=observed_at,
    )

    candidates = build_event_candidates(incoming, [reference])
    decision = decide_event_assignment(candidates)

    assert decision.state is EventAssignmentState.PROVISIONAL
    assert decision.selected_event_id is None


def test_matching_temporal_distance_reduces_score() -> None:
    current = datetime(2026, 6, 26, 9, tzinfo=UTC)
    incoming = ArticleEventProfile(
        title="Company reports data breach affecting customer accounts",
        text="The company said attackers accessed customer accounts in a data breach.",
        published_at=current,
        observed_at=current,
    )
    recent = EventReference(
        event_id=UUID(int=3),
        title="Company reports data breach affecting customer accounts",
        text="Attackers accessed customer accounts in a company data breach.",
        first_detected_at=current - timedelta(hours=2),
        latest_observed_at=current - timedelta(hours=1),
    )
    old = EventReference(
        event_id=UUID(int=4),
        title="Company reports data breach affecting customer accounts",
        text="Attackers accessed customer accounts in a company data breach.",
        first_detected_at=current - timedelta(days=40),
        latest_observed_at=current - timedelta(days=40),
    )

    candidates = build_event_candidates(incoming, [old, recent])
    by_id = {candidate.event_id: candidate for candidate in candidates}

    assert by_id[UUID(int=3)].temporal_compatibility == 1.0
    assert by_id[UUID(int=4)].temporal_compatibility == 0.05
    assert by_id[UUID(int=3)].score > by_id[UUID(int=4)].score
