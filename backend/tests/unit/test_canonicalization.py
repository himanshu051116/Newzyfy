import pytest

from newsintel.domain.acquisition.canonicalization import (
    CanonicalizationPolicy,
    canonicalize_url,
)


def test_canonicalizes_tracking_parameters_and_fragment() -> None:
    result = canonicalize_url(
        "HTTPS://WWW.Example.com:443/news/../news/story/?utm_source=x&id=42#comments"
    )

    assert result.normalized == "https://www.example.com/news/story/?id=42"
    assert result.removed_parameters == ("utm_source",)
    assert len(result.fingerprint) == 64


def test_publisher_policy_can_strip_www_and_keep_only_identity_parameter() -> None:
    result = canonicalize_url(
        "http://www.example.com/article?story=7&page=2&ref=home",
        CanonicalizationPolicy(
            strip_www=True,
            force_https=True,
            keep_only_parameters=frozenset({"story"}),
        ),
    )

    assert result.normalized == "https://example.com/article?story=7"
    assert set(result.removed_parameters) == {"page", "ref"}


def test_rejects_non_http_urls() -> None:
    with pytest.raises(ValueError):
        canonicalize_url("file:///etc/passwd")

