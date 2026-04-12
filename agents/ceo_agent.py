"""
agents/ceo_agent.py - CEO Agent for LaunchMind

ROLE:
  The CEO is the strategic orchestrator of the entire LaunchMind pipeline.
  It uses an LLM for every decision — no hardcoded routing.

RESPONSIBILITIES:
  1. Accept the startup idea as the system entry point
  2. Use LLM to decompose the idea into precise, role-specific tasks
  3. Dispatch tasks to ProductAgent, EngineerAgent, MarketingAgent via MessageBus
  4. Evaluate every result with an LLM quality rubric (0–10 scale)
  5. Enforce a FEEDBACK LOOP: score < threshold → send revision_request → re-evaluate
  6. Coordinate QA review once Engineer + Marketing are accepted
  7. When QA passes, send a final Slack launch announcement and mark complete

FEEDBACK LOOP:
  • CEO sends task → agent responds → CEO calls LLM to score (0-10)
  • Score < QUALITY_THRESHOLD → revision_request with specific feedback
  • After MAX_REVISIONS_PER_AGENT rounds (or satisfactory score) → accept & proceed
  • QA can also trigger targeted revision_requests for HTML and/or marketing
"""

import json
import re
import time
from message_bus import MessageBus, build_message
from utils.llm import send_prompt_json
from utils.slack_api import send_block_message, build_launch_blocks
from config import (
    QUALITY_THRESHOLD,
    MAX_REVISIONS_PER_AGENT,
    DEFAULT_STARTUP_IDEA,
)

AGENT_NAME = "CEO"


