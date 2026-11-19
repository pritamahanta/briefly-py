from datetime import datetime, timedelta, timezone

from app.models import Article
from app.utils.scorer import rank_articles, score_article

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def art(title="", description="", hn_score=0, hours_old=None):
    published = NOW - timedelta(hours=hours_old) if hours_old is not None else None
    return Article(
        title=title,
        link="https://x.com/a",
        description=description,
        source="s",
        hn_score=hn_score,
        published_at=published,
    )


def test_a_keyword_group_adds_its_weight_only_once():
    assert score_article(art(title="AI AI AI llm"), NOW) == 10.0


def test_different_groups_stack():
    assert score_article(art(title="OpenAI Google API"), NOW) == 22.0


def test_keywords_match_whole_words_only():
    assert score_article(art(title="He said it was fair"), NOW) == 0.0


def test_hn_points_are_divided_by_100_and_capped_at_5():
    assert score_article(art(hn_score=250), NOW) == 2.5
    assert score_article(art(hn_score=10000), NOW) == 5.0


def test_recency_bonus_decreases_linearly_to_zero_at_12_hours():
    assert score_article(art(hours_old=0), NOW) == 3.0
    assert score_article(art(hours_old=6), NOW) == 1.5
    assert score_article(art(hours_old=12), NOW) == 0.0
    assert score_article(art(hours_old=20), NOW) == 0.0


def test_undated_article_gets_no_recency_bonus():
    assert score_article(art(hours_old=None), NOW) == 0.0


def test_rank_sorts_best_first_ties_keep_input_order_and_input_is_untouched():
    first = art(title="first")
    top = art(title="AI news")
    second = art(title="second")

    ranked = rank_articles([first, top, second], NOW)

    assert [a.title for a in ranked] == ["AI news", "first", "second"]
    assert ranked[0].score == 10.0
    assert first.score == 0.0