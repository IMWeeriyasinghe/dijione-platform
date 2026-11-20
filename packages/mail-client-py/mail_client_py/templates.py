"""One consistent, escaped email layout for every DijiOne application.

An application supplies *content* (its name, a heading, paragraphs, an optional list and an
optional call-to-action link); this module owns the *presentation*. Every piece of supplied
text is HTML-escaped here, so a name or label taken from data can never inject markup, and
links are restricted to ``https://`` (``http://localhost`` is accepted for local development).

Inline styles only: mail clients ignore stylesheets. Colours follow the DijiOne derived
palette (docs/platform/design-system.md). The plain-text rendering is produced from the same
content, for logs/tests and any future multipart transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from urllib.parse import urlparse

_BRAND_DEEP = "#8f2417"
_BRAND_ORANGE = "#db4d18"
_TEXT = "#24140f"
_TEXT_SECONDARY = "#76584c"
_BORDER = "#eadbd3"
_BACKGROUND = "#f8f5f2"
_SURFACE_WARM = "#fff8ef"


class InvalidTemplateContentError(ValueError):
    """Content that cannot be rendered safely (for example, an unsafe link)."""


@dataclass(frozen=True)
class EmailItem:
    label: str
    detail: str = ""


@dataclass(frozen=True)
class EmailContent:
    application_name: str
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    items: list[EmailItem] = field(default_factory=list)
    action_label: str | None = None
    action_url: str | None = None
    footer_note: str | None = None


@dataclass(frozen=True)
class RenderedEmail:
    html: str
    text: str


def _safe_url(url: str) -> str:
    parsed = urlparse(url)
    local = parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1")
    if not (parsed.scheme == "https" or local) or not parsed.netloc:
        raise InvalidTemplateContentError("action_url must be an https:// link")
    return url


def render_email(content: EmailContent) -> RenderedEmail:
    if not content.application_name.strip() or not content.heading.strip():
        raise InvalidTemplateContentError("application_name and heading are required")
    url = _safe_url(content.action_url) if content.action_url else None
    app = escape(content.application_name)
    footer = content.footer_note or (
        f"This is an automated message from {content.application_name}. Please do not reply to this email."
    )

    table = '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"'
    card_style = (
        f"max-width:600px;background:#ffffff;border:1px solid {_BORDER};border-radius:12px;"
        "overflow:hidden;font-family:Segoe UI,Helvetica,Arial,sans-serif;"
    )
    header_style = (
        f"background:{_BRAND_DEEP};background-image:linear-gradient(90deg,{_BRAND_DEEP},{_BRAND_ORANGE});"
        "padding:18px 24px;color:#ffffff;font-size:18px;font-weight:600;"
    )
    parts: list[str] = [
        f'<!DOCTYPE html><html><body style="margin:0;padding:0;background:{_BACKGROUND};">',
        f'{table} style="background:{_BACKGROUND};padding:24px 12px;">',
        '<tr><td align="center">',
        f'{table} style="{card_style}">',
        f'<tr><td style="{header_style}">{app}</td></tr>',
        f'<tr><td style="padding:24px;color:{_TEXT};font-size:15px;line-height:1.55;">',
        f'<h1 style="margin:0 0 16px;font-size:20px;font-weight:600;color:{_TEXT};">{escape(content.heading)}</h1>',
    ]
    for paragraph in content.paragraphs:
        parts.append(f'<p style="margin:0 0 14px;">{escape(paragraph)}</p>')
    if content.items:
        parts.append(
            f'{table} style="margin:4px 0 18px;background:{_SURFACE_WARM};'
            f'border:1px solid {_BORDER};border-radius:8px;">'
        )
        for item in content.items:
            detail = (
                f'<span style="color:{_TEXT_SECONDARY};"> — {escape(item.detail)}</span>' if item.detail else ""
            )
            parts.append(
                f'<tr><td style="padding:10px 14px;border-bottom:1px solid {_BORDER};font-size:14px;">'
                f"<strong>{escape(item.label)}</strong>{detail}</td></tr>"
            )
        parts.append("</table>")
    if url and content.action_label:
        parts.append(
            f'<p style="margin:8px 0 4px;"><a href="{escape(url, quote=True)}" '
            f'style="display:inline-block;background:{_BRAND_ORANGE};color:#ffffff;text-decoration:none;'
            f'padding:10px 18px;border-radius:8px;font-weight:600;font-size:14px;">{escape(content.action_label)}</a></p>'
        )
    parts.append("</td></tr>")
    parts.append(
        f'<tr><td style="padding:14px 24px;border-top:1px solid {_BORDER};color:{_TEXT_SECONDARY};font-size:12px;">'
        f"{escape(footer)}</td></tr>"
    )
    parts.append("</table></td></tr></table></body></html>")

    text_lines = [content.application_name, "", content.heading, ""]
    text_lines += [p for paragraph in content.paragraphs for p in (paragraph, "")]
    for item in content.items:
        text_lines.append(f"- {item.label}" + (f" — {item.detail}" if item.detail else ""))
    if content.items:
        text_lines.append("")
    if url and content.action_label:
        text_lines += [f"{content.action_label}: {url}", ""]
    text_lines.append(footer)
    return RenderedEmail(html="".join(parts), text="\n".join(text_lines))
