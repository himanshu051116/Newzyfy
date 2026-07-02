from urllib.parse import urlsplit

from .models import DiscoveryChannelType, FrontierPriorityInputs

CHANNEL_BOOSTS: dict[DiscoveryChannelType, float] = {
    DiscoveryChannelType.NEWS_SITEMAP: 0.12,
    DiscoveryChannelType.WEBSUB: 0.12,
    DiscoveryChannelType.WEBHOOK: 0.12,
    DiscoveryChannelType.API: 0.08,
    DiscoveryChannelType.RSS: 0.06,
    DiscoveryChannelType.ATOM: 0.06,
    DiscoveryChannelType.SITEMAP: 0.04,
}


def normalize_domain(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate if "://" in candidate else f"https://{candidate}")
    if not parsed.hostname:
        raise ValueError("canonical domain must contain a hostname")
    return parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")


def bootstrap_priority_inputs(
    channel_type: DiscoveryChannelType,
) -> FrontierPriorityInputs:
    """Conservative priors used until measured publisher/channel metrics exist."""
    return FrontierPriorityInputs(
        freshness_probability=1.0,
        channel_historical_yield=0.5,
        expected_update_probability=0.2,
        recall_gap_impact=0.5,
        source_quality_and_coverage_value=0.5,
        event_significance=0.0,
        publication_velocity=0.3,
        breaking_news_probability=0.2,
        exploration_value=0.5,
        channel_boost=CHANNEL_BOOSTS.get(channel_type, 0.0),
    )

