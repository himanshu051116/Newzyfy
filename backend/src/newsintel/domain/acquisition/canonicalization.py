from dataclasses import dataclass, field
from hashlib import sha256
from posixpath import normpath
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

DEFAULT_TRACKING_PARAMETERS = frozenset(
    {
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "ref",
        "referrer",
        "source",
        "utm_campaign",
        "utm_content",
        "utm_medium",
        "utm_source",
        "utm_term",
    }
)


@dataclass(frozen=True, slots=True)
class CanonicalizationPolicy:
    drop_parameters: frozenset[str] = DEFAULT_TRACKING_PARAMETERS
    keep_only_parameters: frozenset[str] = field(default_factory=frozenset)
    strip_www: bool = False
    force_https: bool = False


@dataclass(frozen=True, slots=True)
class CanonicalUrl:
    original: str
    normalized: str
    fingerprint: str
    removed_parameters: tuple[str, ...]


def canonicalize_url(url: str, policy: CanonicalizationPolicy | None = None) -> CanonicalUrl:
    policy = policy or CanonicalizationPolicy()
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("only HTTP and HTTPS URLs are supported")
    if not parsed.hostname:
        raise ValueError("URL must contain a hostname")

    scheme = "https" if policy.force_https else parsed.scheme.lower()
    host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if policy.strip_www and host.startswith("www."):
        host = host[4:]

    port = parsed.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    raw_path = parsed.path or "/"
    normalized_path = normpath(raw_path)
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if raw_path.endswith("/") and normalized_path != "/":
        normalized_path = f"{normalized_path}/"
    normalized_path = quote(normalized_path, safe="/%:@!$&'()*+,;=-._~")

    kept: list[tuple[str, str]] = []
    removed: list[str] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        should_keep = (
            lowered not in policy.drop_parameters
            and (
                not policy.keep_only_parameters
                or lowered in policy.keep_only_parameters
            )
        )
        if should_keep:
            kept.append((key, value))
        else:
            removed.append(key)
    kept.sort(key=lambda item: (item[0].lower(), item[1]))

    normalized = urlunsplit((scheme, netloc, normalized_path, urlencode(kept), ""))
    return CanonicalUrl(
        original=url,
        normalized=normalized,
        fingerprint=sha256(normalized.encode("utf-8")).hexdigest(),
        removed_parameters=tuple(sorted(set(removed), key=str.lower)),
    )

