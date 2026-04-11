"""
agents/marketing_agent.py - Marketing Agent for LaunchMind

RESPONSIBILITIES:
  1. Receive product spec + task from CEO
  2. Use LLM to generate:
     - Tagline (< 10 words)
     - Description (2-3 sentences)
     - Cold email body
     - 3 social media posts (Twitter/LinkedIn/Instagram)
  3. REAL API actions:
     - Send cold email via SendGrid
     - Post rich Slack message with Block Kit (tagline + description + PR link)
  4. Return all marketing content to CEO
  5. Handle revision_request from CEO
"""

import json
import re
from message_bus import MessageBus, build_message
from utils.llm import send_prompt_json, send_prompt
from utils.email_api import send_email, build_cold_email_html
from utils.slack_api import send_block_message, build_launch_blocks

AGENT_NAME = "MARKETING"


class MarketingAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    # ──────────────────────────────────────────
    #  Main processing tick
    # ──────────────────────────────────────────
    def process(self) -> None:
        messages = self.bus.fetch(AGENT_NAME)
        for msg in messages:
            self._handle_message(msg)

    # ──────────────────────────────────────────
    #  Message dispatcher
    # ──────────────────────────────────────────
    def _handle_message(self, msg: dict) -> None:
        mtype = msg["message_type"]

        if mtype == "task":
            print(f"\n[MARKETING] 📬 Received task from {msg['from_agent']}")
            result = self._process_task(msg["payload"])
            self._send_result(result, parent_id=msg["message_id"])

        elif mtype == "revision_request":
            print(f"\n[MARKETING] 🔁 Revision request from {msg['from_agent']}")
            feedback = msg["payload"].get("feedback", "")
            original = msg["payload"].get("original_result", {})
            result   = self._revise(original, feedback)
            self._send_result(result, parent_id=msg["message_id"])

        else:
            print(f"[MARKETING] ℹ️  Ignoring message type '{mtype}'")

    # ──────────────────────────────────────────
    #  Core task processing
    # ──────────────────────────────────────────
    def _process_task(self, payload: dict) -> dict:
        spec   = payload.get("product_spec", {})
        idea   = payload.get("idea", "")

        # The PR URL might not be available yet (Marketing runs in parallel with Engineer)
        # We'll use a placeholder and update when we know
        pr_url = payload.get("pr_url", "https://github.com/Hasankhan2003/launchmind")

        # Step 1: Generate all content with LLM
        content = self._generate_marketing_content(idea, spec)

        # Step 2: Send real email
        self._send_cold_email(content, pr_url)

        # Step 3: Post Slack message
        self._post_slack_message(content, pr_url)

        return content

    def _revise(self, original: dict, feedback: str) -> dict:
        """Revise marketing content and repost to channels."""
        print(f"[MARKETING] 🧠 Revising content based on: '{feedback}'")
        revised = self._revise_content(original, feedback)

        # Re-send email with revised content
        pr_url = original.get("pr_url", "https://github.com")
        self._send_cold_email(revised, pr_url)
        self._post_slack_message(revised, pr_url)

        return revised

    # ──────────────────────────────────────────
    #  LLM: generate marketing content
    # ──────────────────────────────────────────
    def _generate_marketing_content(self, idea: str, spec: dict) -> dict:
        print("[MARKETING] 🧠 Generating marketing content with LLM...")

        value_prop = spec.get("value_proposition", "")
        tone       = spec.get("tone", "empathetic and motivating")
        personas   = spec.get("personas", [])
        persona_names = ", ".join(p.get("role", "") for p in personas) if personas else "University students"

        prompt = f"""You are a senior marketing strategist for a startup accelerator.

Startup: "AI Study Planner"
Idea: "{idea}"
Value Proposition: "{value_prop}"
Target audience: {persona_names}
Tone: {tone}

Create the following marketing content as a valid JSON object (no markdown, no code fences):

{{
  "tagline": "<MAX 10 WORDS - punchy, emotional, memorable>",
  "description": "<2-3 sentences. Explain what the product does, who it's for, and why it matters. Focus on reducing exam stress and boosting productivity.>",
  "cold_email": {{
    "subject": "<compelling email subject line>",
    "body": "<4-6 paragraphs cold email to potential early adopters. Personal, empathetic, ends with a clear CTA.>"
  }},
  "social_posts": {{
    "twitter": "<tweet under 280 chars, includes 2-3 hashtags like #StudyTips #AI #StudentLife>",
    "linkedin": "<professional LinkedIn post 2-3 paragraphs, storytelling approach, ends with a question>",
    "instagram": "<Instagram caption with emojis, upbeat tone, 5-7 hashtags at the end>"
  }}
}}

Make the tagline emotionally resonate with students under exam pressure. Be authentic, not corporate."""

        raw     = send_prompt_json(prompt, temperature=0.7)
        content = self._parse_json(raw, self._default_content())
        print("[MARKETING] ✅ Marketing content generated.")
        return content

    def _revise_content(self, original: dict, feedback: str) -> dict:
        prompt = f"""You are a marketing strategist revising content based on CEO feedback.

CEO feedback: "{feedback}"

Original content:
{json.dumps(original, indent=2)[:2000]}

Produce an IMPROVED version addressing the feedback.
Return only valid JSON (same structure, no markdown):
{{
  "tagline": "...",
  "description": "...",
  "cold_email": {{"subject": "...", "body": "..."}},
  "social_posts": {{"twitter": "...", "linkedin": "...", "instagram": "..."}}
}}"""

        raw = send_prompt_json(prompt, temperature=0.5)
        return self._parse_json(raw, original)

    # ──────────────────────────────────────────
    #  Real API Actions
    # ──────────────────────────────────────────
    def _send_cold_email(self, content: dict, pr_url: str) -> None:
        """Send actual cold email via SendGrid."""
        cold_email = content.get("cold_email", {})
        subject    = cold_email.get("subject", "Introducing AI Study Planner 🚀")
        body_text  = cold_email.get("body", "Please check out our new product.")
        tagline    = content.get("tagline", "")
        description = content.get("description", "")

        html_body = build_cold_email_html(
            tagline=tagline,
            description=description,
            cold_email_body=body_text,
            pr_url=pr_url,
        )

        try:
            result = send_email(
                subject=subject,
                body_text=body_text,
                body_html=html_body,
            )
            print(f"[MARKETING] ✅ Cold email sent. Status: {result.get('status_code')}")
        except Exception as e:
            print(f"[MARKETING] ⚠️  Email failed: {e}")

    def _post_slack_message(self, content: dict, pr_url: str) -> None:
        """Post rich Block Kit Slack message."""
        tagline     = content.get("tagline", "Study smarter, not harder.")
        description = content.get("description", "AI Study Planner helps students.")
        twitter     = content.get("social_posts", {}).get("twitter", "")

        try:
            blocks = build_launch_blocks(
                tagline=tagline,
                description=description,
                pr_url=pr_url,
            )
            # Add social posts section
            if twitter:
                blocks.insert(-1, {  # insert before footer context
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📢 Social Preview:*\n{twitter}",
                    },
                })

            send_block_message(
                text=f"🚀 Marketing update: {tagline}",
                blocks=blocks,
            )
            print("[MARKETING] ✅ Slack Block Kit message posted.")
        except Exception as e:
            print(f"[MARKETING] ⚠️  Slack post failed: {e}")

    # ──────────────────────────────────────────
    #  Send result to CEO
    # ──────────────────────────────────────────
    def _send_result(self, result: dict, parent_id: str) -> None:
        msg = build_message(
            from_agent=AGENT_NAME,
            to_agent="CEO",
            message_type="result",
            payload=result,
            parent_message_id=parent_id,
        )
        self.bus.send(msg)
        print("[MARKETING] 📤 Result sent to CEO.")

    # ──────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────
    @staticmethod
    def _parse_json(raw: str, default: dict) -> dict:
        try:
            clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
            return json.loads(clean)
        except Exception:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
            print(f"[MARKETING] ⚠️  JSON parse failed, using default. Raw: {raw[:200]}")
            return default

    @staticmethod
    def _default_content() -> dict:
        return {
            "tagline": "Study smarter. Stress less. Succeed always.",
            "description": (
                "AI Study Planner is an intelligent tool that transforms your university syllabus "
                "and exam dates into a personalized daily study schedule. Say goodbye to last-minute cramming "
                "and hello to confident, organized learning."
            ),
            "cold_email": {
                "subject": "🎓 Struggling with exam prep? We built something for you.",
                "body": (
                    "Hi there,\n\n"
                    "Exam season can feel overwhelming — trust us, we know.\n\n"
                    "That's why we built AI Study Planner: an AI-powered tool that takes your syllabus "
                    "and exam dates and creates a realistic daily study schedule just for you.\n\n"
                    "No more guessing what to study. No more all-nighters. Just a clear, balanced plan "
                    "that works with your life.\n\n"
                    "We'd love for you to be one of our first users. It's free to get started.\n\n"
                    "Best,\nThe AI Study Planner Team"
                ),
            },
            "social_posts": {
                "twitter": (
                    "🎓 Tired of cramming the night before exams? AI Study Planner converts your "
                    "syllabus into a daily schedule. Study smarter, not harder. "
                    "#StudyTips #AI #StudentLife"
                ),
                "linkedin": (
                    "University students spend hours trying to figure out WHAT to study and WHEN. "
                    "That's why we built AI Study Planner — it turns your syllabus and exam dates "
                    "into a personalized daily study roadmap.\n\n"
                    "Less stress. More progress. Better grades.\n\n"
                    "What's your biggest study challenge? Drop it in the comments 👇"
                ),
                "instagram": (
                    "📚 No more last-minute panic! AI Study Planner creates your personalized "
                    "study schedule from your syllabus 🗓️✨\n\n"
                    "Smart planning = better grades 🎯\n\n"
                    "#StudySmart #AIStudyPlanner #UniversityLife #ExamPrep #StudentHacks "
                    "#StudyMotivation #AcademicSuccess"
                ),
            },
        }
