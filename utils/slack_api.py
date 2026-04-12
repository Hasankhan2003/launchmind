"""
utils/slack_api.py - Slack Web API wrapper for LaunchMind

Provides:
  - send_block_message(channel, text, blocks)  → post a rich Block Kit message
  - send_simple_message(channel, text)         → post plain text message

Uses the Slack Web API (chat.postMessage) with a Bot Token.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL   = os.getenv("SLACK_CHANNEL", "#launches")

SLACK_API_URL = "https://slack.com/api/chat.postMessage"


def _headers() -> dict:
    if not SLACK_BOT_TOKEN:
        raise EnvironmentError("SLACK_BOT_TOKEN is not set in the environment.")
    return {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    }


# ─────────────────────────────────────────────
#  Public Functions
# ─────────────────────────────────────────────

def send_block_message(
    text: str,
    blocks: list,
    channel: str = SLACK_CHANNEL,
) -> dict:
    """
    Post a rich Block Kit message to Slack.

    Args:
        text:    Fallback plain text (shown in notifications / accessibility).
        blocks:  List of Slack Block Kit block objects.
        channel: Slack channel ID or name (default from env).

    Returns:
        Slack API response JSON.

    Raises:
        RuntimeError if the Slack API returns an error.
    """
    print(f"[Slack] Posting Block Kit message to {channel}...")

    payload = {
        "channel": channel,
        "text": text,      # fallback
        "blocks": blocks,
    }

    resp = requests.post(
        SLACK_API_URL,
        headers=_headers(),
        data=json.dumps(payload),
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data.get("ok"):
        error = data.get("error", "unknown_error")
        raise RuntimeError(f"[Slack] API error: {error}  |  response: {data}")

    print(f"[Slack] ✓ Message posted to {channel} (ts={data.get('ts')})")
    return data


def send_simple_message(text: str, channel: str = SLACK_CHANNEL) -> dict:
    """
    Post a plain-text message to Slack.

    A convenience wrapper around send_block_message with a single section block.
    """
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        }
    ]
    return send_block_message(text=text, blocks=blocks, channel=channel)


def build_launch_blocks(
    tagline: str,
    description: str,
    pr_url: str,
    startup_name: str = "AI Study Planner",
    posted_by: str = "CEO",
    timestamp: str = None,
) -> list:
    """
    Build a rich Slack Block Kit layout for the startup launch announcement.

    Includes:
      - Agent/sender identification with timestamp
      - Header with startup name
      - Tagline (bold)
      - Description paragraph
      - GitHub PR link button
      - Divider footer with metadata

    Args:
        tagline:      One-liner tagline for the product
        description:  Description paragraph
        pr_url:       GitHub PR URL
        startup_name: Product name (default: "AI Study Planner")
        posted_by:    Agent name that posted this (default: "CEO")
        timestamp:    ISO timestamp string (auto-generated if None)
    """
    from datetime import datetime, timezone
    
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    
    # Extract just the time for readability
    time_str = timestamp.split('T')[1].split('.')[0] if 'T' in timestamp else timestamp
    
    # Agent-specific colors for visual differentiation
    agent_colors = {
        "CEO": "#1f88d5",        # Blue
        "MARKETING": "#e91e63",  # Pink/Magenta
        "PRODUCT": "#4caf50",    # Green
        "ENGINEER": "#ff9800",   # Orange
        "QA": "#9c27b0",         # Purple
    }
    color = agent_colors.get(posted_by, "#808080")  # Gray fallback
    
    return [
        # Agent header with timestamp
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*👤 Posted by:* {posted_by}\n_at {time_str} UTC_",
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "📌", "emoji": True},
                "value": "pinned",
                "style": "primary",
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚀 LaunchMind — {startup_name} is LIVE!",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Tagline:*\n_{tagline}_",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*About:*\n{description}",
            },
        },
        # Only add the button if we have a valid HTTPS URL
        *(
            [{
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "🔗 View GitHub PR", "emoji": True},
                        "url": pr_url,
                        "style": "primary",
                    }
                ],
            }]
            if pr_url and pr_url.startswith("https://")
            else [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🔗 GitHub:* {pr_url or 'PR pending…'}",
                },
            }]
        ),
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🤖 *LaunchMind* (Agent: {posted_by}) — AI-powered startup accelerator | Generated on {timestamp.split('T')[0]}",
                }
            ],
        },
    ]
