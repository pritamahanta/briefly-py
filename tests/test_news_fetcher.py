import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.models import Article
from app.services.news_fetcher import (
    clean_text,
    fetch_all_news,
    fetch_hacker_news,
    normalize_hn_story,
    normalize_rss_entry,
)

HN = "https://hn.test/v0"


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, routes):
        self.routes = routes

    async def get(self, url, timeout=None):
        result = self.routes[url]
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)


def hn_story(title):
    return {
        "type": "story",
        "title": title,
        "url": f"https://example.com/{title.lower()}",
        "score": 1,
    }


def test_clean_text_strips_tags_unescapes_and_truncates():
    assert clean_text("<p>Hello &amp; <b>world</b></p>   extra\n\nspace") == "Hello & world extra space"
    assert clean_text("&lt;b&gt;x") == "<b>x"
    assert len(clean_text("a" * 500)) == 300


def test_rss_entry_is_normalized():
    entry = {
        "title": "  Big News  ",
        "link": "https://example.com/story?utm_source=rss#top",
        "summary": "<p>Some <b>summary</b> text.</p>",
        "published_parsed": (2026, 11, 19, 5, 30, 0, 3, 323, 0),
    }
    article = normalize_rss_entry(entry, "TechCrunch")
    assert article.title == "Big News"
    assert article.link == "https://example.com/story"
    assert article.description == "Some summary text."
    assert article.source == "TechCrunch"
    assert article.published_at == datetime(2026, 11, 19, 5, 30, tzinfo=timezone.utc)
    assert article.hn_score == 0


def test_rss_entry_with_bad_or_missing_link_is_skipped():
    assert normalize_rss_entry({"title": "x", "link": "javascript:alert(1)"}, "S") is None
    assert normalize_rss_entry({"title": "x"}, "S") is None


def test_rss_entry_uses_guid_and_untitled_fallbacks():
    article = normalize_rss_entry({"id": "https://example.com/p/1", "summary": ""}, "S")
    assert article.title == "Untitled"
    assert article.link == "https://example.com/p/1"
    assert article.published_at is None


def test_hn_story_is_normalized():
    story = {
        "type": "story",
        "title": "Show: thing",
        "url": "https://example.com/x?utm_medium=y",
        "score": 250,
        "descendants": 40,
        "time": 1763530200,
    }
    article = normalize_hn_story(story)
    assert article.source == "Hacker News"
    assert article.link == "https://example.com/x"
    assert article.hn_score == 250
    assert article.description == "250 points · 40 comments on Hacker News"
    assert article.published_at.tzinfo is not None


def test_hn_story_without_external_url_is_skipped():
    assert normalize_hn_story({"type": "story", "title": "Ask HN: why?", "text": "hi"}) is None


@pytest.mark.parametrize(
    "story",
    [
        {"type": "story", "deleted": True, "url": "https://example.com/"},
        {"type": "story", "dead": True, "url": "https://example.com/"},
        {"type": "job", "url": "https://example.com/"},
    ],
)
def test_hn_deleted_dead_and_non_story_items_are_skipped(story):
    assert normalize_hn_story(story) is None


def test_hacker_news_skips_failed_stories():
    client = FakeClient(
        {
            f"{HN}/topstories.json": [1, 2, 3],
            f"{HN}/item/1.json": hn_story("One"),
            f"{HN}/item/2.json": httpx.ConnectError("boom"),
            f"{HN}/item/3.json": hn_story("Three"),
        }
    )
    articles = asyncio.run(fetch_hacker_news(client, base_url=HN))
    assert [a.title for a in articles] == ["One", "Three"]


def test_hacker_news_raises_when_all_stories_fail():
    client = FakeClient(
        {
            f"{HN}/topstories.json": [1, 2],
            f"{HN}/item/1.json": httpx.ConnectError("boom"),
            f"{HN}/item/2.json": httpx.ConnectError("boom"),
        }
    )
    with pytest.raises(RuntimeError):
        asyncio.run(fetch_hacker_news(client, base_url=HN))


async def _failing():
    raise RuntimeError("down")


async def _working():
    return [Article(title="T", link="https://example.com/", source="Fake")]


def test_fetch_all_news_survives_one_failing_source():
    articles = asyncio.run(fetch_all_news([("RSS", _failing), ("HN", _working)]))
    assert len(articles) == 1


def test_fetch_all_news_raises_when_all_sources_fail():
    with pytest.raises(RuntimeError):
        asyncio.run(fetch_all_news([("RSS", _failing), ("HN", _failing)]))