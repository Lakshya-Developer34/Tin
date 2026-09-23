# Ranking and validation helpers

This file carries one deterministic Python block that the procedure sandbox loads and the
offline test suite executes verbatim. Keep it standard-library-only, deterministic and
independent of the network. Use it unchanged for every run.

```python
import re
import time

OPPORTUNITY_KINDS = frozenset(
    {"content_topic", "positioning_phrase", "product_signal", "engagement_candidate"}
)


def epoch_before(days, *, now=None):
    """Unix seconds `days` before now, bounded to the declared input range."""
    days = int(days)
    if not 7 <= days <= 730:
        raise ValueError("window_days must be between 7 and 730")
    base = now if now is not None else time.time()
    return int(base) - days * 86400


def story_key(hit):
    """A string identity every story record must carry."""
    key = str(hit.get("objectID", "")).strip()
    if not key:
        raise ValueError("story hit carries no objectID")
    return key


def parse_story(hit):
    """Map one /api/v1/search story hit to the record the report uses."""
    if not isinstance(hit, dict):
        raise ValueError("story hit must be an object")
    key = story_key(hit)
    return {
        "objectID": key,
        "title": str(hit.get("title") or "").strip(),
        "url": str(hit.get("url") or "").strip(),
        "points": int(hit.get("points") or 0),
        "num_comments": int(hit.get("num_comments") or 0),
        "author": str(hit.get("author") or "").strip(),
        "created_at": str(hit.get("created_at") or "").strip(),
    }


def parse_comments(comment_hits, *, max_comments=40):
    """Map /api/v1/search_by_date comment hits to bounded {text, author} rows."""
    if not 1 <= max_comments <= 200:
        raise ValueError("max_comments must be between 1 and 200")
    rows = []
    for hit in comment_hits or []:
        if not isinstance(hit, dict):
            raise ValueError("comment hit must be an object")
        text = str(hit.get("comment_text") or "").strip()
        if not text:
            continue
        rows.append(
            {
                "text": text[:16000],
                "author": str(hit.get("author") or "").strip(),
                "created_at": str(hit.get("created_at") or "").strip(),
            }
        )
        if len(rows) >= max_comments:
            break
    return rows


def parse_thread(story_hit, comment_hits, *, max_comments=40):
    """Build a thread record from one story hit and its comment hits."""
    return {
        "story": parse_story(story_hit),
        "comments": parse_comments(comment_hits, max_comments=max_comments),
    }


def select_threads(stories, *, limit=4):
    """Choose the threads worth reading: bounded, deterministic, discussion-first."""
    if not 1 <= limit <= 8:
        raise ValueError("thread limit must be between 1 and 8")
    rows = []
    for story in stories or []:
        if not isinstance(story, dict):
            raise ValueError("story record must be an object")
        key = story_key(story)
        comments = int(story.get("num_comments") or 0)
        points = int(story.get("points") or 0)
        title = str(story.get("title") or "").strip()
        if comments < 1:
            continue
        rows.append(
            {
                "objectID": key,
                "title": title,
                "score": 2 * comments + points,
            }
        )
    rows.sort(key=lambda row: (-row["score"], row["objectID"]))
    seen, picked = set(), []
    for row in rows:
        if row["objectID"] in seen:
            continue
        seen.add(row["objectID"])
        picked.append(row)
        if len(picked) >= limit:
            break
    return picked


def validate_thread(thread):
    """Reject malformed thread records before anything downstream trusts them."""
    if not isinstance(thread, dict):
        raise ValueError("thread must be an object")
    story = thread.get("story")
    if not isinstance(story, dict):
        raise ValueError("thread misses its story record")
    story_key(story)
    comments = thread.get("comments")
    if not isinstance(comments, list):
        raise ValueError("thread comments must be a list")
    if not 0 <= len(comments) <= 200:
        raise ValueError("thread comment count is out of bounds")
    for comment in comments:
        if not isinstance(comment, dict) or not isinstance(comment.get("text"), str):
            raise ValueError("comment record must carry text")
        text = comment["text"].strip()
        if not text:
            raise ValueError("comment text cannot be empty")
        if len(text) > 16000:
            raise ValueError("comment text is too large")
    return thread


def _tokens(text):
    return set(re.findall(r"[a-z0-9]{2,}", (text or "").lower()))


def rank_opportunities(threads, buyer_context="", commits=None, *, top=8):
    """Grade, deduplicate and rank teardown observations into the opportunity ledger.

    threads: validated thread records ({story, comments}).
    commits: observations the agent extracted from the comments, each
      {"kind", "quote", "author", "thread_id", "extra_thread_ids": [...]}.
    A higher score means more independent evidence and a closer fit to the buyer
    context. Identical ideas with the same quote stem are kept once. Each ledger row
    links back to a thread that was actually read.
    """
    if not 1 <= top <= 20:
        raise ValueError("ledger top must be between 1 and 20")
    threads = [validate_thread(thread) for thread in threads or []]
    by_id = {}
    for thread in threads:
        by_id[str(thread["story"]["objectID"])] = thread
    context_tokens = _tokens(buyer_context)
    rows = []
    for record in commits or []:
        if not isinstance(record, dict):
            raise ValueError("each commit must be an object")
        kind = record.get("kind")
        if kind not in OPPORTUNITY_KINDS:
            raise ValueError(f"unknown opportunity kind: {kind!r}")
        thread_key = str(record.get("thread_id") or "").strip()
        thread = by_id.get(thread_key)
        quote = str(record.get("quote") or "").strip()
        if thread is None:
            raise ValueError(f"commit references a thread that was not read: {thread_key}")
        if not quote:
            raise ValueError("opportunity quote cannot be empty")
        extras = {str(value) for value in record.get("extra_thread_ids") or []}
        occurrences = sorted({thread_key, *extras}.intersection(by_id))
        evidence = len(occurrences)
        fit = len(context_tokens & _tokens(quote))
        if fit > 4:
            fit = 4
        rows.append(
            {
                "kind": kind,
                "quote": quote,
                "author": str(record.get("author") or "").strip(),
                "thread_id": thread_key,
                "occurrences": occurrences,
                "evidence": evidence,
                "fit": fit,
                "score": round(evidence * 2 + fit, 2),
                "marker": f"{kind}:{re.sub(r'[^a-z0-9]+', ' ', quote.lower())[:90]}",
            }
        )
    seen, ledger = set(), []
    for row in sorted(rows, key=lambda row: (-row["score"], row["thread_id"], row["quote"])):
        if row["marker"] in seen:
            continue
        seen.add(row["marker"])
        story = by_id[row["thread_id"]]["story"]
        ledger.append(
            {
                "kind": row["kind"],
                "quote": row["quote"],
                "author": row["author"],
                "thread_id": row["thread_id"],
                "title": str(story.get("title") or "").strip(),
                "url": f"https://news.ycombinator.com/item?id={row['thread_id']}",
                "occurrences": row["occurrences"],
                "evidence": row["evidence"],
                "fit": row["fit"],
                "score": row["score"],
            }
        )
        if len(ledger) >= top:
            break
    return ledger
```