"""
agents/product_agent.py - Product Agent for LaunchMind

ROLE:
  Senior Product Manager at a startup accelerator.

RESPONSIBILITIES:
  1. Receive a task from the CEO Agent via the MessageBus
  2. Use the LLM to generate a complete, investor-ready product specification:
       - value_proposition  (1-2 sharp sentences)
       - personas           (3 named personas with role + pain_point)
       - features           (≥5 with name, description, priority)
       - user_stories       (≥4 in "As a… I want… so that…" format)
       - monetization       (pricing model)
       - tone               (brand voice descriptor)
  3. Send the spec back to the CEO for quality evaluation
  4. Handle revision_request: incorporate CEO feedback and resubmit
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
        """Called each tick by main.py. Drains and processes inbox."""
        for msg in self.bus.fetch(AGENT_NAME):
            self._handle_message(msg)

    # ──────────────────────────────────────────
    #  Message dispatcher
    # ──────────────────────────────────────────
    def _handle_message(self, msg: dict) -> None:
        mtype = msg["message_type"]

        if mtype == "task":
            print(f"\n[PRODUCT] 📬 Task received from {msg['from_agent']}")
            spec = self._generate_product_spec(msg["payload"])
            self._send_result(spec, parent_id=msg["message_id"])

        elif mtype == "revision_request":
            print(f"\n[PRODUCT] 🔁 Revision request from {msg['from_agent']}")
            feedback = msg["payload"].get("feedback", "")
            original = msg["payload"].get("original_result", {})
            score    = msg["payload"].get("quality_score", 0)
            revised  = self._revise_product_spec(original, feedback, score)
            self._send_result(revised, parent_id=msg["message_id"])

        else:
            print(f"[PRODUCT] ℹ  Ignoring '{mtype}' from {msg['from_agent']}")

    # ──────────────────────────────────────────
    #  LLM: generate product specification
    # ──────────────────────────────────────────
    def _generate_product_spec(self, task_payload: dict) -> dict:
        idea  = task_payload.get("idea", "")
        task  = task_payload.get("task", {})

        print("[PRODUCT] 🧠 Generating product specification (LLM)…")

        value_prop_hint = task.get("context", idea)
        deliverables    = task.get("deliverables", [])

        prompt = f"""You are a Senior Product Manager at a world-class startup accelerator with deep experience in EdTech products.

You have been assigned to produce a complete product specification for the following startup:

Startup Idea: "{idea}"
Strategic Context: {value_prop_hint}
Required Deliverables: {deliverables}

Your output will be reviewed by the CEO and used directly by Engineering and Marketing teams. Quality matters.

Return a VALID JSON object with NO markdown, NO code fences, NO extra text — raw JSON only:

{{
  "startup_name": "AI Study Planner",
  "value_proposition": "<1-2 sentences. What specific problem does this solve? Why is the solution uniquely valuable? Be concrete, not generic.>",
  "personas": [
    {{
      "name": "<persona first name>",
      "role": "<e.g. 'Second-Year Engineering Student'>",
      "pain_point": "<very specific study-related struggle this person faces daily>"
    }},
    {{
      "name": "<persona first name>",
      "role": "<different academic profile>",
      "pain_point": "<specific pain point distinct from persona 1>"
    }},
    {{
      "name": "<persona first name>",
      "role": "<e.g. 'Part-Time Working Student'>",
      "pain_point": "<specific time-management pain point>"
    }}
  ],
  "features": [
    {{
      "name": "<feature name>",
      "description": "<exactly one sentence: what it does and why it matters>",
      "priority": "high"
    }},
    {{
      "name": "<feature name>",
      "description": "<one sentence>",
      "priority": "high"
    }},
    {{
      "name": "<feature name>",
      "description": "<one sentence>",
      "priority": "medium"
    }},
    {{
      "name": "<feature name>",
      "description": "<one sentence>",
      "priority": "medium"
    }},
    {{
      "name": "<feature name>",
      "description": "<one sentence>",
      "priority": "low"
    }}
  ],
  "user_stories": [
    "As a <role>, I want to <specific action> so that <measurable benefit>.",
    "As a <role>, I want to <specific action> so that <measurable benefit>.",
    "As a <role>, I want to <specific action> so that <measurable benefit>.",
    "As a <role>, I want to <specific action> so that <measurable benefit>."
  ],
  "monetization": "<describe a concrete freemium or tiered pricing model with specific price points>",
  "tone": "<describe brand voice in 2-3 adjectives with brief explanation — e.g. 'Empathetic and direct: we speak to students like a knowledgeable friend, not a corporation'>"
}}

