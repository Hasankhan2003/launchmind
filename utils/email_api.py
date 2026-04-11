"""
utils/email_api.py - SendGrid Email wrapper for LaunchMind

Provides:
  - send_email(to, subject, body_text, body_html)

Uses the SendGrid Web API v3 via the `sendgrid` Python SDK.
"""

import os
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Content, To

load_dotenv()

# ─────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL     = os.getenv("SENDER_EMAIL")
RECEIVER_EMAIL   = os.getenv("RECEIVER_EMAIL")


# ─────────────────────────────────────────────
#  Public Functions
# ─────────────────────────────────────────────

def send_email(
    subject: str,
    body_text: str,
    body_html: str | None = None,
    to_email: str | None = None,
    from_email: str | None = None,
) -> dict:
    """
    Send a transactional email via SendGrid.

    Args:
        subject:    Email subject line.
        body_text:  Plain-text email body (always provided).
        body_html:  Optional HTML body. Falls back to wrapping body_text in <pre>.
        to_email:   Recipient address. Defaults to RECEIVER_EMAIL env var.
        from_email: Sender address.  Defaults to SENDER_EMAIL env var.

    Returns:
        A dict with 'status_code' and 'message_id' from SendGrid.

    Raises:
        EnvironmentError if API key / addresses are not configured.
        RuntimeError if SendGrid returns an error.
    """
    if not SENDGRID_API_KEY:
        raise EnvironmentError("SENDGRID_API_KEY is not set in the environment.")

    recipient = to_email or RECEIVER_EMAIL
    sender    = from_email or SENDER_EMAIL

    if not recipient:
        raise EnvironmentError("Recipient email is not configured (RECEIVER_EMAIL).")
    if not sender:
        raise EnvironmentError("Sender email is not configured (SENDER_EMAIL).")

    html_content = body_html or f"<pre>{body_text}</pre>"

    message = Mail(
        from_email=sender,
        to_emails=recipient,
        subject=subject,
        plain_text_content=body_text,
        html_content=html_content,
    )

    print(f"[Email] Sending '{subject}' → {recipient}...")

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        message_id = response.headers.get("X-Message-Id", "N/A")
        print(f"[Email] ✓ Email sent. Status: {response.status_code}, ID: {message_id}")
        return {"status_code": response.status_code, "message_id": message_id}
    except Exception as exc:
        raise RuntimeError(f"[Email] SendGrid error: {exc}") from exc


def build_cold_email_html(
    tagline: str,
    description: str,
    cold_email_body: str,
    pr_url: str,
    startup_name: str = "AI Study Planner",
) -> str:
    """
    Build a styled HTML cold email for the startup launch.
    """
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: #f5f7fa; margin: 0; padding: 0; }}
  .container {{ max-width: 600px; margin: 30px auto; background: #ffffff; border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.08); overflow: hidden; }}
  .header {{ background: linear-gradient(135deg, #6366f1, #8b5cf6); padding: 36px 40px; color: #fff; }}
  .header h1 {{ margin: 0 0 8px; font-size: 28px; }}
  .header p {{ margin: 0; opacity: 0.85; font-size: 15px; }}
  .body {{ padding: 36px 40px; color: #374151; line-height: 1.7; }}
  .tagline {{ font-size: 20px; font-weight: 700; color: #6366f1; margin-bottom: 16px; }}
  .cta {{ display: inline-block; margin-top: 24px; padding: 14px 28px;
           background: #6366f1; color: #fff; border-radius: 8px;
           text-decoration: none; font-weight: 600; font-size: 15px; }}
  .footer {{ background: #f9fafb; padding: 20px 40px; font-size: 12px; color: #9ca3af;
             border-top: 1px solid #e5e7eb; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🚀 {startup_name}</h1>
    <p>AI-Powered Study Planning for University Students</p>
  </div>
  <div class="body">
    <div class="tagline">{tagline}</div>
    <p>{description}</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
    <p>{cold_email_body}</p>
    <a class="cta" href="{pr_url}">🔗 See the Project on GitHub</a>
  </div>
  <div class="footer">
    You received this because you're part of our early adopter list.<br>
    Built with ❤️ by LaunchMind — the AI Startup Accelerator.
  </div>
</div>
</body>
</html>
"""
