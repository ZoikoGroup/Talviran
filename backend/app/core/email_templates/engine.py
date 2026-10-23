"""Talvrin Unified Email Notification Engine & Template Renderer.

Implements all 199 event-linked email templates specified in
TAL-COMM-EMAIL-001 (Talvrin Email Communications Estate v1.0).
Provides a uniform, premium HTML design template featuring:
- Official Talvrin logo & branding header
- High-contrast typography & sleek dark theme (#0b0f19 / #111827 / #182234)
- Direct Call-to-Action buttons
- Verified audit trail, legal footer, and security compliance notes
"""

from __future__ import annotations

import html
import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.email_templates.logo_data import TALVRIN_LOGO_PNG_B64
from app.modules.monitoring.delivery import _send_resend_email

logger = logging.getLogger(__name__)

_TEMPLATES_FILE = Path(__file__).parent / "templates_199.json"
_REGISTRY: dict[str, dict[str, Any]] = {}


def _load_registry() -> dict[str, dict[str, Any]]:
    global _REGISTRY
    if not _REGISTRY and _TEMPLATES_FILE.exists():
        try:
            with open(_TEMPLATES_FILE, encoding="utf-8") as f:
                _REGISTRY = json.load(f)
        except Exception as exc:
            logger.error("Failed to load email templates registry: %s", exc)
    return _REGISTRY


def get_template(template_id: str) -> dict[str, Any] | None:
    """Retrieve template definition by canonical ID."""
    reg = _load_registry()
    return reg.get(template_id)


def list_templates() -> list[dict[str, Any]]:
    """Retrieve list of all 199 email templates."""
    reg = _load_registry()
    return list(reg.values())


