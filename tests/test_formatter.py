from datetime import datetime, timezone

import pytest

from app.models import Article
from app.services.formatter import format_email

NOW = datetime(2026, 11, 19, 5, 0, tzinfo=timezone.utc)


def make_article(**overrides):
    values = {
        "title": "Title",
        "link": "https://example.com/a",
        "source": "Source",
        "summary": "Summary.",
    }
    values.update(overrides)
    return Article(**values)


@pytest.mark.parametrize(
    "now, expected_date",
    [
        (datetime(2026, 11, 19, 5, 0, tzinfo=timezone.utc), "Thursday, 19 November 2026"),
        (datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc), "Thursday, 19 November 2026"),
        (datetime(2026, 11, 5, 6, 0, tzinfo=timezone.utc), "Thursday, 5 November 2026"),
    ],
)
def test_subject_uses_the_india_date_without_zero_padding(now, expected_date):
    assert format_email([], now).subject == f"Briefly — {expected_date}"


def test_story_count_uses_singular_and_plural():
    one = format_email([make_article()], NOW)
    two = format_email([make_article(), make_article(link="https://example.com/b")], NOW)
    assert "1 story selected." in one.html and "1 story selected." in one.text
    assert "2 stories selected." in two.html and "2 stories selected." in two.text


def test_html_escapes_title_source_summary_and_link():
    article = make_article(
        title='<script>alert(1)</script> & "q"',
        source="<b>Src</b>",
        summary="<img src=x onerror=alert(1)>",
        link='https://example.com/a?x="onmouseover="y',
    )
    html = format_email([article], NOW).html

    assert "<script>" not in html
    assert "<img" not in html
    assert "<b>Src</b>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;q&quot;" in html
    assert "&quot;onmouseover=&quot;" in html


@pytest.mark.parametrize("bad_link", ["javascript:alert(1)", "ftp://example.com/x", "https:///nohost"])
def test_rejects_links_that_are_not_http_or_https(bad_link):
    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        format_email([make_article(link=bad_link)], NOW)


def test_empty_selection_renders_no_new_stories():
    email = format_email([], NOW)
    assert "No new stories today." in email.html
    assert "No new stories today." in email.text
    assert "0 stories selected." in email.text


def test_plain_text_lists_each_story_with_source_summary_and_link():
    text = format_email([make_article()], NOW).text
    assert "1. Title" in text
    assert "Source: Source" in text
    assert "Summary." in text
    assert "Read: https://example.com/a" in text