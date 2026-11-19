import psycopg

from app.models import Article
from app.utils.url import hash_link

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    link TEXT NOT NULL UNIQUE,
    link_hash CHAR(64) NOT NULL UNIQUE,
    source TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    score NUMERIC(6,2)
)
"""

SELECT_SENT_SQL = "SELECT link_hash FROM articles WHERE link_hash = ANY(%s::text[])"

INSERT_SQL = """
INSERT INTO articles (title, link, link_hash, source, published_at, score)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (link_hash) DO NOTHING
"""


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def _connect(self) -> psycopg.AsyncConnection:
        return await psycopg.AsyncConnection.connect(
            self.database_url,
            connect_timeout=5,
            prepare_threshold=None,
        )

    async def init(self) -> None:
        async with await self._connect() as conn:
            await conn.execute(CREATE_TABLE_SQL)

    async def filter_unseen(self, articles: list[Article]) -> list[Article]:
        if not articles:
            return []

        hashes = [hash_link(article.link) for article in articles]
        async with await self._connect() as conn:
            cursor = await conn.execute(SELECT_SENT_SQL, (hashes,))
            sent_hashes = {row[0] for row in await cursor.fetchall()}

        return [article for article in articles if hash_link(article.link) not in sent_hashes]

    async def mark_as_sent(self, articles: list[Article]) -> None:
        if not articles:
            return

        rows = [
            (
                article.title,
                article.link,
                hash_link(article.link),
                article.source,
                article.published_at,
                article.score,
            )
            for article in articles
        ]
        async with await self._connect() as conn:
            async with conn.cursor() as cursor:
                await cursor.executemany(INSERT_SQL, rows)