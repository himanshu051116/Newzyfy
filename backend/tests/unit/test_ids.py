from newsintel.core.ids import uuid7


def test_uuid7_has_expected_version_and_variant() -> None:
    value = uuid7()

    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_uuid7_is_time_ordered_across_separate_milliseconds(monkeypatch) -> None:
    timestamps = iter([1_000_000_000, 1_001_000_000])
    monkeypatch.setattr("newsintel.core.ids.time.time_ns", lambda: next(timestamps))

    assert uuid7().int < uuid7().int