Rules:
- Personas must have DIFFERENT roles and DIFFERENT pain points
- Features must be specific to study planning (not generic SaaS features)
- User stories must follow exact format: "As a..., I want to..., so that..."
- Include at least 5 features (you may add more)
- Value proposition must mention both the problem AND the mechanism of solution"""

        raw  = send_prompt_json(prompt, temperature=0.5)
        spec = self._parse_json(raw, self._default_spec())
        print(f"[PRODUCT] ✅ Spec generated — {len(spec.get('features', []))} features, "
              f"{len(spec.get('personas', []))} personas, "
              f"{len(spec.get('user_stories', []))} user stories.")
        return spec

    def _revise_product_spec(self, original: dict, feedback: str, score: int) -> dict:
        """Use LLM to produce an improved spec addressing the CEO's specific feedback."""
        print(f"[PRODUCT] 🧠 Revising spec (CEO score was {score}/10) — addressing: '{feedback}'")

        prompt = f"""You are a Senior Product Manager revising a product specification after CEO review.

CEO Feedback (score {score}/10):
"{feedback}"

Current Specification:
{json.dumps(original, indent=2)[:2500]}

Your task: Produce a SIGNIFICANTLY IMPROVED version that directly addresses every point in the CEO feedback.
Do NOT just make cosmetic changes — make substantive improvements.

Return ONLY valid JSON (same structure, no markdown, no explanation):

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
    #  Send result to CEO
    # ──────────────────────────────────────────
    def _send_result(self, spec: dict, parent_id: str) -> None:
        self.bus.send(build_message(
            from_agent=AGENT_NAME,
            to_agent="CEO",
            message_type="result",
            payload=spec,
            parent_message_id=parent_id,
        ))
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
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except Exception:
                    pass
            print(f"[PRODUCT] ⚠  JSON parse failed, using default. Raw: {raw[:200]}")
            return default

    @staticmethod
    def _default_spec() -> dict:
        return {
            "startup_name": "AI Study Planner",
            "value_proposition": (
                "AI Study Planner eliminates exam-time panic by converting any university "
                "syllabus and set of deadlines into a balanced, personalized daily study schedule "
                "— so students always know exactly what to study and when."
            ),
            "personas": [
                {
                    "name": "Alex",
                    "role": "Second-Year Engineering Student",
                    "pain_point": "Juggles 6 courses with overlapping deadlines and has no system to prioritize study time."
                },
                {
                    "name": "Sara",
                    "role": "Pre-Med High Achiever",
                    "pain_point": "Needs maximum retention across dense material but wastes hours deciding what to study next."
                },
                {
                    "name": "Jordan",
                    "role": "Part-Time Working Student",
                    "pain_point": "Has only 3-4 hours per day to study and needs every minute to count toward exam readiness."
                },
            ],
            "features": [
                {"name": "Syllabus Import", "description": "Upload or paste your course syllabus; AI extracts topics and assigns weights automatically.", "priority": "high"},
                {"name": "Smart Schedule Generator", "description": "Creates a daily study plan that balances all courses based on exam proximity and topic complexity.", "priority": "high"},
                {"name": "Deadline Tracker", "description": "Visual countdown dashboard for every exam and assignment due date.", "priority": "high"},
                {"name": "Daily Focus Mode", "description": "Shows only today's study tasks to eliminate decision fatigue and boost consistency.", "priority": "medium"},
                {"name": "Progress Analytics", "description": "Tracks completed topics per subject and shows a readiness score so students know where to focus.", "priority": "medium"},
            ],
            "user_stories": [
                "As an overwhelmed student, I want to upload my syllabus so that I receive a structured daily study plan without any manual planning.",
                "As a working student, I want to set my available hours per day so that the AI builds a realistic schedule I can actually follow.",
                "As an exam preparer, I want to see a readiness score per subject so that I know exactly where to focus my remaining time.",
                "As a procrastinator, I want daily push notifications so that I start studying before it is too late to prepare properly.",
            ],
            "monetization": "Freemium — core scheduling is free forever; Premium ($9.99/month) adds calendar sync, AI topic summaries, and study group features.",
            "tone": "Empathetic and direct — we speak to students like a knowledgeable friend who has been through exam stress, not a corporate productivity tool.",
        }
