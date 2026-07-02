from newsintel.domain.acquisition.change_detection import (
    compare_link_sets,
    create_link_set_snapshot,
)


def test_detects_inserted_and_removed_article_links() -> None:
    previous = create_link_set_snapshot(
        "https://example.com/news",
        '<a href="/a?utm_source=home">A</a><a href="/b">B</a>',
    )
    current = create_link_set_snapshot(
        "https://example.com/news",
        '<a href="/b">B</a><a href="/c">C</a>',
    )

    diff = compare_link_sets(previous, current)

    assert diff.inserted == frozenset({"https://example.com/c"})
    assert diff.removed == frozenset({"https://example.com/a"})
    assert diff.unchanged == frozenset({"https://example.com/b"})
    assert diff.materially_changed


def test_template_text_changes_do_not_change_link_set() -> None:
    previous = create_link_set_snapshot(
        "https://example.com",
        '<div class="old"><a href="/story">Old label</a></div>',
    )
    current = create_link_set_snapshot(
        "https://example.com",
        '<section class="new"><a href="/story">New label</a></section>',
    )

    assert not compare_link_sets(previous, current).materially_changed

