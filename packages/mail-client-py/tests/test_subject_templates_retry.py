import pytest

from mail_client_py import (
    EmailContent,
    EmailItem,
    InvalidSubjectError,
    InvalidTemplateContentError,
    MailOutcome,
    backoff_seconds,
    format_subject,
    is_retryable,
    render_email,
)

# --- subject convention ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("app", "purpose", "expected"),
    [
        ("DijiOne", "Access Granted", "[DijiOne] | Access Granted"),
        ("DijiOne", "Application Access Updated", "[DijiOne] | Application Access Updated"),
        ("Example App", "Weekly Summary", "[Example App] | Weekly Summary"),
        ("Sample Tracker", "Status Exception", "[Sample Tracker] | Status Exception"),
        ("DijiTalentFlow", "Candidate Review Required", "[DijiTalentFlow] | Candidate Review Required"),
        ("DIJI Birthday", "Cake Order Confirmation", "[DIJI Birthday] | Cake Order Confirmation"),
    ],
)
def test_subject_convention_examples(app, purpose, expected):
    assert format_subject(app, purpose) == expected


def test_subject_collapses_whitespace_and_strips():
    assert format_subject("  DijiOne ", "  Access\tGranted  ") == "[DijiOne] | Access Granted"


@pytest.mark.parametrize("bad", ["Access\nGranted", "Access\r\nBcc: x@y.z"])
def test_subject_rejects_header_injection(bad):
    with pytest.raises(InvalidSubjectError):
        format_subject("DijiOne", bad)


@pytest.mark.parametrize("app", ["", "   ", "Diji[One]", "Diji|One"])
def test_subject_rejects_bad_application_name(app):
    with pytest.raises(InvalidSubjectError):
        format_subject(app, "Access Granted")


def test_subject_requires_purpose():
    with pytest.raises(InvalidSubjectError):
        format_subject("DijiOne", " ")


def test_subject_is_bounded():
    subject = format_subject("DijiOne", "x" * 500)
    assert len(subject) <= 200 and subject.startswith("[DijiOne] | ")


# --- templates ---------------------------------------------------------------------------


def _content(**overrides):
    base = dict(
        application_name="DijiOne",
        heading="Your access has changed",
        paragraphs=["Hello,", "Your access was updated."],
        items=[EmailItem("Example App", "Access granted")],
        action_label="Open DijiOne",
        action_url="https://dijione.example.com/",
    )
    base.update(overrides)
    return EmailContent(**base)


def test_render_contains_content_in_html_and_text():
    rendered = render_email(_content())
    for needle in ("DijiOne", "Your access has changed", "Example App", "Access granted", "https://dijione.example.com/"):
        assert needle in rendered.html
        assert needle in rendered.text
    assert rendered.html.startswith("<!DOCTYPE html>")


def test_render_escapes_every_supplied_value():
    evil = '<script>alert("x")</script>'
    rendered = render_email(
        _content(heading=evil, paragraphs=[evil], items=[EmailItem(evil, evil)], action_label=evil, footer_note=evil)
    )
    assert "<script>" not in rendered.html
    assert "&lt;script&gt;" in rendered.html


@pytest.mark.parametrize("url", ["javascript:alert(1)", "http://evil.example.com", "ftp://x", "https://"])
def test_render_rejects_unsafe_links(url):
    with pytest.raises(InvalidTemplateContentError):
        render_email(_content(action_url=url))


def test_render_allows_localhost_http_for_local_dev():
    assert "http://localhost:3000/" in render_email(_content(action_url="http://localhost:3000/")).html


def test_render_without_action_or_items():
    rendered = render_email(_content(items=[], action_label=None, action_url=None))
    assert "<a " not in rendered.html


def test_render_requires_heading():
    with pytest.raises(InvalidTemplateContentError):
        render_email(_content(heading=" "))


# --- retry -----------------------------------------------------------------------------


def test_backoff_is_exponential_and_capped():
    assert [backoff_seconds(n, base=60, cap=600) for n in range(0, 7)] == [0, 60, 120, 240, 480, 600, 600]


def test_only_transport_failures_are_retryable():
    assert is_retryable(MailOutcome.FAILED)
    for outcome in (MailOutcome.SUBMITTED, MailOutcome.SIMULATED, MailOutcome.BLOCKED, MailOutcome.DISABLED):
        assert not is_retryable(outcome)
