"""Renders the supplier order-release notification — subject, HTML body,
and a plain-text fallback. Table-based, inline-styled HTML only (no
external CSS/JS) so it renders consistently in Gmail and Outlook.

Kept as its own module (rather than growing inline in
order_email_service.py) purely for readability — it owns no business
rules; every value it needs is passed in already resolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape

from app.core.config import get_settings
from app.models.birthday_order import BirthdayOrder
from app.models.supplier import Supplier

# BambooHR's own placeholder for "no office set" (verified live) — never
# shown to a supplier verbatim; substituted with a professional label
# instead. The underlying order.office_location snapshot is untouched.
_UNSET_OFFICE_MARKERS = {"", "unassigned office"}

_BRAND_ORANGE = "#c9431d"
_BRAND_ORANGE_DEEP = "#aa2f1d"
_BRAND_CREAM = "#fff8ef"
_BRAND_BG = "#f8f5f2"
_BRAND_TEXT = "#24140f"
_BRAND_TEXT_SECONDARY = "#76584c"
_BRAND_BORDER = "#eadbd3"


@dataclass(frozen=True)
class SupplierEmailContent:
    subject: str
    html_body: str
    text_body: str


def _format_date(value: date) -> str:
    # "27 September 2026" — built without %-d/%#d (neither is portable
    # across the Linux containers this runs in and Windows, where tests
    # also run) rather than relying on a platform-specific strftime flag.
    return f"{value.day} {value.strftime('%B %Y')}"


def _display_office_location(office_location: str) -> str:
    if (office_location or "").strip().lower() in _UNSET_OFFICE_MARKERS:
        return "To be confirmed"
    return office_location


def _order_portal_url(order: BirthdayOrder) -> str | None:
    base = get_settings().supplier_public_base_url.rstrip("/")
    if not base:
        return None
    return f"{base}/orders/{order.id}"


def render_supplier_order_email(
    order: BirthdayOrder, supplier_instructions: list[str]
) -> SupplierEmailContent:
    subject = f"[{order.order_reference}] New Birthday Cake Order — {order.employee_name}"

    supplier: Supplier | None = order.supplier
    greeting_name = (
        (supplier.primary_contact_name if supplier else "") or (supplier.name if supplier else "") or ""
    ).strip()
    office_display = _display_office_location(order.office_location)
    date_display = _format_date(order.birthday_date)
    portal_url = _order_portal_url(order)

    html_body = _render_html(
        order=order,
        greeting_name=greeting_name,
        date_display=date_display,
        office_display=office_display,
        supplier_instructions=supplier_instructions,
        portal_url=portal_url,
    )
    text_body = _render_text(
        order=order,
        greeting_name=greeting_name,
        date_display=date_display,
        office_display=office_display,
        supplier_instructions=supplier_instructions,
        portal_url=portal_url,
    )
    return SupplierEmailContent(subject=subject, html_body=html_body, text_body=text_body)


def _render_text(
    *,
    order: BirthdayOrder,
    greeting_name: str,
    date_display: str,
    office_display: str,
    supplier_instructions: list[str],
    portal_url: str | None,
) -> str:
    lines = [
        f"Hello {greeting_name}," if greeting_name else "Hello,",
        "",
        "A new birthday cake order has been assigned to you.",
        "",
        "ORDER DETAILS",
        f"Order Reference: {order.order_reference}",
        f"Employee: {order.employee_name}",
        f"Birthday / Required Date: {date_display}",
        f"Delivery / Office Location: {office_display}",
        f"Quantity: {order.quantity}",
    ]
    if supplier_instructions:
        lines.append("")
        lines.append("Special Instructions:")
        lines.extend(f"- {text}" for text in supplier_instructions)

    lines.append("")
    if portal_url:
        lines.append(f"View this order in the Supplier Portal: {portal_url}")
    lines.append(
        "Please review the order details and confirm/update the order through the Supplier Portal."
    )
    lines.append("")
    lines.append(f"Please confirm receipt of order {order.order_reference}.")
    return "\n".join(lines)


def _detail_row(label: str, value: str) -> str:
    return f"""
      <tr>
        <td style="padding:10px 0;border-bottom:1px solid {_BRAND_BORDER};font-size:12px;
                   font-weight:600;text-transform:uppercase;letter-spacing:.04em;
                   color:{_BRAND_TEXT_SECONDARY};width:44%;vertical-align:top;">{escape(label)}</td>
        <td style="padding:10px 0;border-bottom:1px solid {_BRAND_BORDER};font-size:14px;
                   color:{_BRAND_TEXT};vertical-align:top;">{escape(value)}</td>
      </tr>"""


def _render_html(
    *,
    order: BirthdayOrder,
    greeting_name: str,
    date_display: str,
    office_display: str,
    supplier_instructions: list[str],
    portal_url: str | None,
) -> str:
    greeting = f"Hello {escape(greeting_name)}," if greeting_name else "Hello,"

    rows = [
        _detail_row("Order Reference", order.order_reference),
        _detail_row("Employee", order.employee_name),
        _detail_row("Birthday / Required Date", date_display),
        _detail_row("Delivery / Office Location", office_display),
        _detail_row("Quantity", str(order.quantity)),
    ]
    if supplier_instructions:
        instructions_html = "".join(f"<li style=\"margin:2px 0;\">{escape(t)}</li>" for t in supplier_instructions)
        rows.append(f"""
      <tr>
        <td style="padding:10px 0;font-size:12px;font-weight:600;text-transform:uppercase;
                   letter-spacing:.04em;color:{_BRAND_TEXT_SECONDARY};width:44%;vertical-align:top;">
                   Special Instructions</td>
        <td style="padding:10px 0;font-size:14px;color:{_BRAND_TEXT};vertical-align:top;">
          <ul style="margin:0;padding-left:18px;">{instructions_html}</ul>
        </td>
      </tr>""")

    cta = ""
    secondary_link = ""
    if portal_url:
        cta = f"""
      <tr>
        <td align="center" style="padding:28px 0 8px 0;">
          <a href="{escape(portal_url)}"
             style="display:inline-block;background:{_BRAND_ORANGE};color:#ffffff;font-size:14px;
                    font-weight:600;text-decoration:none;padding:12px 28px;border-radius:8px;">
            View Order
          </a>
        </td>
      </tr>
      <tr>
        <td align="center" style="padding:0 24px 4px 24px;font-size:13px;color:{_BRAND_TEXT_SECONDARY};
                   text-align:center;">
          Please review the order details and confirm/update the order through the Supplier Portal.
        </td>
      </tr>"""
        portal_home = portal_url.rsplit("/orders/", 1)[0]
        secondary_link = f"""
      <tr>
        <td align="center" style="padding:10px 0 0 0;">
          <a href="{escape(portal_home)}" style="font-size:12px;color:{_BRAND_ORANGE_DEEP};">
            Open Supplier Portal
          </a>
        </td>
      </tr>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(order.order_reference)}</title>
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
                New Birthday Cake Order
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 28px 4px 28px;font-size:14px;color:{_BRAND_TEXT};">
              {greeting}
            </td>
          </tr>
          <tr>
            <td style="padding:4px 28px 16px 28px;font-size:14px;color:{_BRAND_TEXT};">
              A new birthday cake order has been assigned to you.
            </td>
          </tr>
          <tr>
            <td style="padding:0 28px;">
              <p style="margin:0 0 4px 0;font-size:11px;font-weight:700;letter-spacing:.06em;
                        text-transform:uppercase;color:{_BRAND_ORANGE_DEEP};">Order Details</p>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                {"".join(rows)}
              </table>
            </td>
          </tr>
          {cta}
          {secondary_link}
          <tr>
            <td style="padding:24px 28px 28px 28px;font-size:12px;color:{_BRAND_TEXT_SECONDARY};
                       border-top:1px solid {_BRAND_BORDER};margin-top:20px;">
              Please confirm receipt of order {escape(order.order_reference)}.
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
