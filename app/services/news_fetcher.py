import asyncio
import html
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from functools import partial
from typing import Any

import feedparser
import httpx

from app.models import Article
from app.utils.url import normalize_url

logger = logging.getLogger(__name__)

USER_AGENT = "Briefly/1.0"
DESCRIPTION_LIMIT = 300
HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"
HN_STORY_LIMIT = 60
HN_CONCURRENCY = 20

RSS_SOURCES = [
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
]

NewsSource = tuple[str, Callable[[], Awaitable[list[Article]]]]

BLOCK_TAGS = re.compile(r"</?(?:p|div|br|li|ul|ol|blockquote|h[1-6])\b[^>]*>", re.IGNORECASE)
ANY_TAG = re.compile(r"<[^>]*>")


def clean_text(text: str, limit: int = DESCRIPTION_LIMIT) -> str:
    text = BLOCK_TAGS.sub(" ", text)
    text = ANY_TAG.sub("", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _to_datetime(parsed: Any) -> datetime | None:
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def normalize_rss_entry(entry: Any, source: str) -> Article | None:
    raw_link = (entry.get("link") or entry.get("id") or "").strip()
    try:
        link = normalize_url(raw_link)
    except ValueError:
        return None

    return Article(
        title=(entry.get("title") or "").strip() or "Untitled",
        link=link,
        description=clean_text(entry.get("summary") or ""),
        source=source,
        published_at=_to_datetime(entry.get("published_parsed") or entry.get("updated_parsed")),
    )


def normalize_hn_story(story: Any) -> Article | None:
    if not isinstance(story, dict) or story.get("type") != "story":
        return None
    if story.get("deleted") or story.get("dead"):
        return None

    url = story.get("url")
    if not isinstance(url, str):
        return None
    try:
        link = normalize_url(url)
    except ValueError:
        return None

    score = _as_int(story.get("score"))
    comments = _as_int(story.get("descendants"))
    description = clean_text(story.get("text") or "") or (
        f"{score} points · {comments} comments on Hacker News"
    )

    posted = story.get("time")
    published_at = (
        datetime.fromtimestamp(posted, tz=timezone.utc)
        if isinstance(posted, int) and not isinstance(posted, bool)
        else None
    )

    return Article(
        title=str(story.get("title") or "").strip() or "Untitled",
        link=link,
        description=description,
        source="Hacker News",
        published_at=published_at,
        hn_score=score,
    )


async def _gather_articles(
    tasks: Sequence[Awaitable[list[Article]]],
    names: Sequence[str],
    label: str,
) -> list[Article]:
    results = await asyncio.gather(*tasks, return_exceptions=True)

    articles: list[Article] = []
    failures = 0
    for name, result in zip(names, results):
        if isinstance(result, BaseException):
            failures += 1
            logger.warning("Failed to fetch %s (%s): %r", label, name, result)
        else:
            articles.extend(result)

    if names and failures == len(names):
        raise RuntimeError(f"All {label} failed. Check the warnings above.")

    return articles


async def _fetch_feed(client: httpx.AsyncClient, name: str, url: str) -> list[Article]:
    response = await client.get(url, timeout=10.0)
    response.raise_for_status()

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError("feed could not be parsed")

    articles = [normalize_rss_entry(entry, name) for entry in parsed.entries]
    return [article for article in articles if article is not None]


async def fetch_rss_feeds(
    client: httpx.AsyncClient,
    sources: Sequence[tuple[str, str]] = RSS_SOURCES,
) -> list[Article]:
    return await _gather_articles(
        [_fetch_feed(client, name, url) for name, url in sources],
        [name for name, _ in sources],
        "RSS feeds",
    )


async def fetch_hacker_news(
    client: httpx.AsyncClient,
    base_url: str = HN_BASE_URL,
) -> list[Article]:
    response = await client.get(f"{base_url}/topstories.json", timeout=8.0)
    response.raise_for_status()

    ids = response.json()
    if not isinstance(ids, list) or not all(isinstance(i, int) and i > 0 for i in ids):
        raise ValueError("Hacker News returned an invalid story list")
    ids = ids[:HN_STORY_LIMIT]

    semaphore = asyncio.Semaphore(HN_CONCURRENCY)

    async def fetch_story(story_id: int) -> list[Article]:
        async with semaphore:
            item = await client.get(f"{base_url}/item/{story_id}.json", timeout=5.0)
            item.raise_for_status()
            article = normalize_hn_story(item.json())
            return [article] if article else []

    return await _gather_articles(
        [fetch_story(story_id) for story_id in ids],
        [str(story_id) for story_id in ids],
        "Hacker News stories",
    )


async def _run_sources(sources: Sequence[NewsSource]) -> list[Article]:
    return await _gather_articles(
        [fetch() for _, fetch in sources],
        [name for name, _ in sources],
        "news sources",
    )


async def fetch_all_news(sources: Sequence[NewsSource] | None = None) -> list[Article]:
    if sources is not None:
        return await _run_sources(sources)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True
    ) as client:
        return await _run_sources(
            [
                ("RSS", partial(fetch_rss_feeds, client)),
                ("Hacker News", partial(fetch_hacker_news, client)),
            ]
        )