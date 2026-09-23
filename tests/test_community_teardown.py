"""Offline checks of the community teardown recipe; no Hacker News requests or model calls."""

import json
import re
from pathlib import Path

import pytest

RESOURCE = (
    Path(__file__).parents[1]
    / "workflow_packages/growth.community_teardown/skills/community-teardown/RANKING.md"
)
FIXTURES = Path(__file__).parent / "fixtures/community_teardown"


@pytest.fixture
def recipe():
    # This exact reviewed repository resource is executable inside the procedure sandbox.
    # Never use this loader for packages submitted to the qualification service.
    blocks = re.findall(r"```python\n(.*?)\n```", RESOURCE.read_text(), re.S)
    assert len(blocks) == 1
    namespace = {}
    exec(compile(blocks[0], str(RESOURCE), "exec"), namespace)  # noqa: S102 - fixed, reviewed fixture
    return namespace


def stories():
    return json.loads((FIXTURES / "stories.json").read_text())["hits"]


def comments():
    return json.loads((FIXTURES / "comments.json").read_text())["hits"]


def threads(recipe):
    parsed = []
    for hit in stories():
        parsed.append(recipe["parse_thread"](hit, comments()))
    story_records = [row["story"] for row in parsed]
    picked = recipe["select_threads"](story_records, limit=4)
    picked_ids = {row["objectID"] for row in picked}
    return [row for row in parsed if row["story"]["objectID"] in picked_ids]


def test_epoch_before_is_bounded_and_deterministic(recipe):
    now = 1_800_000_000
    assert recipe["epoch_before"](7, now=now) == now - 7 * 86400
    assert recipe["epoch_before"](730, now=now) == now - 730 * 86400
    for days in (6, 731):
        with pytest.raises(ValueError):
            recipe["epoch_before"](days, now=now)


def test_select_threads_prefers_discussion_and_drops_dead_posts(recipe):
    parsed = [recipe["parse_thread"](hit, comments()) for hit in stories()]
    story_records = [row["story"] for row in parsed]
    picked = recipe["select_threads"](story_records, limit=4)
    assert [row["objectID"] for row in picked] == ["44520003", "44520001", "44520005", "44520007"]
    assert all(row["score"] > 0 for row in picked)
    # The zero-comment job post never appears, even at a wide limit.
    ids = {row["objectID"] for row in recipe["select_threads"](story_records, limit=8)}
    assert "44520006" not in ids


def test_select_threads_dedupes_and_bounds(recipe):
    hits = stories() + [stories()[0]]
    assert len(recipe["select_threads"](hits, limit=8)) <= len({row["objectID"] for row in hits})
    with pytest.raises(ValueError):
        recipe["select_threads"](hits, limit=0)


def test_parse_increases_and_fixture_stays_valid(recipe):
    hit = stories()[0]
    story = recipe["parse_story"](hit)
    assert story == {
        "objectID": "44520001",
        "title": "Ask HN: What's everyone using for bursty GPU batch jobs?",
        "url": "",
        "points": 86,
        "num_comments": 42,
        "author": "ana",
        "created_at": "2026-06-01T08:00:00Z",
    }
    with pytest.raises(ValueError):
        recipe["parse_story"]({"title": "no id"})
    empty = {"comment_text": ""}
    assert recipe["parse_comments"]([empty, comments()[0]]) == [
        {
            "text": comments()[0]["comment_text"],
            "author": "mlguru",
            "created_at": "2026-06-01T09:11:00Z",
        }
    ]


def test_validate_thread_rejects_bad_shapes(recipe):
    story = recipe["parse_story"](stories()[0])
    good = recipe["parse_thread"](story, comments())
    assert recipe["validate_thread"](good) is good

    thread = {"story": {}, "comments": []}
    with pytest.raises(ValueError, match="objectID"):
        recipe["validate_thread"](thread)

    thread = {"story": story, "comments": [{"text": "   "}]}
    with pytest.raises(ValueError, match="empty"):
        recipe["validate_thread"](thread)

    thread = {"story": story, "comments": [{"text": "x" * 20_000}]}
    with pytest.raises(ValueError, match="too large"):
        recipe["validate_thread"](thread)

    for bad in (None, {"story": story}, {"story": story, "comments": "nope"}):
        with pytest.raises(ValueError):
            recipe["validate_thread"](bad)


def test_rank_grades_evidence_fit_and_dedupes(recipe):
    commits = [
        {
            "kind": "content_topic",
            "quote": "cheaper than keeping a big reserved cluster around",
            "author": "clusterfan",
            "thread_id": "44520003",
            "extra_thread_ids": ["44520001"],
        },
        {
            "kind": "content_topic",
            "quote": "per-GPU cost dropped a lot on a spot pool",
            "author": "mlguru",
            "thread_id": "44520001",
        },
        {
            "kind": "product_signal",
            "quote": "pricing pages hide the per-GPU cost",
            "author": "devrel",
            "thread_id": "44520005",
        },
        {
            "kind": "engagement_candidate",
            "quote": "anything that just syncs folders across three devices?",
            "author": "syncseeker",
            "thread_id": "44520007",
        },
    ]
    ledger = recipe["rank_opportunities"](
        threads(recipe),
        buyer_context="cheap burst gpu batch computing",
        commits=commits,
    )
    assert ledger[0]["kind"] == "content_topic"
    assert ledger[0]["evidence"] == 2
    assert set(ledger[0]["occurrences"]) == {"44520001", "44520003"}
    assert ledger[0]["url"] == "https://news.ycombinator.com/item?id=44520003"
    assert {row["kind"] for row in ledger} == {
        "content_topic",
        "product_signal",
        "engagement_candidate",
    }


def test_rank_rejects_unknown_kinds_and_unread_threads(recipe):
    story = recipe["parse_story"](stories()[0])
    parsed = [recipe["parse_thread"](story, comments())]
    with pytest.raises(ValueError, match="unknown opportunity kind"):
        recipe["rank_opportunities"](
            parsed,
            commits=[{"kind": "backlink", "quote": "x", "thread_id": "44520003"}],
        )
    with pytest.raises(ValueError, match="was not read"):
        recipe["rank_opportunities"](
            parsed,
            commits=[{"kind": "content_topic", "quote": "x", "thread_id": "44520099"}],
        )
    assert recipe["rank_opportunities"]([], commits=[]) == []


def test_rank_dedupes_identical_ideas(recipe):
    story = recipe["parse_story"](stories()[0])
    parsed = [recipe["parse_thread"](story, comments())]
    commits = [
        {
            "kind": "content_topic",
            "quote": "burst gpu too expensive to rent",
            "author": "a",
            "thread_id": "44520001",
        },
        {
            "kind": "content_topic",
            "quote": "burst gpu too expensive to rent",
            "author": "b",
            "thread_id": "44520001",
        },
    ]
    ledger = recipe["rank_opportunities"](parsed, buyer_context="gpu", commits=commits)
    assert len(ledger) == 1
