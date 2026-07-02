from .models import FrontierPriority, FrontierPriorityInputs

POLICY_VERSION = "frontier-v1"


def calculate_frontier_priority(inputs: FrontierPriorityInputs) -> FrontierPriority:
    components = {
        "freshness_probability": 0.22 * inputs.freshness_probability,
        "channel_historical_yield": 0.15 * inputs.channel_historical_yield,
        "expected_update_probability": 0.12 * inputs.expected_update_probability,
        "recall_gap_impact": 0.10 * inputs.recall_gap_impact,
        "source_quality_and_coverage_value": (
            0.10 * inputs.source_quality_and_coverage_value
        ),
        "event_significance": 0.10 * inputs.event_significance,
        "publication_velocity": 0.08 * inputs.publication_velocity,
        "breaking_news_probability": 0.08 * inputs.breaking_news_probability,
        "exploration_value": 0.05 * inputs.exploration_value,
        "channel_boost": inputs.channel_boost,
        "host_saturation_penalty": -inputs.host_saturation_penalty,
        "retry_penalty": -inputs.retry_penalty,
        "expected_cost_penalty": -inputs.expected_cost_penalty,
    }
    raw_score = sum(components.values())
    return FrontierPriority(
        score=max(0.0, min(1.0, raw_score)),
        components=components,
        policy_version=POLICY_VERSION,
    )

