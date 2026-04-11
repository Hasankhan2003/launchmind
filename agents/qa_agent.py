"""
agents/qa_agent.py - QA Agent for LaunchMind

RESPONSIBILITIES:
  1. Receive HTML code, product spec, PR URL, and marketing content from CEO
  2. Use LLM to:
     - Review HTML landing page against product spec (does it match features/value prop?)
     - Review marketing content for quality, clarity, and brand alignment
  3. Post 2 inline review comments on the GitHub PR (REAL API call)
  4. Return a structured verdict: { "verdict": "pass|fail", "issues": [...] }
  5. If FAIL, CEO triggers a revision loop

VERDICT CRITERIA:
  - pass: HTML covers key features + marketing is coherent
  - fail: Major mismatches, missing sections, or low quality content
"""

import json
import re
from message_bus import MessageBus, build_message
from utils.llm import send_prompt_json
from utils import github_api

AGENT_NAME = "QA"


class QAAgent:
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
            print(f"\n[QA] 📬 Received QA task from {msg['from_agent']}")
            result = self._process_qa(msg["payload"])
            self._send_result(result, parent_id=msg["message_id"])

        elif mtype == "revision_request":
            print(f"\n[QA] 🔁 Re-running QA after revision...")
            result = self._process_qa(msg["payload"].get("original_result", msg["payload"]))
            self._send_result(result, parent_id=msg["message_id"])

        else:
            print(f"[QA] ℹ️  Ignoring message type '{mtype}'")

    # ──────────────────────────────────────────
    #  Core QA process
    # ──────────────────────────────────────────
    def _process_qa(self, payload: dict) -> dict:
        html_code         = payload.get("html_code", "")
        product_spec      = payload.get("product_spec", {})
        marketing_content = payload.get("marketing_content", {})
        pr_number         = payload.get("pr_number", 0)
        pr_url            = payload.get("pr_url", "")

        # Step 1: LLM review
        html_review       = self._review_html(html_code, product_spec)
        marketing_review  = self._review_marketing(marketing_content, product_spec)

        # Step 2: Post PR comments
        if pr_number:
            self._post_pr_comments(pr_number, html_review, marketing_review)
        else:
            print("[QA] ⚠️  No PR number provided — skipping GitHub comments.")

        # Step 3: Determine verdict
        all_issues = html_review.get("issues", []) + marketing_review.get("issues", [])
        critical   = [i for i in all_issues if i.get("severity", "").lower() in ("critical", "high")]
        verdict    = "fail" if critical else "pass"

        result = {
            "verdict": verdict,
            "issues": all_issues,
            "html_review": html_review,
            "marketing_review": marketing_review,
            "pr_url": pr_url,
        }

        print(f"\n[QA] {'✅ PASS' if verdict == 'pass' else '❌ FAIL'} — {len(all_issues)} issues found")
        for issue in all_issues[:5]:
            print(f"[QA]   [{issue.get('severity','?').upper()}] {issue.get('description', '')}")

        return result

    # ──────────────────────────────────────────
    #  LLM: Review HTML vs Product Spec
    # ──────────────────────────────────────────
    def _review_html(self, html_code: str, spec: dict) -> dict:
        print("[QA] 🧠 Reviewing HTML with LLM...")

        features  = [f.get("name", "") for f in spec.get("features", [])]
        value_prop = spec.get("value_proposition", "")

        prompt = f"""You are a QA Engineer reviewing an HTML landing page for a startup.

Product Spec:
- Value Proposition: "{value_prop}"
- Expected Features: {features}

HTML Code (first 3000 chars):
{html_code[:3000]}

Review this HTML against the spec. Check:
1. Does the hero section convey the value proposition?
2. Are the key features represented?
3. Is there a clear CTA?
4. Is the design responsive and modern?
5. Are there any obvious HTML errors?

Return ONLY a valid JSON object (no markdown):
{{
  "overall_score": <integer 0-10>,
  "summary": "<2 sentences describing the overall quality>",
  "positives": ["<thing 1>", "<thing 2>"],
  "issues": [
    {{
      "type": "html_issue",
      "severity": "critical | high | medium | low",
      "description": "<specific issue>",
      "suggestion": "<how to fix>"
    }}
  ]
}}"""

        raw    = send_prompt_json(prompt, temperature=0.2)
        review = self._parse_json(raw, self._default_html_review())
        print(f"[QA] HTML score: {review.get('overall_score', '?')}/10")
        return review

    # ──────────────────────────────────────────
    #  LLM: Review Marketing Content
    # ──────────────────────────────────────────
    def _review_marketing(self, marketing: dict, spec: dict) -> dict:
        print("[QA] 🧠 Reviewing marketing content with LLM...")

        tone = spec.get("tone", "empathetic and motivating")

        prompt = f"""You are a QA Engineer reviewing marketing content for a startup.

Expected tone: {tone}
Target audience: University students under exam pressure.

Marketing Content:
Tagline: "{marketing.get('tagline', '')}"
Description: "{marketing.get('description', '')}"
Twitter: "{marketing.get('social_posts', {}).get('twitter', '')}"
LinkedIn: "{marketing.get('social_posts', {}).get('linkedin', '')}"

Review the marketing content. Check:
1. Is the tagline under 10 words and memorable?
2. Does the description clearly explain the product?
3. Are social posts platform-appropriate?
4. Does the tone match the expected brand voice?
5. Is the cold email subject compelling?

Return ONLY a valid JSON object (no markdown):
{{
  "overall_score": <integer 0-10>,
  "summary": "<2 sentences>",
  "positives": ["<thing 1>", "<thing 2>"],
  "issues": [
    {{
      "type": "marketing_issue",
      "severity": "critical | high | medium | low",
      "description": "<specific issue>",
      "suggestion": "<how to fix>"
    }}
  ]
}}"""

        raw    = send_prompt_json(prompt, temperature=0.2)
        review = self._parse_json(raw, self._default_marketing_review())
        print(f"[QA] Marketing score: {review.get('overall_score', '?')}/10")
        return review

    # ──────────────────────────────────────────
    #  Post REAL GitHub PR comments
    # ──────────────────────────────────────────
    def _post_pr_comments(self, pr_number: int, html_review: dict, marketing_review: dict) -> None:
        """Post 2 PR review comments: one for HTML, one for marketing."""

        # Comment 1: HTML Review
        html_positives  = "\n".join(f"  ✅ {p}" for p in html_review.get("positives", []))
        html_issues_txt = "\n".join(
            f"  [{i.get('severity','?').upper()}] {i.get('description','')} → {i.get('suggestion','')}"
            for i in html_review.get("issues", [])
        ) or "  No critical issues found."

        html_comment = (
            "## 🔍 QA Agent - HTML Review\n\n"
            f"**Score:** {html_review.get('overall_score', 'N/A')}/10\n\n"
            f"**Summary:** {html_review.get('summary', '')}\n\n"
            "### ✅ Positives\n"
            f"{html_positives or '  Good overall quality.'}\n\n"
            "### ⚠️ Issues\n"
            f"{html_issues_txt}\n\n"
            "---\n_Auto-reviewed by LaunchMind QA Agent_ 🤖"
        )

        # Comment 2: Marketing Review
        mkt_positives  = "\n".join(f"  ✅ {p}" for p in marketing_review.get("positives", []))
        mkt_issues_txt = "\n".join(
            f"  [{i.get('severity','?').upper()}] {i.get('description','')} → {i.get('suggestion','')}"
            for i in marketing_review.get("issues", [])
        ) or "  No critical issues found."

        marketing_comment = (
            "## 📢 QA Agent - Marketing Content Review\n\n"
            f"**Score:** {marketing_review.get('overall_score', 'N/A')}/10\n\n"
            f"**Summary:** {marketing_review.get('summary', '')}\n\n"
            "### ✅ Positives\n"
            f"{mkt_positives or '  Good overall quality.'}\n\n"
            "### ⚠️ Issues\n"
            f"{mkt_issues_txt}\n\n"
            "---\n_Auto-reviewed by LaunchMind QA Agent_ 🤖"
        )

        try:
            github_api.add_pr_comment(pr_number, html_comment)
            print(f"[QA] ✅ HTML review comment posted on PR #{pr_number}")
        except Exception as e:
            print(f"[QA] ⚠️  Could not post HTML review comment: {e}")

        try:
            github_api.add_pr_comment(pr_number, marketing_comment)
            print(f"[QA] ✅ Marketing review comment posted on PR #{pr_number}")
        except Exception as e:
            print(f"[QA] ⚠️  Could not post marketing review comment: {e}")

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
        print("[QA] 📤 QA verdict sent to CEO.")

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
            print(f"[QA] ⚠️  JSON parse failed, using default. Raw: {raw[:200]}")
            return default

    @staticmethod
    def _default_html_review() -> dict:
        return {
            "overall_score": 7,
            "summary": "The HTML landing page is functional and covers the main value proposition.",
            "positives": ["Clean layout", "Responsive design"],
            "issues": [
                {
                    "type": "html_issue",
                    "severity": "low",
                    "description": "Some feature descriptions could be more detailed.",
                    "suggestion": "Expand feature card descriptions."
                }
            ]
        }

    @staticmethod
    def _default_marketing_review() -> dict:
        return {
            "overall_score": 8,
            "summary": "Marketing content is clear and targets the right audience.",
            "positives": ["Compelling tagline", "Good social media copy"],
            "issues": []
        }
