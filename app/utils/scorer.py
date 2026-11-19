import re
from datetime import datetime, timezone

from app.models import Article

KEYWORD_WEIGHTS = [
    (10, r"\b(ai|artificial intelligence|llm|gpt|gemini|openai|anthropic|claude|machine learning|deep learning)\b"),
    (8, r"\b(developer tools|open source|github|api|sdk|framework|release|launch)\b"),
    (7, r"\b(security|breach|vulnerability|privacy|regulation|law)\b"),
    (5, r"\b(startup|funding|series a|series b|ipo|acquisition|unicorn|raised)\b"),
    (4, r"\b(apple|google|microsoft|meta|amazon|nvidia|tesla)\b"),
    (2, r"\b(cloud|saas|infrastructure|kubernetes|docker)\b"),
]

COMPILED_WEIGHTS = [(weight, re.compile(pattern, re.IGNORECASE)) for weight, pattern in KEYWORD_WEIGHTS]

HN_POINTS_DIVISOR = 100
HN_POINTS_CAP = 5
RECENCY_WINDOW_HOURS = 12
RECENCY_MAX_BONUS = 3


def score_article(article: Article, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    text = f"{article.title} {article.description}"

    score = sum(weight for weight, pattern in COMPILED_WEIGHTS if pattern.search(text))
    score += min(max(article.hn_score, 0) / HN_POINTS_DIVISOR, HN_POINTS_CAP)

    if article.published_at:
        age_hours = (now - article.published_at).total_seconds() / 3600
        bonus = (1 - age_hours / RECENCY_WINDOW_HOURS) * RECENCY_MAX_BONUS
        score += min(max(bonus, 0), RECENCY_MAX_BONUS)

    return round(score, 2)


def rank_articles(articles: list[Article], now: datetime | None = None) -> list[Article]:
    now = now or datetime.now(timezone.utc)
    scored = [article.model_copy(update={"score": score_article(article, now)}) for article in articles]
    return sorted(scored, key=lambda article: article.score, reverse=True)