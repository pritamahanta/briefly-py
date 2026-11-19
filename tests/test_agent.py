import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.agent import Services, run_agent
from app.config import Settings
from app.models import Article


def make_settings(**overrides):
    values = {
        "database_url": "postgresql://user:pass@localhost/db",
        "ai_api_key": "key",
        "resend_api_key": "re_test",
        "email_from": "briefly@example.com",
        "email_to": "me@example.com",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def article(title, link, hours_old=1):
    return Article(
        title=title,
        link=link,
        description="",
        source="Source",
        published_at=datetime.now(timezone.utc) - timedelta(hours=hours_old),
    )


class FakeDatabase:
    def __init__(self, sent_links=(), fail_mark=False):
        self.sent_links = set(sent_links)
        self.fail_mark = fail_mark
        self.init_calls = 0
        self.marked = []

    async def init(self):
        self.init_calls += 1

    async def filter_unseen(self, articles):
        return [a for a in articles if a.link not in self.sent_links]

    async def mark_as_sent(self, articles):
        if self.fail_mark:
            raise RuntimeError("db down")
        self.marked.extend(articles)


class Recorder:
    def __init__(self, articles, select=2, send_error=None, fetch_error=None):
        self.articles = articles
        self.select = select
        self.send_error = send_error
        self.fetch_error = fetch_error
        self.summarize_input = None
        self.sent_emails = []

    async def fetch(self):
        if self.fetch_error:
            raise self.fetch_error
        return self.articles

    async def summarize(self, ranked, settings):
        self.summarize_input = ranked
        return [a.model_copy(update={"summary": "Summary."}) for a in ranked[: self.select]]

    async def send(self, email, settings):
        if self.send_error:
            raise self.send_error
        self.sent_emails.append(email)
        return "email-1"


def build(db, recorder):
    return Services(db=db, fetch_news=recorder.fetch, summarize=recorder.summarize, send=recorder.send)


def run(settings, db, recorder, should_send=False):
    return asyncio.run(run_agent(settings, should_send=should_send, services=build(db, recorder)))


def three_articles():
    return [article("Story A", "https://x.com/a"), article("Story B", "https://x.com/b"), article("Story C", "https://x.com/c")]


def test_preview_builds_the_digest_but_sends_and_records_nothing():
    db, recorder = FakeDatabase(), Recorder(three_articles())

    result = run(make_settings(), db, recorder)

    assert len(result.articles) == 2
    assert result.email is not None and result.email_id is None
    assert recorder.sent_emails == []
    assert db.marked == []
    assert db.init_calls == 1


def test_filters_stale_duplicate_and_already_sent_articles_then_ranks_the_rest():
    fresh_ai = article("New AI model released", "https://x.com/ai", hours_old=1)
    plain = article("Local news", "https://x.com/plain", hours_old=2)
    stale = article("AI thing", "https://x.com/stale", hours_old=30)
    duplicate = article("Local news again", "https://x.com/plain", hours_old=3)
    already_sent = article("Old news", "https://x.com/sent", hours_old=1)
    db = FakeDatabase(sent_links={"https://x.com/sent"})
    recorder = Recorder([plain, stale, duplicate, already_sent, fresh_ai])

    run(make_settings(), db, recorder)

    assert [a.link for a in recorder.summarize_input] == ["https://x.com/ai", "https://x.com/plain"]


def test_send_mode_sends_the_email_then_records_the_selected_articles():
    db, recorder = FakeDatabase(), Recorder(three_articles())

    result = run(make_settings(), db, recorder, should_send=True)

    assert len(recorder.sent_emails) == 1
    assert result.email_id == "email-1"
    assert [a.link for a in db.marked] == [a.link for a in result.articles]
    assert all(a.summary == "Summary." for a in db.marked)


def test_nothing_new_skips_the_ai_step_and_the_email():
    articles = three_articles()
    db = FakeDatabase(sent_links={a.link for a in articles})
    recorder = Recorder(articles)

    result = run(make_settings(), db, recorder, should_send=True)

    assert result.articles == [] and result.email is None
    assert recorder.summarize_input is None
    assert recorder.sent_emails == []


def test_ai_selecting_nothing_sends_and_records_nothing():
    db, recorder = FakeDatabase(), Recorder(three_articles(), select=0)

    result = run(make_settings(), db, recorder, should_send=True)

    assert result.articles == []
    assert recorder.sent_emails == []
    assert db.marked == []


def test_send_mode_validates_email_settings_before_fetching_anything():
    db, recorder = FakeDatabase(), Recorder([], fetch_error=AssertionError("must not fetch"))

    with pytest.raises(ValueError, match="Missing email settings"):
        run(make_settings(resend_api_key=""), db, recorder, should_send=True)
    assert db.init_calls == 0


def test_failed_send_records_nothing():
    db = FakeDatabase()
    recorder = Recorder(three_articles(), send_error=RuntimeError("resend down"))

    with pytest.raises(RuntimeError, match="resend down"):
        run(make_settings(), db, recorder, should_send=True)
    assert db.marked == []


def test_failed_recording_after_an_accepted_email_reports_the_email_id():
    db, recorder = FakeDatabase(fail_mark=True), Recorder(three_articles())

    with pytest.raises(RuntimeError, match="email-1 was accepted.*Check Resend before retrying"):
        run(make_settings(), db, recorder, should_send=True)
    assert len(recorder.sent_emails) == 1


def test_fetch_failure_stops_the_run_before_anything_is_sent():
    db = FakeDatabase()
    recorder = Recorder([], fetch_error=RuntimeError("All news sources failed."))

    with pytest.raises(RuntimeError, match="All news sources failed"):
        run(make_settings(), db, recorder, should_send=True)
    assert recorder.sent_emails == [] and db.marked == []