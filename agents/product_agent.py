"""
agents/product_agent.py - Product Agent for LaunchMind

RESPONSIBILITIES:
  1. Receive task from CEO Agent
  2. Use LLM to generate a full product specification:
     - Value proposition
     - User personas (name, role, pain_point)
     - Features (name, description, priority)
     - User stories
  3. Send the spec to ENGINEER and MARKETING
  4. Send confirmation to CEO
  5. Handle revision_request from CEO (regenerate with feedback)
"""

import json
import re
from message_bus import MessageBus, build_message
from utils.llm import send_prompt_json

AGENT_NAME = "PRODUCT"


class ProductAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    # ──────────────────────────────────────────
    #  Main processing tick
    # ──────────────────────────────────────────
    def process(self) -> None:
        """Called each tick by main.py. Drains and processes inbox messages."""
        messages = self.bus.fetch(AGENT_NAME)
        for msg in messages:
            self._handle_message(msg)

    # ──────────────────────────────────────────
    #  Message dispatcher
    # ──────────────────────────────────────────
    def _handle_message(self, msg: dict) -> None:
        mtype = msg["message_type"]

        if mtype == "task":
            print(f"\n[PRODUCT] 📬 Received task from {msg['from_agent']}")
            spec = self._generate_product_spec(msg["payload"])
            self._send_results(spec, parent_id=msg["message_id"])

        elif mtype == "revision_request":
            print(f"\n[PRODUCT] 🔁 Revision request from {msg['from_agent']}")
            feedback    = msg["payload"].get("feedback", "")
            original    = msg["payload"].get("original_result", {})
            revised     = self._revise_product_spec(original, feedback)
            self._send_results(revised, parent_id=msg["message_id"])

        else:
            print(f"[PRODUCT] ℹ️  Ignoring message type '{mtype}' from {msg['from_agent']}")

    # ──────────────────────────────────────────
    #  LLM: generate product spec
    # ──────────────────────────────────────────
    def _generate_product_spec(self, task_payload: dict) -> dict:
        idea  = task_payload.get("idea", "")
        task  = task_payload.get("task", {})
        extra = task_payload.get("instructions", "")

        print("[PRODUCT] 🧠 Generating product specification with LLM...")

        prompt = f"""You are a senior Product Manager at a startup accelerator.

Startup idea: "{idea}"

Your task: {task.get('objective', extra)}
Deliverables: {task.get('deliverables', [])}

Generate a comprehensive product specification as a VALID JSON object with NO markdown, code fences, or extra text:

{{
  "startup_name": "AI Study Planner",
  "value_proposition": "<1-2 sentences on what makes this product unique and valuable>",
  "personas": [
    {{
      "name": "<persona name>",
      "role": "<e.g. University Student>",
      "pain_point": "<specific study-related pain point>"
    }},
    {{
      "name": "<persona name>",
      "role": "<e.g. Exam Preparer>",
      "pain_point": "<specific pain point>"
    }},
    {{
      "name": "<persona name>",
      "role": "<e.g. Procrastinator>",
      "pain_point": "<specific pain point>"
    }}
  ],
  "features": [
    {{
      "name": "<feature name>",
      "description": "<clear 1-sentence description>",
      "priority": "high | medium | low"
    }}
  ],
  "user_stories": [
    "As a <role>, I want to <action> so that <benefit>.",
    "As a <role>, I want to <action> so that <benefit>.",
    "As a <role>, I want to <action> so that <benefit>.",
    "As a <role>, I want to <action> so that <benefit>."
  ],
  "monetization": "<describe the freemium or pricing model>",
  "tone": "<describe the product tone: e.g. empathetic, motivating, calm>"
}}

Include at least 5 features. Be specific to the study planning domain."""

        raw  = send_prompt_json(prompt, temperature=0.5)
        spec = self._parse_json(raw, self._default_spec())
        print("[PRODUCT] ✅ Product specification generated.")
        return spec

    def _revise_product_spec(self, original: dict, feedback: str) -> dict:
        """Use LLM to revise the spec based on CEO feedback."""
        print(f"[PRODUCT] 🧠 Revising spec based on feedback: '{feedback}'")

        prompt = f"""You are a Product Manager revising a product specification based on CEO feedback.

Original spec:
{json.dumps(original, indent=2)[:2000]}

CEO feedback: "{feedback}"

Produce an IMPROVED version addressing the feedback. Return ONLY valid JSON (same structure, no markdown):

{{
  "startup_name": "AI Study Planner",
  "value_proposition": "...",
  "personas": [...],
  "features": [...],
  "user_stories": [...],
  "monetization": "...",
  "tone": "..."
}}"""

        raw  = send_prompt_json(prompt, temperature=0.4)
        spec = self._parse_json(raw, original)
        print("[PRODUCT] ✅ Revised spec ready.")
        return spec

    # ──────────────────────────────────────────
    #  Send results to CEO, Engineer, Marketing
    # ──────────────────────────────────────────
    def _send_results(self, spec: dict, parent_id: str) -> None:
        # 1. Report back to CEO
        ceo_msg = build_message(
            from_agent=AGENT_NAME,
            to_agent="CEO",
            message_type="result",
            payload=spec,
            parent_message_id=parent_id,
        )
        self.bus.send(ceo_msg)
        print("[PRODUCT] 📤 Spec sent to CEO for evaluation.")

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
            print(f"[PRODUCT] ⚠️  JSON parse failed, using default. Raw: {raw[:200]}")
            return default

    @staticmethod
    def _default_spec() -> dict:
        return {
            "startup_name": "AI Study Planner",
            "value_proposition": (
                "AI Study Planner converts your syllabus and exam deadlines into "
                "a personalized daily study schedule, reducing academic stress."
            ),
            "personas": [
                {"name": "Alex", "role": "University Student", "pain_point": "Overwhelmed by multiple courses"},
                {"name": "Sam",  "role": "Exam Preparer",      "pain_point": "Doesn't know how to allocate study time"},
                {"name": "Jordan","role": "Procrastinator",    "pain_point": "Leaves everything to the last minute"},
            ],
            "features": [
                {"name": "Schedule Generator",    "description": "Creates a daily study plan from syllabus input.", "priority": "high"},
                {"name": "Deadline Tracker",      "description": "Monitors exam and assignment deadlines.",         "priority": "high"},
                {"name": "Workload Balancer",     "description": "Distributes study load evenly across days.",     "priority": "high"},
                {"name": "Daily Recommendations", "description": "Suggests what to study each day.",              "priority": "medium"},
                {"name": "Progress Tracker",      "description": "Tracks completed topics and milestones.",       "priority": "medium"},
            ],
            "user_stories": [
                "As a student, I want to input my syllabus so that I get a daily study plan.",
                "As a student, I want to set exam dates so that I never miss a deadline.",
                "As a procrastinator, I want daily reminders so that I stay on track.",
                "As an exam preparer, I want balanced study loads so that I avoid burnout.",
            ],
            "monetization": "Freemium — basic schedule is free; premium unlocks analytics and reminders.",
            "tone": "Empathetic, motivating, calm — focused on reducing stress.",
        }
