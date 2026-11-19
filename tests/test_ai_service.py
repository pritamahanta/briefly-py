import asyncio
import json

import pytest

from app.config import Settings
from app.models import Article
from app.services.ai_service import summarize_and_filter


def make_settings(**overrides):
    values = {
        "database_url": "postgresql://user:pass@localhost/db",
        "ai_api_key": "test-key",
        "top_articles_count": 2,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_articles(count=3):
    return [
        Article(
            title=f"Story {i}",
            link=f"https://example.com/{i}",
            description=f"Description {i}",
            source="Source",
            score=float(count - i),
        )
        for i in range(count)
    ]


def fake_generate(raw):
    async def generate(prompt):
        return raw

    return generate


def run(articles, settings, raw):
    return asyncio.run(summarize_and_filter(articles, settings, fake_generate(raw)))


def test_returns_selected_articles_with_summaries_and_original_fields():
    articles = make_articles(3)
    raw = json.dumps({"selected": [{"index": 2, "summary": "  Two.  "}, {"index": 0, "summary": "Zero."}]})

    result = run(articles, make_settings(), raw)

    assert [a.title for a in result] == ["Story 2", "Story 0"]
    assert [a.summary for a in result] == ["Two.", "Zero."]
    assert result[0].link == "https://example.com/2"
    assert result[1].source == "Source"


def test_prompt_is_json_data_and_never_contains_links():
    captured = {}

    async def generate(prompt):
        captured["prompt"] = prompt
        return '{"selected": []}'

    asyncio.run(summarize_and_filter(make_articles(3), make_settings(), generate))

    data = json.loads(captured["prompt"])
    assert data["maxStories"] == 2
    assert [c["index"] for c in data["candidates"]] == [0, 1, 2]
    assert set(data["candidates"][0]) == {"index", "title", "description", "source", "score"}


def test_sends_at_most_30_candidates_and_caps_the_story_limit():
    captured = []

    async def generate(prompt):
        captured.append(json.loads(prompt))
        return '{"selected": []}'

    asyncio.run(summarize_and_filter(make_articles(40), make_settings(top_articles_count=8), generate))
    asyncio.run(summarize_and_filter(make_articles(3), make_settings(top_articles_count=8), generate))

    assert len(captured[0]["candidates"]) == 30
    assert captured[0]["maxStories"] == 8
    assert captured[1]["maxStories"] == 3


def test_empty_input_returns_empty_without_calling_the_model():
    async def generate(prompt):
        raise AssertionError("model must not be called")

    assert asyncio.run(summarize_and_filter([], make_settings(), generate)) == []


def test_missing_api_key_raises():
    with pytest.raises(ValueError, match="AI_API_KEY"):
        run(make_articles(), make_settings(ai_api_key=""), '{"selected": []}')


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{}",
        json.dumps({"selected": [{"index": 5, "summary": "Out of range."}]}),
        json.dumps({"selected": [{"index": -1, "summary": "Negative."}]}),
        json.dumps({"selected": [{"index": 0, "summary": "A."}, {"index": 0, "summary": "B."}]}),
        json.dumps({"selected": [{"index": 0, "summary": "   "}]}),
        json.dumps({"selected": [{"index": 0, "summary": "x" * 1201}]}),
        json.dumps({"selected": [{"index": i, "summary": "S."} for i in range(3)]}),
        json.dumps({"selected": [{"index": "a", "summary": "Bad index."}]}),
    ],
)
def test_invalid_model_output_is_rejected(raw):
    with pytest.raises(ValueError, match="invalid article selection"):
        run(make_articles(3), make_settings(), raw)


def test_selecting_nothing_is_allowed():
    assert run(make_articles(3), make_settings(), '{"selected": []}') == []


def test_input_articles_are_not_mutated():
    articles = make_articles(2)
    run(articles, make_settings(), json.dumps({"selected": [{"index": 0, "summary": "Done."}]}))
    assert articles[0].summary == ""