class CEOAgent:
    def __init__(self, bus: MessageBus, idea: str | None = None):
        self.bus  = bus
        self.idea = idea or DEFAULT_STARTUP_IDEA

        # Which agents we are currently waiting on (>0 = pending)
        self._waiting_for: dict[str, int] = {
            "PRODUCT":   0,
            "ENGINEER":  0,
            "MARKETING": 0,
            "QA":        0,
        }
        # Accepted results per agent
        self._results: dict[str, dict] = {}

        # QA-triggered revision tracking (fire only once per run)
        self._qa_revision_dispatched: bool = False

        # CEO-driven revision counts (per agent)
        self._revision_counts: dict[str, int] = {
            "PRODUCT":   0,
            "ENGINEER":  0,
            "MARKETING": 0,
            "QA":        0,
        }

        self._project_complete = False
        self._quality_threshold = QUALITY_THRESHOLD
        self._max_revisions     = MAX_REVISIONS_PER_AGENT

    # ──────────────────────────────────────────
    #  Public entry point
    # ──────────────────────────────────────────
    def kickoff(self) -> None:
        """Called once by main.py to bootstrap the entire MAS pipeline."""
        print(f"\n{'='*60}")
        print(f"[CEO] 🚀 Startup idea received:")
        print(f"[CEO]    {self.idea}")
        print(f"{'='*60}\n")

        tasks = self._decompose_idea()
        self._dispatch_product_task(tasks)

    # ──────────────────────────────────────────
    #  Main tick (called each loop iteration)
    # ──────────────────────────────────────────
    def process(self) -> bool:
        """Drain inbox and process all pending messages. Returns True when done."""
        if self._project_complete:
            return True

        for msg in self.bus.fetch(AGENT_NAME):
            mtype      = msg["message_type"]
            from_agent = msg["from_agent"]
            payload    = msg["payload"]

            print(f"[CEO] 📬 {mtype.upper()} from {from_agent}")

            if mtype == "result":
                self._handle_result(from_agent, payload, msg["message_id"])
            elif mtype == "confirmation":
                print(f"[CEO] ✅ Confirmation from {from_agent}: {payload.get('status', 'ok')}")

        return self._project_complete

    # ──────────────────────────────────────────
    #  LLM: strategic task decomposition
    # ──────────────────────────────────────────
    def _decompose_idea(self) -> dict:
        """
        Use the LLM to break the startup idea into three structured, role-specific tasks.
        This is the CEO's first real act of intelligence — not a template, but genuine reasoning.
        """
        print("[CEO] 🧠 Decomposing startup idea into agent tasks (LLM)…")

        prompt = f"""You are the CEO of a top-tier startup accelerator. You have just received a new startup idea from a founder:

"{self.idea}"

Your job is to act as a strategic leader and decompose this idea into three precisely-scoped tasks — one per specialist agent on your team. Each task must be actionable, domain-specific, and directly tied to this product.

Return a VALID JSON object with EXACTLY this structure (no markdown, no code fences, raw JSON only):

{{
  "product_task": {{
    "objective": "<One sharp sentence: what the Product Manager must produce>",
    "context": "<2-3 sentences on the target user, their core pain, and what makes this product uniquely valuable>",
    "deliverables": ["value_proposition", "user_personas (3)", "features (min 5 with priority)", "user_stories (min 4)"]
  }},
  "engineer_task": {{
    "objective": "<One sharp sentence: what the Engineer must build>",
    "context": "<2-3 sentences on the landing page purpose, design direction, and GitHub deliverables>",
    "deliverables": ["complete HTML landing page", "GitHub Issue", "GitHub branch", "committed index.html", "Pull Request"]
  }},
  "marketing_task": {{
    "objective": "<One sharp sentence: what the Marketing strategist must create>",
    "context": "<2-3 sentences on the target audience, tone, and campaign goals>",
    "deliverables": ["memorable tagline (max 10 words)", "product description (2-3 sentences)", "cold email with subject + body", "3 platform-specific social posts"]
  }}
}}

Be specific to the study planning domain. Reference students, syllabus, exams, and scheduling where relevant."""

        raw   = send_prompt_json(prompt)
        tasks = self._parse_json(raw, default={
            "product_task": {
                "objective": "Produce a comprehensive product specification for AI Study Planner",
                "context": self.idea,
                "deliverables": ["value_proposition", "personas", "features", "user_stories"],
            },
            "engineer_task": {
                "objective": "Build a modern HTML landing page and set up GitHub infrastructure",
                "context": self.idea,
                "deliverables": ["index.html", "GitHub Issue", "GitHub PR"],
            },
            "marketing_task": {
                "objective": "Create all launch marketing content for AI Study Planner",
                "context": self.idea,
                "deliverables": ["tagline", "description", "cold_email", "social_posts"],
            },
        })

        print(f"[CEO] ✅ Decomposition complete: {list(tasks.keys())}")
        return tasks

    # ──────────────────────────────────────────
    #  Task dispatch
    # ──────────────────────────────────────────
    def _dispatch_product_task(self, tasks: dict) -> None:
        msg = build_message(
            from_agent=AGENT_NAME,
            to_agent="PRODUCT",
            message_type="task",
            payload={
                "idea":  self.idea,
                "task":  tasks.get("product_task", {}),
                "instructions": (
                    "Generate a complete, investment-ready product specification "
                    "as structured JSON for the AI Study Planner startup."
                ),
            },
        )
        self.bus.send(msg)
        self._waiting_for["PRODUCT"] += 1
        print("[CEO] 📤 Task dispatched → PRODUCT")
        print("[CEO] ⏳ Waiting for PRODUCT spec before dispatching ENGINEER & MARKETING…")

    def _dispatch_engineer_and_marketing(self, product_spec: dict) -> None:
        """Dispatch to Engineer and Marketing agents, passing the accepted product spec."""

        # Engineer
        self.bus.send(build_message(
            from_agent=AGENT_NAME,
            to_agent="ENGINEER",
            message_type="task",
            payload={
                "idea":         self.idea,
                "product_spec": product_spec,
                "instructions": (
                    "Generate a complete, visually stunning single-file HTML landing page. "
                    "Then: create a GitHub branch, commit index.html, open a GitHub Issue, "
                    "and open a Pull Request. Return the PR URL, Issue URL, and HTML code."
                ),
            },
        ))
        self._waiting_for["ENGINEER"] += 1

        # Marketing
        self.bus.send(build_message(
            from_agent=AGENT_NAME,
            to_agent="MARKETING",
            message_type="task",
            payload={
                "idea":         self.idea,
                "product_spec": product_spec,
                "instructions": (
                    "Generate a tagline, product description, cold email, and 3 social posts. "
                    "Send a real email via SendGrid and post a Slack Block Kit message. "
                    "Return all content as structured JSON."
                ),
            },
        ))
        self._waiting_for["MARKETING"] += 1

        print("[CEO] 📤 Tasks dispatched → ENGINEER & MARKETING (running in parallel)")

    def _dispatch_qa(self) -> None:
        """Send QA task with all produced artifacts."""
        eng = self._results.get("ENGINEER", {})
        mkt = self._results.get("MARKETING", {})

        self.bus.send(build_message(
            from_agent=AGENT_NAME,
            to_agent="QA",
            message_type="task",
            payload={
                "product_spec":      self._results.get("PRODUCT", {}),
                "html_code":         eng.get("html_code", ""),
                "pr_url":            eng.get("pr_url", ""),
                "pr_number":         eng.get("pr_number", 0),
                "marketing_content": mkt,
                "full_state":        {"engineer": eng, "marketing": mkt},
                "instructions": (
                    "Review the HTML landing page against the product spec for completeness. "
                    "Review the marketing content for quality, tone, and brand alignment. "
                    "Post 2 PR review comments on GitHub. "
                    "Return a structured JSON verdict: pass or fail with specific issues."
                ),
            },
        ))
        self._waiting_for["QA"] += 1
        print("[CEO] 📤 Task dispatched → QA")

    # ──────────────────────────────────────────
    #  Handle incoming results (with feedback loop)
    # ──────────────────────────────────────────
    def _handle_result(self, from_agent: str, payload: dict, parent_id: str) -> None:
        score, feedback = self._evaluate_result(from_agent, payload)
        rev_count       = self._revision_counts.get(from_agent, 0)

        print(f"[CEO] 📊 Quality score for {from_agent}: {score}/10")
        print(f"[CEO]    Feedback: {feedback}")

        # ── DECISION: Revise or Accept? ──
        if score < self._quality_threshold:
            if rev_count < self._max_revisions:
                # ── REQUEST REVISION (within max rounds) ──
                self._revision_counts[from_agent] = rev_count + 1
                new_round = self._revision_counts[from_agent]
                print(
                    f"[CEO] 🔁 Score {score} < threshold {self._quality_threshold}. "
                    f"Sending revision_request to {from_agent} "
                    f"(round {new_round}/{self._max_revisions})"
                )
                self.bus.send(build_message(
                    from_agent=AGENT_NAME,
                    to_agent=from_agent,
                    message_type="revision_request",
                    payload={
                        "original_result": payload,
                        "feedback":        feedback,
                        "quality_score":   score,
                        "instructions": (
                            f"Your output scored {score}/10. CEO feedback: {feedback} "
                            f"Please address this feedback and resubmit an improved result."
                        ),
                    },
                    parent_message_id=parent_id,
                ))
            else:
                # ── MAX REVISIONS REACHED: Accept as-is ──
                print(
                    f"[CEO] ⚠  Max revisions reached for {from_agent} "
                    f"({rev_count}/{self._max_revisions}). Accepting output despite score {score}/10."
                )
                self._results[from_agent]    = payload
                self._waiting_for[from_agent] = 0

                self.bus.send(build_message(
                    from_agent=AGENT_NAME,
                    to_agent=from_agent,
                    message_type="confirmation",
                    payload={"status": "accepted", "score": score},
                ))

                self._advance_pipeline()
        else:
            # ── SCORE ACCEPTABLE: Accept result ──
            print(f"[CEO] ✅ Result from {from_agent} accepted (score {score}/10).")

            self._results[from_agent]    = payload
            self._waiting_for[from_agent] = 0

            self.bus.send(build_message(
                from_agent=AGENT_NAME,
                to_agent=from_agent,
                message_type="confirmation",
                payload={"status": "accepted", "score": score},
            ))

            self._advance_pipeline()

    # ──────────────────────────────────────────
    #  Pipeline progression
    # ──────────────────────────────────────────
    def _advance_pipeline(self) -> None:
        """Decide what to do next based on accepted results."""

        # Phase 1 → 2: PRODUCT accepted, dispatch ENGINEER + MARKETING
        if (
            "PRODUCT" in self._results
            and "ENGINEER" not in self._results
            and "MARKETING" not in self._results
            and self._waiting_for["ENGINEER"] == 0
            and self._waiting_for["MARKETING"] == 0
        ):
            print("[CEO] 🔄 PRODUCT accepted — dispatching ENGINEER & MARKETING…")
            self._dispatch_engineer_and_marketing(self._results["PRODUCT"])
            return

        # Phase 2 → 3: Both ENGINEER + MARKETING accepted, dispatch QA
        if (
            "ENGINEER" in self._results
            and "MARKETING" in self._results
            and "QA" not in self._results
            and self._waiting_for["QA"] == 0
        ):
            print("[CEO] 🔄 ENGINEER & MARKETING accepted — dispatching QA…")
            self._dispatch_qa()
            return

        # Phase 3 → 4: QA result accepted → finalise
        if "QA" in self._results:
            self._finalise()

    # ──────────────────────────────────────────
    #  Finalise: QA-driven revision + launch
    # ──────────────────────────────────────────
    def _finalise(self) -> None:
        """
        After QA:
          1. If issues exist and we haven't looped yet → send targeted revision_requests
          2. Otherwise → post final Slack announcement and mark complete
        """
        # Hold if any revised outputs are still pending
        if self._waiting_for["ENGINEER"] > 0 or self._waiting_for["MARKETING"] > 0:
            print("[CEO] ⏳ Holding finalisation — awaiting revised outputs…")
            return

        qa_result = self._results.get("QA", {})
        verdict   = qa_result.get("verdict", "unknown")
        issues    = qa_result.get("issues", [])

        print(f"\n[CEO] 🎯 QA Verdict: {verdict.upper()} | Issues: {len(issues)}")

        # ── QA FEEDBACK LOOP (fires once) ────────────────────────────────
        html_issues = [i for i in issues if i.get("type") == "html_issue"]
        mkt_issues  = [i for i in issues if i.get("type") == "marketing_issue"]

        if not self._qa_revision_dispatched and (html_issues or mkt_issues):
            self._qa_revision_dispatched = True
            print(f"[CEO] 🔁 QA found issues — triggering revision loop ({len(issues)} issues)")
            dispatched = False

            if html_issues:
                fb = " | ".join(
                    f"{i.get('severity','?').upper()}: {i.get('description','')}"
                    for i in html_issues[:3]
                )
                self.bus.send(build_message(
                    from_agent=AGENT_NAME,
                    to_agent="ENGINEER",
                    message_type="revision_request",
                    payload={
                        "original_result": self._results.get("ENGINEER", {}),
                        "feedback": f"QA issues in HTML — please fix: {fb}",
                        "quality_score": qa_result.get("html_review", {}).get("overall_score", 7),
                        "instructions": (
                            "Revise index.html to address QA feedback. "
                            "Commit the improved file to the same branch and return the updated result."
                        ),
                    },
                ))
                self._waiting_for["ENGINEER"] += 1
                dispatched = True
                print("[CEO] 📤 revision_request → ENGINEER (QA HTML feedback)")

            if mkt_issues:
                fb = " | ".join(
                    f"{i.get('severity','?').upper()}: {i.get('description','')}"
                    for i in mkt_issues[:3]
                )
                self.bus.send(build_message(
                    from_agent=AGENT_NAME,
                    to_agent="MARKETING",
                    message_type="revision_request",
                    payload={
                        "original_result": self._results.get("MARKETING", {}),
                        "feedback": f"QA issues in marketing copy — please fix: {fb}",
                        "quality_score": qa_result.get("marketing_review", {}).get("overall_score", 7),
                        "instructions": (
                            "Revise tagline, description, and social posts to address QA feedback. "
                            "Resend email and Slack message, then resubmit."
                        ),
                    },
                ))
                self._waiting_for["MARKETING"] += 1
                dispatched = True
                print("[CEO] 📤 revision_request → MARKETING (QA content feedback)")

            if dispatched:
                print("[CEO] ⏳ Revision requests sent. Pipeline paused until agents respond…")
                return

        elif self._qa_revision_dispatched:
            print("[CEO] ℹ  QA revision loop completed. Proceeding to launch.")
        else:
            print("[CEO] ✅ QA found no actionable issues — proceeding to launch.")
        # ─────────────────────────────────────────────────────────────────

        # ── Launch announcement ──
        eng_r = self._results.get("ENGINEER", {})
        mkt_r = self._results.get("MARKETING", {})

        tagline     = mkt_r.get("tagline", "Study smarter. Stress less.")
        description = mkt_r.get("description", "AI Study Planner — your AI-powered study buddy.")
        pr_url      = eng_r.get("pr_url", "https://github.com/Hasankhan2003/launchmind")

        try:
            blocks = build_launch_blocks(
                tagline=tagline, 
                description=description, 
                pr_url=pr_url,
                posted_by="CEO"
            )
            send_block_message(
                text=f"🚀 AI Study Planner is LIVE! {tagline}",
                blocks=blocks,
            )
            print("[CEO] ✅ Final Slack launch announcement posted.")
        except Exception as e:
            print(f"[CEO] ⚠  Slack announcement failed: {e}")

        print("\n" + "="*60)
        print("[CEO] 🏁 PROJECT COMPLETE — LaunchMind pipeline finished.")
        print("="*60)
        self._project_complete = True

    # ──────────────────────────────────────────
    #  LLM: quality rubric evaluation
    # ──────────────────────────────────────────
    def _evaluate_result(self, agent: str, payload: dict) -> tuple[int, str]:
        """
        Score the result from an agent on a 0–10 rubric using the LLM.
        Returns (score: int, feedback: str).
        """
        print(f"[CEO] 🧠 Evaluating {agent} output with LLM quality rubric…")

        # Agent-specific rubric context
        rubric_context = {
            "PRODUCT": (
                "Check: Does it have a clear value proposition? "
                "Are there at least 3 personas with specific pain points? "
                "Are there at least 5 features with priorities? "
                "Are there at least 4 user stories in 'As a… I want… so that…' format?"
            ),
            "ENGINEER": (
                "Check: Is the HTML complete with a hero, features, CTA, and footer? "
                "Does it look modern and professional? "
                "Were GitHub operations (branch, commit, issue, PR) completed successfully?"
            ),
            "MARKETING": (
                "Check: Is the tagline under 10 words and emotionally compelling? "
                "Does the description clearly explain the product value? "
                "Are social posts platform-appropriate and engaging? "
                "Is the cold email personalized and actionable?"
            ),
            "QA": (
                "Check: Is the QA verdict clearly justified? "
                "Are specific, actionable issues listed? "
                "Did the QA agent post PR comments? "
                "Is the overall assessment balanced and useful?"
            ),
        }.get(agent, "Check: Is the output complete, accurate, and high-quality?")

        prompt = f"""You are the CEO of a startup accelerator critically evaluating your {agent} Agent's output.

Startup: "{self.idea}"

{agent} Agent Output (JSON):
{json.dumps(payload, indent=2)[:3000]}

Evaluation Rubric:
{rubric_context}

Scoring Scale:
  9–10 = Exceptional — exceeds all requirements, publication-ready
   7–8 = Good — meets all requirements with minor room for improvement
   5–6 = Acceptable — meets most requirements but has notable gaps
   0–4 = Poor — significant gaps or errors that must be fixed

Respond ONLY with a raw JSON object (no markdown, no fences):
{{
  "score": <integer 0-10>,
  "feedback": "<2-3 specific, actionable sentences explaining the score and exactly what to improve>"
}}"""

        raw    = send_prompt_json(prompt, temperature=0.2)
        result = self._parse_json(raw, default={"score": 7, "feedback": "Acceptable output."})
        score    = max(0, min(10, int(result.get("score", 7))))
        feedback = str(result.get("feedback", ""))
        return score, feedback

    # ──────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────
    @staticmethod
    def _parse_json(raw: str, default: dict) -> dict:
        """Robustly parse JSON from LLM output, with fallback default."""
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
            print(f"[CEO] ⚠  JSON parse failed, using default. Raw snippet: {raw[:200]}")
            return default

    @property
    def is_complete(self) -> bool:
        return self._project_complete
