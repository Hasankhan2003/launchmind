"""
agents/marketing_agent.py - Marketing Agent for LaunchMind

ROLE:
  Senior Marketing Strategist.

RESPONSIBILITIES:
  1. Receive product spec + task from the CEO
  2. Use LLM to generate high-converting, platform-specific marketing content:
       - tagline      (< 10 words, punchy)
       - description  (2-3 sentences, emotional hook)
       - cold_email   (subject + personalized body)
       - social_posts (Twitter, LinkedIn, Instagram)
  3. Validate tagline length programmatically
  4. Perform REAL API actions:
       - Send a beautifully-styled cold email via SendGrid
       - Post a rich Block Kit announcement to Slack
  5. Return content to CEO
  6. Handle revision_request: incorporate feedback, re-send emails/Slack, and resubmit
"""

import json
import re
from message_bus import MessageBus, build_message
from utils.llm import send_prompt_json
from utils.email_api import send_email, build_cold_email_html
from utils.slack_api import send_block_message, build_launch_blocks
from config import MAX_TAGLINE_WORDS

AGENT_NAME = "MARKETING"


class MarketingAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    # ──────────────────────────────────────────
    #  Main processing tick
    # ──────────────────────────────────────────
    def process(self) -> None:
        for msg in self.bus.fetch(AGENT_NAME):
            self._handle_message(msg)

    # ──────────────────────────────────────────
    #  Message dispatcher
    # ──────────────────────────────────────────
    def _handle_message(self, msg: dict) -> None:
        mtype = msg["message_type"]

        if mtype == "task":
            print(f"\n[MARKETING] 📬 Task received from {msg['from_agent']}")
            result = self._process_task(msg["payload"])
            self._send_result(result, parent_id=msg["message_id"])

        elif mtype == "revision_request":
            print(f"\n[MARKETING] 🔁 Revision request from {msg['from_agent']}")
            feedback = msg["payload"].get("feedback", "")
            original = msg["payload"].get("original_result", {})
            score    = msg["payload"].get("quality_score", 0)
            result   = self._revise(original, feedback, score)
            self._send_result(result, parent_id=msg["message_id"])

        else:
            print(f"[MARKETING] ℹ  Ignoring '{mtype}' from {msg['from_agent']}")

    # ──────────────────────────────────────────
    #  Core task processing
    # ──────────────────────────────────────────
    def _process_task(self, payload: dict) -> dict:
        spec = payload.get("product_spec", {})
        idea = payload.get("idea", "")

        # Engineer is running in parallel, PR URL might not exist yet
        pr_url = payload.get("pr_url", "https://github.com/Hasankhan2003/launchmind")

        # 1. Generate content
        content = self._generate_marketing_content(idea, spec)

        # 2. Validate tagline
        if not self._validate_tagline(content.get("tagline", "")):
            print("[MARKETING] ⚠  Tagline too long. Auto-generating a shorter one…")
            content = self._generate_marketing_content(idea, spec) # Try once more

        # 3. Real APIs
        self._send_cold_email(content, pr_url)
        self._post_slack_message(content, pr_url)

        return content

    def _revise(self, original: dict, feedback: str, score: int) -> dict:
        print(f"[MARKETING] 🧠 Revising content (CEO score={score}/10) — addressing: '{feedback[:120]}'")
        revised = self._revise_content(original, feedback)

        pr_url = original.get("pr_url", "https://github.com/Hasankhan2003/launchmind")
        self._send_cold_email(revised, pr_url)
        self._post_slack_message(revised, pr_url)

        return revised

    # ──────────────────────────────────────────
    #  LLM: generate marketing content
    # ──────────────────────────────────────────
    def _generate_marketing_content(self, idea: str, spec: dict) -> dict:
        print("[MARKETING] 🧠 Generating marketing materials (LLM)…")

        value_prop = spec.get("value_proposition", "")
        tone       = spec.get("tone", "empathetic and motivating")
        personas   = spec.get("personas", [])

        persona_str = "\n".join(f"- {p.get('name','')} ({p.get('role','')}): {p.get('pain_point','')}" for p in personas)

        prompt = f"""You are a world-class Marketing Strategist launching an EdTech startup.

Startup Idea: "{idea}"
Core Value Proposition: "{value_prop}"
Brand Voice/Tone: {tone}

Target Personas:
{persona_str}

Your task is to write high-converting, platform-specific marketing copy.
Return ONLY a valid JSON object (no markdown, no fences):

{{
  "tagline": "<MAX {MAX_TAGLINE_WORDS} WORDS. Must be punchy, memorable, and emotional>",
  "description": "<2-3 sentences. State the problem, introduce the solution, and highlight the main benefit. Do not use generic corporate speak.>",
  "cold_email": {{
    "subject": "<Compelling, short subject line (e.g. 'Never cram for an exam again')>",
    "body": "<A 4-5 paragraph cold email for early adopter outreach. Personal, empathetic tone. Acknowledge the student's pain point, explain what AI Study Planner does, and include a clear call-to-action.>"
  }},
  "social_posts": {{
    "twitter": "<Tweet under 280 chars. Engaging hook, emojis, 2-3 specific hashtags like #StudyTips>",
    "linkedin": "<Professional but storytelling LinkedIn post (3-4 paragraphs). Start with a relatable student struggle. End with a question to drive comments.>",
    "instagram": "<Instagram caption. Very visual, energetic, heavy emoji use, 5-7 popular student hashtags.>"
  }}
}}"""

        raw     = send_prompt_json(prompt, temperature=0.7)
        content = self._parse_json(raw, self._default_content())
        print("[MARKETING] ✅ Marketing content generated.")
        return content

    def _revise_content(self, original: dict, feedback: str) -> dict:
        prompt = f"""You are a Marketing Strategist revising launch content based on feedback.

Feedback to address:
"{feedback}"

Current Content:
{json.dumps(original, indent=2)[:3000]}

Rewrite the content to thoroughly address the feedback while maintaining a high standard of copywriting.
Return ONLY valid JSON (same schema as current content). No markdown fences."""

        raw = send_prompt_json(prompt, temperature=0.5)
        return self._parse_json(raw, original)

    # ──────────────────────────────────────────
    #  Actions / Validation
    # ──────────────────────────────────────────
    def _validate_tagline(self, tagline: str) -> bool:
        words = len(tagline.split())
        if words > MAX_TAGLINE_WORDS:
            print(f"[MARKETING] ❌ Tagline validation failed: {words} words > limit ({MAX_TAGLINE_WORDS})")
            return False
        print(f"[MARKETING] ✓ Tagline valid ({words} words)")
        return True

    def _send_cold_email(self, content: dict, pr_url: str) -> None:
        cold = content.get("cold_email", {})
        sub  = cold.get("subject", "Introducing AI Study Planner 🚀")
        body = cold.get("body", "Check out our new product!")

        html_body = build_cold_email_html(
            tagline=content.get("tagline", ""),
            description=content.get("description", ""),
            cold_email_body=body,
            pr_url=pr_url,
        )

        try:
            result = send_email(subject=sub, body_text=body, body_html=html_body)
            print(f"[MARKETING] ✅ Cold email sent via SendGrid (Status: {result.get('status_code')})")
        except Exception as e:
            print(f"[MARKETING] ⚠  Cold email failed: {e}")

    def _post_slack_message(self, content: dict, pr_url: str) -> None:
        tagline = content.get("tagline", "Study smarter.")
        desc    = content.get("description", "AI Study Planner helps students.")
        twit    = content.get("social_posts", {}).get("twitter", "")

        try:
            blocks = build_launch_blocks(tagline=tagline, description=desc, pr_url=pr_url)
            if twit:
                # Insert social preview right before the footer context block
                blocks.insert(-1, {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📢 Social Preview (Twitter):*\n> {twit}",
                    },
                })
            send_block_message(text=f"🚀 Marketing update: {tagline}", blocks=blocks)
            print("[MARKETING] ✅ Launch announcement posted to Slack.")
        except Exception as e:
            print(f"[MARKETING] ⚠  Slack post failed: {e}")

    # ──────────────────────────────────────────
    #  Send result to CEO
    # ──────────────────────────────────────────
    def _send_result(self, result: dict, parent_id: str) -> None:
        self.bus.send(build_message(
            from_agent=AGENT_NAME,
            to_agent="CEO",
            message_type="result",
            payload=result,
            parent_message_id=parent_id,
        ))
        print("[MARKETING] 📤 Content sent to CEO.")

    # ──────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────
    @staticmethod
    def _parse_json(raw: str, default: dict) -> dict:
        try:
            clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
            return json.loads(clean)
        except Exception:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except Exception:
                    pass
            print(f"[MARKETING] ⚠  JSON parse failed, using default.")
            return default

    @staticmethod
    def _default_content() -> dict:
        return {
            "tagline": "Study Smarter. Stress Less. Ace Every Exam.",
            "description": "AI Study Planner transforms your syllabus into a personalized daily schedule. Stop guessing what to study and start learning with confidence.",
            "cold_email": {
                "subject": "🎓 Let AI manage your study schedule",
                "body": "Hi there,\n\nWe know exam prep is stressful. That's why we built AI Study Planner.\n\nUpload your syllabus and get a balanced, daily study roadmap. Try it free today.\n\nBest,\nThe Team",
            },
            "social_posts": {
                "twitter": "Stop cramming! AI Study Planner converts your syllabus into a daily schedule. #StudyTips #StudentLife",
                "linkedin": "Students are overwhelmed. We built a tool to fix that.",
                "instagram": "Crush your exams with AI Study Planner! ✨📚",
            },
        }
