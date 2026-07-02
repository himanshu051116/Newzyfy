from newsintel.domain.intelligence.claims import (
    CLAIM_EXTRACTOR_VERSION,
    ClaimVerificationLabel,
    claim_sha256,
    extract_claims,
    split_sentences,
)


def test_extract_claims_selects_factual_sentences() -> None:
    text = """
    Advertisement. ISRO launched a satellite imaging mission from Sriharikota on June 26, 2026.
    The mission will support disaster monitoring across India, officials said.
    What does this mean for investors?
    Analysts could possibly expect broader commercial demand.
    The company reported revenue rose 18% in 2026 after new contracts.
    """

    claims = extract_claims(text)

    assert CLAIM_EXTRACTOR_VERSION == "deterministic-claim-extractor-v1"
    assert len(claims) == 3
    assert claims[0].text == (
        "ISRO launched a satellite imaging mission from Sriharikota on June 26, 2026."
    )
    assert claims[0].features["has_date"] is True
    assert claims[0].features["entity_count"] >= 1
    assert all(not claim.text.endswith("?") for claim in claims)


def test_claim_hash_is_normalized() -> None:
    first = claim_sha256("Company reported revenue rose 18%.")
    second = claim_sha256(" company   reported revenue rose 18%. ")

    assert first == second


def test_sentence_splitter_preserves_exact_claim_text() -> None:
    sentences = split_sentences("Company filed a case. Court approved the request.")

    assert sentences == (
        "Company filed a case.",
        "Court approved the request.",
    )


def test_verification_labels_match_allowed_contract() -> None:
    assert {item.value for item in ClaimVerificationLabel} == {
        "supported",
        "disputed",
        "misleading",
        "unsupported",
        "contradicted",
        "not_checkable",
    }
