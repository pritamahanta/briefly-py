import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.config import Settings
from app.db import Database
from app.models import Article
from app.services.ai_service import summarize_and_filter
from app.services.email_service import send_email, validate_email_settings
from app.services.formatter import Email, format_email
from app.services.news_fetcher import fetch_all_news
from app.utils.article_filter import filter_articles
from app.utils.scorer import rank_articles

logger = logging.getLogger(__name__)


class ArticleStore(Protocol):
    async def init(self) -> None: ...

    async def filter_unseen(self, articles: list[Article]) -> list[Article]: ...

    async def mark_as_sent(self, articles: list[Article]) -> None: ...


@dataclass
class Services:
    db: ArticleStore
    fetch_news: Callable[[], Awaitable[list[Article]]]
    summarize: Callable[[list[Article], Settings], Awaitable[list[Article]]]
    send: Callable[[Email, Settings], Awaitable[str]]


@dataclass
class DigestResult:
    articles: list[Article] = field(default_factory=list)
    email: Email | None = None
    email_id: str | None = None


def default_services(settings: Settings) -> Services:
    return Services(
        db=Database(settings.database_url),
        fetch_news=fetch_all_news,
        summarize=summarize_and_filter,
        send=send_email,
    )


async def run_agent(
    settings: Settings,
    should_send: bool = False,
    services: Services | None = None,
) -> DigestResult:
    services = services or default_services(settings)
    if should_send:
        validate_email_settings(settings)

    logger.info("Mode: %s.", "send" if should_send else "preview")
    logger.info("Maximum article age: %s hours.", settings.max_article_age_hours)
    logger.info("Maximum stories per digest: %s.", settings.top_articles_count)

    await services.db.init()
    logger.info("Database initialized.")

    articles = await services.fetch_news()
    logger.info("Fetched %d articles in total.", len(articles))

    now = datetime.now(timezone.utc)
    filtered = filter_articles(articles, settings.max_article_age_hours, now)
    logger.info("Retained %d articles after age filtering and deduplication.", len(filtered))

    unseen = await services.db.filter_unseen(filtered)
    logger.info("Found %d articles not previously sent.", len(unseen))
    ranked = rank_articles(unseen, now)

    if not ranked:
        logger.info("No new articles available after filtering.")
        return DigestResult()

    logger.info("Selecting and summarizing with Gemini (%s).", settings.gemini_model)
    summarized = await services.summarize(ranked, settings)
    logger.info("AI selected %d stories.", len(summarized))

    if not summarized:
        logger.info("No suitable stories selected.")
        return DigestResult()

    email = format_email(summarized, now)
    if not should_send:
        return DigestResult(articles=summarized, email=email)

    email_id = await services.send(email, settings)
    logger.info("Resend accepted email: %s.", email_id)

    try:
        await services.db.mark_as_sent(summarized)
    except Exception as error:
        raise RuntimeError(
            f"Email {email_id} was accepted, but recording sent articles failed: {error}. "
            "Check Resend before retrying."
        ) from error
    logger.info("Recorded %d articles as sent.", len(summarized))

    return DigestResult(articles=summarized, email=email, email_id=email_id)