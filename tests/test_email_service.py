import asyncio

import pytest
import resend

from app.config import Settings
from app.services import email_service
from app.services.email_service import make_resend_send, send_email, validate_email_settings
from app.services.formatter import Email


def make_settings(**overrides):
    values = {
        "database_url": "postgresql://user:pass@localhost/db",
        "resend_api_key": "re_test",
        "email_from": "from@example.com",
        "email_to": "to@example.com",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_email(**overrides):
    values = {"subject": "Subject", "html": "<p>Hi</p>", "text": "Hi"}
    values.update(overrides)
    return Email(**values)


class FakeSend:
    def __init__(self, response=None, error=None):
        self.response = {"id": "email-1"} if response is None else response
        self.error = error
        self.calls = []

    def __call__(self, params):
        self.calls.append(params)
        if self.error:
            raise self.error
        return self.response


def run(email, settings, send):
    return asyncio.run(send_email(email, settings, send))


def test_valid_settings_pass():
    validate_email_settings(make_settings())


def test_missing_settings_are_all_named():
    settings = make_settings(resend_api_key="", email_to="")
    with pytest.raises(ValueError, match="RESEND_API_KEY, EMAIL_TO"):
        validate_email_settings(settings)


@pytest.mark.parametrize(
    "field, value",
    [
        ("email_from", "not-an-email"),
        ("email_from", "Name <from@example.com>"),
        ("email_to", "a@example.com, b@example.com"),
        ("email_to", "a@example.com;b@example.com"),
        ("email_to", "a@example.com b@example.com"),
    ],
)
def test_addresses_must_be_a_single_plain_email(field, value):
    with pytest.raises(ValueError, match=f"{field.upper()} must be a single email address"):
        validate_email_settings(make_settings(**{field: value}))


def test_send_passes_the_expected_payload_and_returns_the_id():
    send = FakeSend()
    email = make_email()

    assert run(email, make_settings(), send) == "email-1"
    assert send.calls == [
        {
            "from": "from@example.com",
            "to": ["to@example.com"],
            "subject": "Subject",
            "html": "<p>Hi</p>",
            "text": "Hi",
        }
    ]


def test_invalid_settings_stop_before_anything_is_sent():
    send = FakeSend()
    with pytest.raises(ValueError):
        run(make_email(), make_settings(email_to=""), send)
    assert send.calls == []


@pytest.mark.parametrize("field", ["subject", "html", "text"])
def test_blank_fields_are_rejected_before_sending(field):
    send = FakeSend()
    with pytest.raises(ValueError, match=f"Email {field} is required"):
        run(make_email(**{field: "   "}), make_settings(), send)
    assert send.calls == []


@pytest.mark.parametrize("subject", ["Line one\nLine two", "Line one\rLine two"])
def test_multiline_subjects_are_rejected(subject):
    send = FakeSend()
    with pytest.raises(ValueError, match="single line"):
        run(make_email(subject=subject), make_settings(), send)
    assert send.calls == []


def test_provider_errors_are_wrapped_with_the_cause():
    send = FakeSend(error=ConnectionError("boom"))
    with pytest.raises(RuntimeError, match="Resend email request failed: boom") as info:
        run(make_email(), make_settings(), send)
    assert isinstance(info.value.__cause__, ConnectionError)


@pytest.mark.parametrize(
    "response",
    [{"id": ""}, {"id": "   "}, {"id": 123}, {"id": None}, {}, "email-1", ["email-1"]],
)
def test_send_requires_an_accepted_email_id(response):
    with pytest.raises(RuntimeError, match="did not return an accepted email ID"):
        run(make_email(), make_settings(), FakeSend(response=response))


def test_default_sender_sets_the_api_key_and_calls_resend(monkeypatch):
    seen = {}

    def fake_send(params):
        seen["key"] = resend.api_key
        seen["params"] = params
        return {"id": "email-2"}

    monkeypatch.setattr(resend.Emails, "send", fake_send)
    monkeypatch.setattr(resend, "api_key", None)

    result = make_resend_send("re_live")({"subject": "S"})

    assert result == {"id": "email-2"}
    assert seen == {"key": "re_live", "params": {"subject": "S"}}


def test_send_email_builds_the_resend_sender_from_settings(monkeypatch):
    keys = []
    send = FakeSend()

    def fake_make(api_key):
        keys.append(api_key)
        return send

    monkeypatch.setattr(email_service, "make_resend_send", fake_make)

    assert asyncio.run(send_email(make_email(), make_settings())) == "email-1"
    assert keys == ["re_test"]
