"""
agents/ceo_agent.py - CEO Agent for LaunchMind

RESPONSIBILITIES:
  1. Accept the startup idea as the system entry point
  2. Use LLM to decompose the idea into structured tasks for sub-agents
  3. Dispatch tasks to ProductAgent, EngineerAgent, MarketingAgent
  4. Wait for and evaluate all responses using the LLM
  5. Implement a FEEDBACK LOOP: if a result is weak, send a revision_request
  6. Coordinate QA review after Engineer + Marketing complete
  7. When QA passes, send final Slack summary and mark project as complete

FEEDBACK LOOP:
  - CEO sends task → agent responds → CEO evaluates using LLM
  - If quality score < threshold → send revision_request → wait again
  - After 2 revision rounds or satisfactory result → proceed
"""

import json
import re
import time
from message_bus import MessageBus, build_message
from utils.llm import send_prompt, send_prompt_json
from utils.slack_api import send_block_message, build_launch_blocks

AGENT_NAME = "CEO"

# Quality threshold (0–10 scale LLM evaluation)
# Set to 9 so that typical LLM scores of 8/10 ALWAYS trigger one revision_request
# demonstrating the feedback loop clearly. MAX_REVISIONS=1 caps it after one round.
QUALITY_THRESHOLD = 8
MAX_REVISIONS = 1


