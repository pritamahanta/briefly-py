import asyncio
import sys
import uuid
from datetime import datetime, timezone

import psycopg

from app.config import get_settings
from app.db import Database
from app.models import Article

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def check_database() -> None:
    settings = get_settings()
    db = Database(settings.database_url)

    prefix = f"https://briefly-db-check.invalid/{uuid.uuid4()}"
    articles = [
        Article(
            title="Database check: quotes ' stay as data",
            link=f"{prefix}/Story",
            source="Database check",
            published_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
            score=12.34,
        ),
        Article(
            title="Database check: undated article",
            link=f"{prefix}/story",
            source="Database check",
            published_at=None,
            score=0,
        ),
    ]
    links = [article.link for article in articles]

    await db.init()
    await db.init()

    try:
        assert await db.filter_unseen([]) == []
        await db.mark_as_sent([])

        assert await db.filter_unseen(articles) == articles
        await db.mark_as_sent([articles[0]])
        assert await db.filter_unseen(articles) == [articles[1]]

        await db.mark_as_sent(articles)
        await db.mark_as_sent(articles)
        assert await db.filter_unseen(articles) == []

        async with await psycopg.AsyncConnection.connect(
            settings.database_url, connect_timeout=5
        ) as conn:
            cursor = await conn.execute(
                "SELECT title, link, published_at, sent_at, score "
                "FROM articles WHERE link = ANY(%s::text[])",
                (links,),
            )
            rows = await cursor.fetchall()

        assert len(rows) == 2
        dated = next(row for row in rows if row[1] == links[0])
        undated = next(row for row in rows if row[1] == links[1])
        assert dated[0] == articles[0].title
        assert dated[2] == articles[0].published_at
        assert float(dated[4]) == 12.34
        assert undated[2] is None
        assert all(isinstance(row[3], datetime) for row in rows)
    finally:
        async with await psycopg.AsyncConnection.connect(
            settings.database_url, connect_timeout=5
        ) as conn:
            await conn.execute("DELETE FROM articles WHERE link = ANY(%s::text[])", (links,))
        print("Database check fixtures removed.")

    print(
        "Database checks passed: schema setup, sent-article filtering, exact URL matching, "
        "duplicate inserts, dates, scores, and parameterized values."
    )


if __name__ == "__main__":
    asyncio.run(check_database())