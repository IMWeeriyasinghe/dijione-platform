"""Renders the Supplier Portal invitation email — subject, HTML body, and a
plain-text fallback. Same table-based, inline-styled HTML convention as
supplier_email_template.py (order-release emails); kept as a separate
module since the two have no shared business logic, only a shared visual
language.

No environment-specific subject prefix: none of this app's other
outbound emails (the order-release notification included) use one, so
none is introduced here either — verified no such convention exists
before writing this.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from app.core.config import get_settings
from app.models.supplier_user import SupplierUser

_BRAND_ORANGE = "#c9431d"
_BRAND_ORANGE_DEEP = "#aa2f1d"
_BRAND_BG = "#f8f5f2"
_BRAND_TEXT = "#24140f"
_BRAND_TEXT_SECONDARY = "#76584c"
_BRAND_BORDER = "#eadbd3"

SUBJECT = "You're invited to the DIJI Birthday Supplier Portal"


@dataclass(frozen=True)
class SupplierInvitationEmailContent:
    subject: str
    html_body: str
    text_body: str


def _portal_home_url() -> str | None:
    base = get_settings().supplier_public_base_url.rstrip("/")
    return base or None


def render_supplier_invitation_email(
    user: SupplierUser, supplier_name: str
) -> SupplierInvitationEmailContent:
    portal_url = _portal_home_url()
    greeting_name = (user.full_name or user.email).strip()

    text_body = _render_text(
        greeting_name=greeting_name, supplier_name=supplier_name, email=user.email, portal_url=portal_url
    )
    html_body = _render_html(
        greeting_name=greeting_name, supplier_name=supplier_name, email=user.email, portal_url=portal_url
    )
    return SupplierInvitationEmailContent(subject=SUBJECT, html_body=html_body, text_body=text_body)


def _render_text(*, greeting_name: str, supplier_name: str, email: str, portal_url: str | None) -> str:
    lines = [
        f"Hello {greeting_name},",
        "",
        f"You've been invited to access the DIJI Birthday Supplier Portal for {supplier_name}.",
        "",
        "Through the Supplier Portal you can securely review and manage birthday orders "
        "assigned to your organisation.",
        "",
    ]
    if portal_url:
        lines.append(f"Access the Supplier Portal: {portal_url}")
        lines.append("")
    lines.append(f"Sign in using: {email}")
    lines.append("Use your Microsoft account to complete the sign-in process.")
    lines.append("")
    lines.append(
        "If you have not previously accessed the portal, Microsoft may guide you through the "
        "guest-account acceptance/sign-in process."
    )
    lines.append("")
    lines.append("Regards,")
    lines.append("Dijital Team")
    lines.append("DIJI Birthday")
    return "\n".join(lines)


def _render_html(*, greeting_name: str, supplier_name: str, email: str, portal_url: str | None) -> str:
    cta = ""
    if portal_url:
        cta = f"""
      <tr>
        <td align="center" style="padding:24px 0 8px 0;">
          <a href="{escape(portal_url)}"
             style="display:inline-block;background:{_BRAND_ORANGE};color:#ffffff;font-size:14px;
                    font-weight:600;text-decoration:none;padding:12px 28px;border-radius:8px;">
            Access Supplier Portal
          </a>
        </td>
      </tr>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DIJI Birthday Supplier Portal invitation</title>
</head>
<body style="margin:0;padding:0;background:{_BRAND_BG};font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BRAND_BG};padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;
                      border:1px solid {_BRAND_BORDER};">
          <tr>
            <td style="background:linear-gradient(135deg,{_BRAND_ORANGE_DEEP},{_BRAND_ORANGE});
                       padding:20px 28px;">
              <p style="margin:0;font-size:12px;font-weight:700;letter-spacing:.08em;
                        text-transform:uppercase;color:#ffe8d6;">DIJI Birthday</p>
              <p style="margin:4px 0 0 0;font-size:18px;font-weight:700;color:#ffffff;">
                Supplier Portal Invitation
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 28px 4px 28px;font-size:14px;color:{_BRAND_TEXT};">
              Hello {escape(greeting_name)},
            </td>
          </tr>
          <tr>
            <td style="padding:4px 28px 4px 28px;font-size:14px;color:{_BRAND_TEXT};">
              You've been invited to access the DIJI Birthday Supplier Portal for
              <strong>{escape(supplier_name)}</strong>.
            </td>
          </tr>
          <tr>
            <td style="padding:4px 28px 0 28px;font-size:14px;color:{_BRAND_TEXT};">
              Through the Supplier Portal you can securely review and manage birthday orders
              assigned to your organisation.
            </td>
          </tr>
          {cta}
          <tr>
            <td style="padding:8px 28px 0 28px;font-size:13px;color:{_BRAND_TEXT_SECONDARY};text-align:center;">
              Sign in using: <strong style="color:{_BRAND_TEXT};">{escape(email)}</strong>
              <br>Use your Microsoft account to complete the sign-in process.
            </td>
          </tr>
          <tr>
            <td style="padding:16px 28px 0 28px;font-size:12px;color:{_BRAND_TEXT_SECONDARY};text-align:center;">
              If you have not previously accessed the portal, Microsoft may guide you through the
              guest-account acceptance/sign-in process.
            </td>
          </tr>
          <tr>
            <td style="padding:24px 28px 28px 28px;font-size:12px;color:{_BRAND_TEXT_SECONDARY};
                       border-top:1px solid {_BRAND_BORDER};margin-top:20px;">
              Regards,<br>Dijital Team &middot; DIJI Birthday
              <br><br>
              Diji App Notifications &middot; Dijital Team
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