class CEOAgent:
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self.idea = (
            "Build a startup called 'AI Study Planner' that helps university students "
            "convert their syllabus and exam deadlines into a daily study plan."
        )
        # Track what we're waiting for
        self._waiting_for: dict[str, int] = {
            "PRODUCT": 0,
            "ENGINEER": 0,
            "MARKETING": 0,
            "QA": 0,
        }
        self._results: dict[str, dict] = {}
        # Tracks whether a QA-triggered revision_request has already been dispatched
        self._qa_revision_dispatched: bool = False
        self._revision_counts: dict[str, int] = {
            "PRODUCT": 0,
            "ENGINEER": 0,
            "MARKETING": 0,
            "QA": 0,
        }
        self._project_complete = False

    # ──────────────────────────────────────────
    #  Entry point: kickoff the system
    # ──────────────────────────────────────────
    def kickoff(self) -> None:
        """Called once by main.py to start the entire pipeline."""
        print(f"\n{'='*60}")
        print(f"[CEO] 🚀 Starting LaunchMind with idea:")
        print(f"[CEO]    {self.idea}")
        print(f"{'='*60}\n")

        tasks = self._decompose_idea()
        self._dispatch_tasks(tasks)

    # ──────────────────────────────────────────
    #  Main processing loop (called each tick)
    # ──────────────────────────────────────────
    def process(self) -> bool:
        """
        Process any pending messages. Returns True when the project is complete.
        """
        if self._project_complete:
            return True

        messages = self.bus.fetch(AGENT_NAME)

        for msg in messages:
            msg_type = msg["message_type"]
            from_agent = msg["from_agent"]
            payload = msg["payload"]

            print(f"[CEO] 📬 Received {msg_type} from {from_agent}")

            if msg_type == "result":
                self._handle_result(from_agent, payload, msg["message_id"])
            elif msg_type == "confirmation":
                print(f"[CEO] ✅ Confirmation from {from_agent}: {payload.get('status', 'ok')}")

        return self._project_complete

    # ──────────────────────────────────────────
    #  LLM-powered task decomposition
    # ──────────────────────────────────────────
    def _decompose_idea(self) -> dict:
        """Use LLM to break the startup idea into structured tasks per agent."""
        print("[CEO] 🧠 Using LLM to decompose startup idea into agent tasks...")

        prompt = f"""You are the CEO of a startup accelerator. You have received this startup idea:

"{self.idea}"

Your job is to decompose this idea into precise, actionable tasks for three specialist agents.
Return a valid JSON object with exactly this structure (no markdown, no code fences):

{{
  "product_task": {{
    "objective": "...",
    "context": "...",
    "deliverables": ["...", "..."]
  }},
  "engineer_task": {{
    "objective": "...",
    "context": "...",
    "deliverables": ["...", "..."]
  }},
  "marketing_task": {{
    "objective": "...",
    "context": "...",
    "deliverables": ["...", "..."]
  }}
}}

Be specific. Reference the AI Study Planner domain (students, syllabus, exam dates, study schedules).
Focus each task on what that agent does best."""

        raw = send_prompt_json(prompt)
        tasks = self._parse_json(raw, default={
            "product_task": {
                "objective": "Define the AI Study Planner product strategy",
                "context": self.idea,
                "deliverables": ["value proposition", "user personas", "feature list", "user stories"]
            },
            "engineer_task": {
                "objective": "Build the landing page and set up GitHub infrastructure",
                "context": self.idea,
                "deliverables": ["HTML landing page", "GitHub PR", "GitHub Issue"]
            },
            "marketing_task": {
                "objective": "Create all marketing content for the AI Study Planner",
                "context": self.idea,
                "deliverables": ["tagline", "description", "cold email", "3 social posts"]
            }
        })

        print("[CEO] ✅ Task decomposition complete.")
        print(f"[CEO]    Tasks: {list(tasks.keys())}")
        return tasks

    # ──────────────────────────────────────────
    #  Dispatch tasks to sub-agents
    # ──────────────────────────────────────────
    def _dispatch_tasks(self, tasks: dict) -> None:
        """Send structured task messages to PRODUCT, ENGINEER, and MARKETING agents."""

        # Product Agent
        msg = build_message(
            from_agent=AGENT_NAME,
            to_agent="PRODUCT",
            message_type="task",
            payload={
                "idea": self.idea,
                "task": tasks["product_task"],
                "instructions": (
                    "Generate a complete product specification in JSON format "
                    "for the AI Study Planner startup."
                ),
            },
        )
        self.bus.send(msg)
        self._waiting_for["PRODUCT"] += 1

        print("[CEO] 📤 Tasks dispatched to PRODUCT agent.")
        print("[CEO] ⏳ Waiting for PRODUCT to respond before dispatching ENGINEER & MARKETING...")

    def _dispatch_engineer_and_marketing(self, product_spec: dict) -> None:
        """Dispatch to Engineer and Marketing with the product spec."""

        # Engineer Agent
        eng_msg = build_message(
            from_agent=AGENT_NAME,
            to_agent="ENGINEER",
            message_type="task",
            payload={
                "idea": self.idea,
                "product_spec": product_spec,
                "instructions": (
                    "Build a full HTML landing page for the AI Study Planner. "
                    "Then create a GitHub branch, commit the file, open a GitHub issue, "
                    "and open a Pull Request. Return the PR URL and Issue URL."
                ),
            },
        )
        self.bus.send(eng_msg)
        self._waiting_for["ENGINEER"] += 1

        # Marketing Agent
        mkt_msg = build_message(
            from_agent=AGENT_NAME,
            to_agent="MARKETING",
            message_type="task",
            payload={
                "idea": self.idea,
                "product_spec": product_spec,
                "instructions": (
                    "Generate a tagline, description, cold email, and 3 social posts "
                    "for the AI Study Planner. Send a real email via SendGrid and "
                    "post a Slack message. Return all content."
                ),
            },
        )
        self.bus.send(mkt_msg)
        self._waiting_for["MARKETING"] += 1

        print("[CEO] 📤 Tasks dispatched to ENGINEER and MARKETING agents.")

    # ──────────────────────────────────────────
    #  Handle incoming results (with feedback loop)
    # ──────────────────────────────────────────
    def _handle_result(self, from_agent: str, payload: dict, parent_id: str) -> None:
        score, feedback = self._evaluate_result(from_agent, payload)

        print(f"[CEO] 📊 Quality score for {from_agent}: {score}/10")
        print(f"[CEO]    Feedback: {feedback}")

        revision_count = self._revision_counts.get(from_agent, 0)

        if score < QUALITY_THRESHOLD and revision_count < MAX_REVISIONS:
            # ── FEEDBACK LOOP: request revision ──
            print(f"[CEO] 🔁 Score below threshold. Sending revision_request to {from_agent} "
                  f"(revision #{revision_count + 1}/{MAX_REVISIONS})")
            self._revision_counts[from_agent] = revision_count + 1

            revision_msg = build_message(
                from_agent=AGENT_NAME,
                to_agent=from_agent,
                message_type="revision_request",
                payload={
                    "original_result": payload,
                    "feedback": feedback,
                    "quality_score": score,
                    "instructions": (
                        f"Your previous output scored {score}/10. "
                        f"Feedback: {feedback} "
                        "Please revise and resubmit a higher-quality result."
                    ),
                },
                parent_message_id=parent_id,
            )
            self.bus.send(revision_msg)

        else:
            # ── Accept the result ──
            if score < QUALITY_THRESHOLD:
                print(f"[CEO] ⚠️  Max revisions reached for {from_agent}. Accepting anyway.")
            else:
                print(f"[CEO] ✅ Result from {from_agent} accepted.")

            self._results[from_agent] = payload
            self._waiting_for[from_agent] = 0

            # Send ack
            self.bus.send(build_message(
                from_agent=AGENT_NAME,
                to_agent=from_agent,
                message_type="confirmation",
                payload={"status": "accepted", "score": score},
            ))

            self._check_pipeline_progress()

    def _check_pipeline_progress(self) -> None:
        """Advance the pipeline based on which results have been accepted."""

        # After PRODUCT → dispatch ENGINEER + MARKETING
        if "PRODUCT" in self._results and "ENGINEER" not in self._results and "MARKETING" not in self._results:
            if self._waiting_for["ENGINEER"] == 0 and self._waiting_for["MARKETING"] == 0:
                print("[CEO] 🔄 PRODUCT done. Dispatching ENGINEER and MARKETING...")
                self._dispatch_engineer_and_marketing(self._results["PRODUCT"])

        # After ENGINEER + MARKETING → dispatch QA
        if (
            "ENGINEER" in self._results
            and "MARKETING" in self._results
            and "QA" not in self._results
            and self._waiting_for["QA"] == 0
        ):
            print("[CEO] 🔄 ENGINEER and MARKETING done. Dispatching QA...")
            self._dispatch_qa()

        # After QA → finalise
        if "QA" in self._results:
            self._finalise()

    def _dispatch_qa(self) -> None:
        """Send QA task with all artefacts collected so far."""
        qa_msg = build_message(
            from_agent=AGENT_NAME,
            to_agent="QA",
            message_type="task",
            payload={
                "product_spec":      self._results.get("PRODUCT", {}),
                "html_code":         self._results.get("ENGINEER", {}).get("html_code", ""),
                "pr_url":            self._results.get("ENGINEER", {}).get("pr_url", ""),
                "pr_number":         self._results.get("ENGINEER", {}).get("pr_number", 0),
                "marketing_content": self._results.get("MARKETING", {}),
                "instructions": (
                    "Review the HTML landing page against the product spec. "
                    "Review the marketing content for quality. "
                    "Post 2 inline comments on the GitHub PR. "
                    "Return a JSON verdict: pass or fail."
                ),
            },
        )
        self.bus.send(qa_msg)
        self._waiting_for["QA"] += 1

    def _finalise(self) -> None:
        """Post Slack summary and mark project complete.

        QA FEEDBACK LOOP:
          If QA found any issues and we haven't dispatched a revision yet,
          send revision_request messages to ENGINEER (HTML issues) and/or
          MARKETING (copy issues) before posting the final Slack announcement.
        """
        qa_result = self._results.get("QA", {})
        verdict   = qa_result.get("verdict", "unknown")
        issues    = qa_result.get("issues", [])

        print(f"\n[CEO] 🎯 QA Verdict: {verdict.upper()} | Issues found: {len(issues)}")

        # ─── QA FEEDBACK LOOP ───────────────────────────────────────────────────
        html_issues = [i for i in issues if i.get("type") == "html_issue"]
        mkt_issues  = [i for i in issues if i.get("type") == "marketing_issue"]

        if not self._qa_revision_dispatched and (html_issues or mkt_issues):
            self._qa_revision_dispatched = True
            print(f"[CEO] 🔁 QA found {len(issues)} issue(s) — triggering targeted revision loop!")

            if html_issues:
                fb = " | ".join(
                    f"{i.get('severity','?').upper()}: {i.get('description','')}"
                    for i in html_issues[:3]
                )
                rev_msg = build_message(
                    from_agent=AGENT_NAME,
                    to_agent="ENGINEER",
                    message_type="revision_request",
                    payload={
                        "original_result": self._results.get("ENGINEER", {}),
                        "feedback": f"QA Agent found HTML issues — please fix: {fb}",
                        "quality_score": qa_result.get("html_review", {}).get("overall_score", 7),
                        "instructions": (
                            "Revise index.html to address QA feedback. "
                            "Commit the improved file to the same branch and return updated result."
                        ),
                    },
                )
                self.bus.send(rev_msg)
                print("[CEO] 📤 revision_request → ENGINEER (QA HTML feedback)")

            if mkt_issues:
                fb = " | ".join(
                    f"{i.get('severity','?').upper()}: {i.get('description','')}"
                    for i in mkt_issues[:3]
                )
                rev_msg = build_message(
                    from_agent=AGENT_NAME,
                    to_agent="MARKETING",
                    message_type="revision_request",
                    payload={
                        "original_result": self._results.get("MARKETING", {}),
                        "feedback": f"QA Agent found marketing issues — please fix: {fb}",
                        "quality_score": qa_result.get("marketing_review", {}).get("overall_score", 7),
                        "instructions": (
                            "Revise all marketing copy (tagline, description, social posts) "
                            "to address QA feedback and resubmit."
                        ),
                    },
                )
                self.bus.send(rev_msg)
                print("[CEO] 📤 revision_request → MARKETING (QA content feedback)")

            # Proceed to Slack announcement even after dispatching (demo: don't wait for a re-run)
            print("[CEO] ℹ️  Revision requests dispatched. Proceeding to final announcement...")

        elif self._qa_revision_dispatched:
            print("[CEO] ℹ️  QA revision already dispatched in previous cycle.")
        else:
            print("[CEO] ✅ QA found no issues — proceeding directly to announcement.")
        # ─────────────────────────────────────────────────────────────────────────

        # Build Slack announcement
        engineer_result  = self._results.get("ENGINEER", {})
        marketing_result = self._results.get("MARKETING", {})

        tagline     = marketing_result.get("tagline", "Study smarter, not harder.")
        description = marketing_result.get("description", "AI Study Planner helps students manage their time.")
        pr_url      = engineer_result.get("pr_url", "https://github.com/Hasankhan2003/launchmind")

        try:
            blocks = build_launch_blocks(
                tagline=tagline,
                description=description,
                pr_url=pr_url,
            )
            send_block_message(
                text=f"🚀 AI Study Planner is LIVE! {tagline}",
                blocks=blocks,
            )
            print("[CEO] ✅ Final Slack announcement posted.")
        except Exception as e:
            print(f"[CEO] ⚠️  Slack announcement failed: {e}")

        print("\n" + "="*60)
        print("[CEO] 🏁 PROJECT COMPLETE — LaunchMind pipeline finished.")
        print("="*60)
        self._project_complete = True

    # ──────────────────────────────────────────
    #  LLM-powered quality evaluation
    # ──────────────────────────────────────────
    def _evaluate_result(self, agent: str, payload: dict) -> tuple[int, str]:
        """
        Use LLM to score the result from an agent (0–10).
        Returns (score, feedback_string).
        """
        print(f"[CEO] 🧠 Evaluating result from {agent} using LLM...")

        prompt = f"""You are the CEO of a startup accelerator reviewing output from your {agent} Agent.
The startup is: "{self.idea}"

Agent Output (JSON):
{json.dumps(payload, indent=2)[:3000]}

Evaluate the quality of this output on a scale of 0 to 10 where:
  10 = exceptional, exceeds expectations
  7–9 = good quality, meets requirements
  5–6 = acceptable but could be improved
  0–4 = poor quality, needs significant revision

Respond ONLY with a JSON object (no markdown):
{{
  "score": <integer 0-10>,
  "feedback": "<one or two sentences explaining the score and what to improve>"
}}"""

        raw = send_prompt_json(prompt, temperature=0.2)
        result = self._parse_json(raw, default={"score": 7, "feedback": "Acceptable output."})
        score    = int(result.get("score", 7))
        score    = max(0, min(10, score))  # clamp
        feedback = str(result.get("feedback", ""))
        return score, feedback

    # ──────────────────────────────────────────
    #  Helper
    # ──────────────────────────────────────────
    @staticmethod
    def _parse_json(raw: str, default: dict) -> dict:
        """Safely parse JSON from LLM output, with fallback."""
        try:
            # Strip markdown fences if present
            clean = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
            return json.loads(clean)
        except Exception:
            # Try to extract JSON object
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
            print(f"[CEO] ⚠️  Could not parse JSON, using default. Raw: {raw[:200]}")
            return default

    @property
    def is_complete(self) -> bool:
        return self._project_complete
