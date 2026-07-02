import pytest

from newsintel.domain.acquisition.frontier import calculate_frontier_priority
from newsintel.domain.acquisition.models import FrontierPriorityInputs


def test_priority_is_reproducible_and_exposes_components() -> None:
    inputs = FrontierPriorityInputs(
        freshness_probability=1,
        channel_historical_yield=0.8,
        expected_update_probability=0.4,
        recall_gap_impact=0.9,
        source_quality_and_coverage_value=0.7,
        event_significance=0.6,
        publication_velocity=0.5,
        breaking_news_probability=0.3,
        exploration_value=0.2,
        channel_boost=0.05,
        host_saturation_penalty=0.04,
    )

    first = calculate_frontier_priority(inputs)
    second = calculate_frontier_priority(inputs)

    assert first == second
    assert first.policy_version == "frontier-v1"
    assert first.score == pytest.approx(sum(first.components.values()))
    assert first.components["host_saturation_penalty"] == -0.04


def test_invalid_feature_is_rejected() -> None:
    with pytest.raises(ValueError):
        FrontierPriorityInputs(
            freshness_probability=1.1,
            channel_historical_yield=0,
            expected_update_probability=0,
            recall_gap_impact=0,
            source_quality_and_coverage_value=0,
            event_significance=0,
            publication_velocity=0,
            breaking_news_probability=0,
            exploration_value=0,
        )