def render_talvrin_email_html(
    *,
    subject: str,
    preheader: str,
    body_text: str,
    cta_label: str | None = None,
    action_url: str | None = None,
    badge_label: str = "Evidence Notification",
    notice_reference: str | None = None,
) -> str:
    """Renders the executive, high-aesthetic Talvrin HTML email layout with official logo."""
    # Convert body paragraphs to HTML
    paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
    formatted_body_chunks = []
    for p in paragraphs:
        # Check if paragraph has key-value items or links
        escaped = html.escape(p).replace("\n", "<br/>")
        formatted_body_chunks.append(
            f'<p style="margin: 0 0 16px; font-size: 14px; line-height: 1.6; color: #cbd5e1;">{escaped}</p>'
        )
    body_html = "".join(formatted_body_chunks)

    # CTA Button
    cta_html = ""
    if cta_label and action_url:
        cta_html = f"""
        <div style="margin: 28px 0 24px; text-align: left;">
          <a href="{html.escape(action_url)}" target="_blank"
             style="display: inline-block; background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
                    color: #ffffff; text-decoration: none; font-size: 13px; font-weight: 600;
                    padding: 12px 24px; border-radius: 8px; box-shadow: 0 4px 12px rgba(79, 70, 229, 0.35);
                    letter-spacing: -0.01em;">
            {html.escape(cta_label)} &rarr;
          </a>
        </div>
        """

    notice_ref_html = (
        f'<span style="color: #64748b; font-family: monospace; font-size: 11px;">Notice Ref: {html.escape(notice_reference)}</span>'
        if notice_reference
        else ""
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
</head>
<body style="margin: 0; padding: 28px 16px; background-color: #06090e; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0;">
  <!-- Preview / Preheader text for mail clients -->
  <div style="display: none; font-size: 1px; color: #06090e; line-height: 1px; max-height: 0px; max-width: 0px; opacity: 0; overflow: hidden;">
    {html.escape(preheader)}
  </div>

  <div style="max-width: 600px; margin: 0 auto; background-color: #0f1623; border: 1px solid #1e293b; border-radius: 14px; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.65);">
    <!-- Header with Talvrin Branding & Logo -->
    <div style="padding: 24px 32px; border-bottom: 1px solid #1e293b; background: linear-gradient(180deg, #162032 0%, #0f1623 100%);">
      <table style="width: 100%; border-collapse: collapse;">
        <tr>
          <td style="vertical-align: middle; width: 44px; padding-right: 12px;">
            <img src="data:image/png;base64,{TALVRIN_LOGO_PNG_B64}" width="38" height="38"
                 alt="Talvrin Logo"
                 style="display: block; width: 38px; height: 38px; border-radius: 8px; border: 1px solid rgba(129, 140, 248, 0.4); box-shadow: 0 2px 8px rgba(0,0,0,0.4);" />
          </td>
          <td style="vertical-align: middle;">
            <span style="font-size: 20px; font-weight: 800; letter-spacing: -0.02em; color: #ffffff; line-height: 1;">TALVRIN</span>
            <p style="margin: 4px 0 0; font-size: 11.5px; color: #94a3b8; letter-spacing: 0.02em; line-height: 1.2;">
              Evidence. Precision. Clarity. Vigilance.
            </p>
          </td>
          <td style="text-align: right; vertical-align: middle;">
            <span style="display: inline-block; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; background: rgba(99, 102, 241, 0.15); color: #818cf8; padding: 4px 10px; border-radius: 9999px; border: 1px solid rgba(99, 102, 241, 0.3);">
              {html.escape(badge_label)}
            </span>
          </td>
        </tr>
      </table>
    </div>


    <!-- Main Message Body -->
    <div style="padding: 32px 32px 24px;">
      <h1 style="margin: 0 0 18px; font-size: 20px; font-weight: 700; color: #f8fafc; line-height: 1.35; letter-spacing: -0.01em;">
        {html.escape(subject)}
      </h1>

      <div style="margin-bottom: 20px;">
        {body_html}
      </div>

      {cta_html}
    </div>

    <!-- Legal & Security Footer -->
    <div style="padding: 24px 32px 36px; background-color: #0a0f18; border-top: 1px solid #1e293b;">
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 14px;">
        <tr>
          <td style="vertical-align: middle; font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em;">
            Zoiko Group &bull; Talvrin Research &amp; Data Platform
          </td>
          <td style="text-align: right; vertical-align: middle;">
            {notice_ref_html}
          </td>
        </tr>
      </table>

      <p style="margin: 0 0 10px; font-size: 11.5px; color: #94a3b8; line-height: 1.55;">
        Talvrin delivers factual market observations, pinned calculations and objective monitoring. This transmission does not constitute financial, investment, or trading advice.
      </p>
      <p style="margin: 0; font-size: 11px; color: #64748b; line-height: 1.5;">
        Security Notice: Talvrin will never ask for your password, recovery key, or 2FA credentials via email.
      </p>
    </div>
  </div>
  <div style="height: 32px; line-height: 32px;">&nbsp;</div>
</body>
</html>"""



def send_talvrin_template_email(
    *,
    template_id: str,
    recipient_email: str,
    variables: dict[str, Any] | None = None,
    badge_label: str = "Evidence Notification",
) -> bool:
    """Dispatches any of the 199 Talvrin email templates using Resend."""
    tpl = get_template(template_id)
    if not tpl:
        logger.warning("Email template not found: %s", template_id)
        return False

    settings = get_settings()
    if not settings.resend_api_key:
        logger.warning("Cannot dispatch email: resend_api_key not configured")
        return False

    vars_dict = variables or {}

    # Replace {{var}} in subject, preheader, body
    subject = tpl["subject"]
    preheader = tpl["preheader"]
    body = tpl["body"]
    cta_label = tpl["cta_label"] or "Open Talvrin"
    action_url = vars_dict.get("action_url") or "https://app.talvrin.com"

    for k, v in vars_dict.items():
        placeholder = f"{{{{{k}}}}}"
        str_val = str(v)
        subject = subject.replace(placeholder, str_val)
        preheader = preheader.replace(placeholder, str_val)
        body = body.replace(placeholder, str_val)

    # Clean unreplaced placeholders with blanks or defaults
    import re
    subject = re.sub(r"\{\{[^}]+\}\}", "", subject).strip()
    preheader = re.sub(r"\{\{[^}]+\}\}", "", preheader).strip()
    body = re.sub(r"\{\{[^}]+\}\}", "", body).strip()

    html_content = render_talvrin_email_html(
        subject=subject,
        preheader=preheader,
        body_text=body,
        cta_label=cta_label,
        action_url=action_url,
        badge_label=badge_label,
        notice_reference=str(vars_dict.get("notice_reference") or template_id),
    )

    return _send_resend_email(
        to_email=recipient_email,
        subject=subject,
        html_content=html_content,
        api_key=settings.resend_api_key,
        from_email=settings.alerts_from_email,
    )
