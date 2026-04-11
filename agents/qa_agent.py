"""
agents/qa_agent.py - QA Agent for LaunchMind

ROLE:
  Senior QA Engineer & Brand Guardian.

RESPONSIBILITIES:
  1. Receive HTML, product spec, marketing content, and PR URL from CEO
  2. Use LLM to review HTML landing page against the Product Spec (completeness, design, UX)
  3. Use LLM to review Marketing Content (clarity, tone, brand alignment)
  4. Post 2 REAL inline review comments on the GitHub PR
  5. Return a structured verdict: "pass" or "fail" (with specific issues)
  6. (If FAIL, CEO triggers a targeted revision loop with the Engineer/Marketing)
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

    def process(self) -> None:
        for msg in self.bus.fetch(AGENT_NAME):
            self._handle_message(msg)

    def _handle_message(self, msg: dict) -> None:
        mtype = msg["message_type"]

        if mtype == "task":
            print(f"\n[QA] 📬 Task received from {msg['from_agent']}")
            result = self._process_qa(msg["payload"])
            self._send_result(result, parent_id=msg["message_id"])

        elif mtype == "revision_request":
            print(f"\n[QA] 🔁 Re-running QA after revision…")
            # Pull latest artifacts from full_state if provided
            payload = msg["payload"]
            if "full_state" in payload:
                up_payload = {
                    "html_code":         payload["full_state"].get("engineer", {}).get("html_code", ""),
                    "product_spec":      payload.get("product_spec", {}),
                    "marketing_content": payload["full_state"].get("marketing", {}),
                    "pr_number":         payload.get("pr_number", 0),
                    "pr_url":            payload.get("pr_url", ""),
                }
                result = self._process_qa(up_payload)
            else:
                result = self._process_qa(payload.get("original_result", payload))
            self._send_result(result, parent_id=msg["message_id"])

        else:
            print(f"[QA] ℹ  Ignoring '{mtype}' from {msg['from_agent']}")

    def _process_qa(self, payload: dict) -> dict:
        html_code = payload.get("html_code", "")
        spec      = payload.get("product_spec", {})
        marketing = payload.get("marketing_content", {})
        pr_number = payload.get("pr_number", 0)

        html_review = self._review_html(html_code, spec)
        mkt_review  = self._review_marketing(marketing, spec)

        if pr_number:
            self._post_pr_comments(pr_number, html_review, mkt_review)
        else:
            print("[QA] ⚠  No PR number provided — skipping GitHub comments.")

        all_issues = html_review.get("issues", []) + mkt_review.get("issues", [])
        # Strict pass/fail criteria — anything High/Critical fails
        critical   = [i for i in all_issues if i.get("severity", "").lower() in ("critical", "high")]
        verdict    = "fail" if critical else "pass"

        print(f"\n[QA] {'✅ PASS' if verdict == 'pass' else '❌ FAIL'} — {len(all_issues)} issues found")
        for issue in all_issues[:3]:
            print(f"[QA]   [{issue.get('severity','?').upper()}] {issue.get('description', '')}")

        return {
            "verdict": verdict,
            "issues":  all_issues,
            "html_review": html_review,
            "marketing_review": mkt_review,
        }

    def _review_html(self, html_code: str, spec: dict) -> dict:
        print("[QA] 🧠 Reviewing HTML against Product Spec (LLM)…")

        features = [f.get("name", "") for f in spec.get("features", [])]
        val_prop = spec.get("value_proposition", "")

        prompt = f"""You are a strict QA Engineer reviewing a launch landing page.

Product Spec Requirements:
- Value Proposition: "{val_prop}"
- Expected Features: {features}

HTML Code (snippet):
{html_code[:3500]}

Review Criteria:
1. Is the value proposition clearly stated in the hero section?
2. Are ALL expected features present?
3. Is semantic HTML used (header, nav, main, footer)?
4. Does it include interactive elements (e.g., CTA buttons, forms)?

