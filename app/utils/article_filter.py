from datetime import datetime, timezone

from app.models import Article


def filter_articles(
    articles: list[Article],
    max_age_hours: int,
    now: datetime | None = None,
) -> list[Article]:
    now = now or datetime.now(timezone.utc)
    seen_links: set[str] = set()
    kept: list[Article] = []

    for article in articles:
        if not article.link or article.link in seen_links:
            continue

        if article.published_at:
            age_hours = (now - article.published_at).total_seconds() / 3600
            if age_hours < 0 or age_hours > max_age_hours:
                continue

        seen_links.add(article.link)
        kept.append(article)

    return kept