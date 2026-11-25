"""Branded HTML email templates for missed-checkout staged reminders.

Sender display: "Diji App Notifications" <appassistant@dijitalteam.com>
(set at the transport level; never overridden here).

Templates use inline CSS only — no external stylesheets — so they render
correctly in Outlook and other clients that strip <head> styles.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_BRAND = "#E85D04"  # dt-orange
_BRAND_DARK = "#C44B00"
_TEXT = "#1A1A1A"
_TEXT_SEC = "#6B6B6B"
_BG = "#F9F5F0"
_WHITE = "#FFFFFF"
_BORDER = "#E5DDD5"


def _base_html(title: str, body_content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title></head>
<body style="margin:0;padding:0;background:{_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:32px 16px;">
    <tr><td align="center">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:{_WHITE};border-radius:12px;border:1px solid {_BORDER};overflow:hidden;">
        <!-- Header -->
        <tr><td style="background:{_BRAND};padding:20px 32px;">
          <span style="color:{_WHITE};font-size:18px;font-weight:700;letter-spacing:-0.3px;">DijiAtWork</span>
          <span style="color:rgba(255,255,255,0.7);font-size:13px;margin-left:8px;">by Dijital Team</span>
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:32px;">
          {body_content}
        </td></tr>
        <!-- Footer -->
        <tr><td style="padding:16px 32px 24px;border-top:1px solid {_BORDER};">
          <p style="margin:0;font-size:12px;color:{_TEXT_SEC};">This message was sent by DijiAtWork. If you have already checked out or submitted a correction, you can ignore this message.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _fmt_local(dt: datetime, zone: ZoneInfo) -> str:
    local = dt.astimezone(zone)
    return local.strftime("%-d %B %Y at %-I:%M %p")


def _action_button(label: str, url: str) -> str:
    return (
        f'<a href="{url}" style="display:inline-block;margin-top:24px;padding:12px 28px;'
        f"background:{_BRAND};color:{_WHITE};font-size:14px;font-weight:600;text-decoration:none;"
        f'border-radius:8px;">{label}</a>'
    )


def render_stage1_email(
    *,
    employee_name: str,
    check_in_at: datetime,
    zone: ZoneInfo,
    zone_name: str,
    app_url: str,
) -> tuple[str, str]:
    """Stage 1 (10 h): friendly reminder. Returns (subject, html_body)."""
    subject = "DijiAtWork | Your work session is still active"
    check_in_str = _fmt_local(check_in_at, zone)
    body = f"""
      <p style="margin:0 0 8px;font-size:16px;font-weight:600;color:{_TEXT};">Hi {employee_name},</p>
      <p style="margin:0 0 20px;font-size:14px;color:{_TEXT_SEC};">Your DijiAtWork session has been active for over <strong style="color:{_TEXT};">10 hours</strong>.</p>
      <table cellpadding="0" cellspacing="0" style="background:{_BG};border-radius:8px;padding:16px;width:100%;margin-bottom:4px;">
        <tr><td style="font-size:13px;color:{_TEXT_SEC};">Check-in time</td></tr>
        <tr><td style="font-size:15px;font-weight:600;color:{_TEXT};padding-top:4px;">{check_in_str}</td></tr>
        <tr><td style="font-size:13px;color:{_TEXT_SEC};padding-top:12px;">Time zone</td></tr>
        <tr><td style="font-size:14px;color:{_TEXT};padding-top:2px;">{zone_name}</td></tr>
      </table>
      <p style="margin:20px 0 0;font-size:14px;color:{_TEXT_SEC};">If you have finished working, please check out now. If you need to record a different end time, you can submit a correction request.</p>
      {_action_button("Check Out Now", f"{app_url}/atwork")}
    """
    return subject, _base_html(subject, body)


def render_stage2_email(
    *,
    employee_name: str,
    check_in_at: datetime,
    zone: ZoneInfo,
    zone_name: str,
    threshold_hours: int,
    app_url: str,
) -> tuple[str, str]:
    """Stage 2 (policy threshold, default 12 h): possible missed checkout."""
    subject = "DijiAtWork | Action required: Possible missed checkout"
    check_in_str = _fmt_local(check_in_at, zone)
    body = f"""
      <p style="margin:0 0 8px;font-size:16px;font-weight:600;color:{_TEXT};">Hi {employee_name},</p>
      <p style="margin:0 0 20px;font-size:14px;color:{_TEXT_SEC};">Your DijiAtWork session has been open for over <strong style="color:{_TEXT};">{threshold_hours} hours</strong>. This may indicate a missed check-out.</p>
      <table cellpadding="0" cellspacing="0" style="background:{_BG};border-radius:8px;padding:16px;width:100%;margin-bottom:4px;">
        <tr><td style="font-size:13px;color:{_TEXT_SEC};">Check-in time</td></tr>
        <tr><td style="font-size:15px;font-weight:600;color:{_TEXT};padding-top:4px;">{check_in_str}</td></tr>
        <tr><td style="font-size:13px;color:{_TEXT_SEC};padding-top:12px;">Time zone</td></tr>
        <tr><td style="font-size:14px;color:{_TEXT};padding-top:2px;">{zone_name}</td></tr>
      </table>
      <p style="margin:20px 0 0;font-size:14px;color:{_TEXT_SEC};">The session's elapsed time is currently shown as unverified. Please check out or submit a correction request so your attendance record is accurate.</p>
      {_action_button("Check Out or Request Correction", f"{app_url}/atwork")}
    """
    return subject, _base_html(subject, body)


def render_stage3_email(
    *,
    employee_name: str,
    check_in_at: datetime,
    zone: ZoneInfo,
    zone_name: str,
    app_url: str,
) -> tuple[str, str]:
    """Stage 3 (24 h): final follow-up."""
    subject = "DijiAtWork | Follow-up: Your attendance session remains open"
    check_in_str = _fmt_local(check_in_at, zone)
    body = f"""
      <p style="margin:0 0 8px;font-size:16px;font-weight:600;color:{_TEXT};">Hi {employee_name},</p>
      <p style="margin:0 0 20px;font-size:14px;color:{_TEXT_SEC};">Your DijiAtWork session has now been open for over <strong style="color:{_TEXT};">24 hours</strong>. No action has been taken yet.</p>
      <table cellpadding="0" cellspacing="0" style="background:{_BG};border-radius:8px;padding:16px;width:100%;margin-bottom:4px;">
        <tr><td style="font-size:13px;color:{_TEXT_SEC};">Check-in time</td></tr>
        <tr><td style="font-size:15px;font-weight:600;color:{_TEXT};padding-top:4px;">{check_in_str}</td></tr>
        <tr><td style="font-size:13px;color:{_TEXT_SEC};padding-top:12px;">Time zone</td></tr>
        <tr><td style="font-size:14px;color:{_TEXT};padding-top:2px;">{zone_name}</td></tr>
      </table>
      <p style="margin:20px 0 0;font-size:14px;color:{_TEXT_SEC};">Your attendance manager has also been notified. Please check out or submit a correction request as soon as possible.</p>
      {_action_button("Check Out or Request Correction", f"{app_url}/atwork")}
    """
    return subject, _base_html(subject, body)