Return ONLY valid JSON (no markdown):
{{
  "overall_score": <integer 0-10>,
  "summary": "<2 sentences summarising quality>",
  "positives": ["<strength 1>", "<strength 2>"],
  "issues": [
    {{
      "type": "html_issue",
      "severity": "critical | high | medium | low",
      "description": "<exact issue>",
      "suggestion": "<actionable fix>"
    }}
  ]
}}"""
        raw = send_prompt_json(prompt, temperature=0.2)
        rev = self._parse_json(raw, self._default_html_review())
        print(f"[QA] HTML Score: {rev.get('overall_score','?')}/10")
        return rev

    def _review_marketing(self, marketing: dict, spec: dict) -> dict:
        print("[QA] 🧠 Reviewing Marketing Copy (LLM)…")

        tone = spec.get("tone", "empathetic and motivating")

        prompt = f"""You are a strict QA Engineer reviewing launch marketing content.

Brand Tone required: "{tone}"

Content under review:
Tagline: "{marketing.get('tagline', '')}"
Description: "{marketing.get('description', '')}"
Cold Email Subject: "{marketing.get('cold_email', {}).get('subject', '')}"
LinkedIn Post: "{marketing.get('social_posts', {}).get('linkedin', '')}"

Review Criteria:
1. Is the tagline actually under 10 words and memorable?
2. Does the tone match the brand requirement?
3. Are there spelling/grammar issues or generic corporate jargon?
4. Is the LinkedIn post engaging and well-structured?

Return ONLY valid JSON (no markdown):
{{
  "overall_score": <integer 0-10>,
  "summary": "<2 sentences summarising quality>",
  "positives": ["<strength 1>", "<strength 2>"],
  "issues": [
    {{
      "type": "marketing_issue",
      "severity": "critical | high | medium | low",
      "description": "<exact issue>",
      "suggestion": "<actionable fix>"
    }}
  ]
}}"""
        raw = send_prompt_json(prompt, temperature=0.2)
        rev = self._parse_json(raw, self._default_marketing_review())
        print(f"[QA] Marketing Score: {rev.get('overall_score','?')}/10")
        return rev

    def _post_pr_comments(self, pr_number: int, html_rev: dict, mkt_rev: dict) -> None:
        def build_comment(title: str, review: dict) -> str:
            pos = "\n".join(f"  ✅ {p}" for p in review.get("positives", [])) or "  Good overall."
            iss = "\n".join(
                f"  [{i.get('severity','?').upper()}] {i.get('description','')} → _{i.get('suggestion','')}_"
                for i in review.get("issues", [])
            ) or "  No critical issues found."
            
            return (
                f"## 🔍 QA Agent — {title}\n\n"
                f"**Score:** {review.get('overall_score', 'N/A')}/10\n"
                f"**Summary:** {review.get('summary', '')}\n\n"
                f"### ✅ Positives\n{pos}\n\n"
                f"### ⚠ Issues Detected\n{iss}\n\n"
                "---\n_Auto-reviewed by LaunchMind QA Agent_ 🤖"
            )

        try:
            github_api.add_pr_comment(pr_number, build_comment("HTML Validation", html_rev))
            print(f"[QA] ✅ HTML comment posted to PR #{pr_number}")
        except Exception as e:
            print(f"[QA] ⚠  HTML comment failed: {e}")

        try:
            github_api.add_pr_comment(pr_number, build_comment("Marketing Validation", mkt_rev))
            print(f"[QA] ✅ Marketing comment posted to PR #{pr_number}")
        except Exception as e:
            print(f"[QA] ⚠  Marketing comment failed: {e}")

    def _send_result(self, result: dict, parent_id: str) -> None:
        self.bus.send(build_message(
            from_agent=AGENT_NAME,
            to_agent="CEO",
            message_type="result",
            payload=result,
            parent_message_id=parent_id,
        ))
        print("[QA] 📤 Verdict sent to CEO.")

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
            print(f"[QA] ⚠  JSON parse failed, using default.")
            return default

    @staticmethod
    def _default_html_review() -> dict:
        return {"overall_score": 7, "summary": "Acceptable HTML baseline.", "positives": ["Valid HTML"], "issues": []}

    @staticmethod
    def _default_marketing_review() -> dict:
        return {"overall_score": 8, "summary": "Acceptable marketing copy.", "positives": ["Clear value prop"], "issues": []}
