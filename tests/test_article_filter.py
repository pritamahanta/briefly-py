from datetime import datetime, timedelta, timezone

from app.models import Article
from app.utils.article_filter import filter_articles

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def make(link, hours_old=None):
    published = NOW - timedelta(hours=hours_old) if hours_old is not None else None
    return Article(title="t", link=link, source="s", published_at=published)


def test_drops_articles_older_than_max_age_and_keeps_the_boundary():
    articles = [
        make("https://x.com/a", 5),
        make("https://x.com/b", 25),
        make("https://x.com/c", 26),
    ]
    kept = filter_articles(articles, max_age_hours=25, now=NOW)
    assert [a.link for a in kept] == ["https://x.com/a", "https://x.com/b"]


def test_drops_future_dated_articles():
    kept = filter_articles([make("https://x.com/a", -1)], max_age_hours=25, now=NOW)
    assert kept == []


def test_keeps_undated_articles():
    kept = filter_articles([make("https://x.com/a")], max_age_hours=25, now=NOW)
    assert len(kept) == 1


def test_removes_duplicate_links_and_keeps_the_first():
    first = make("https://x.com/a", 1)
    second = make("https://x.com/a", 2)
    kept = filter_articles([first, second], max_age_hours=25, now=NOW)
    assert kept == [first]