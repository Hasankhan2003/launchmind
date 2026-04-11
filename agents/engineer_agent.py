"""
agents/engineer_agent.py - Engineer Agent for LaunchMind

RESPONSIBILITIES:
  1. Receive product spec + task from CEO
  2. Use LLM to generate a full, modern HTML landing page
  3. Perform REAL GitHub actions:
       a. Create a new branch
       b. Commit index.html to that branch
       c. Create a GitHub Issue ("Initial landing page")
       d. Open a Pull Request
  4. Return PR URL, Issue URL, and the HTML code to CEO
  5. Handle revision_request from CEO
"""

import json
import re
import time
from message_bus import MessageBus, build_message
from utils.llm import send_prompt, send_prompt_json
from utils import github_api

AGENT_NAME = "ENGINEER"
BRANCH_NAME = "feature/landing-page"


class EngineerAgent:
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
            print(f"\n[ENGINEER] 📬 Received task from {msg['from_agent']}")
            result = self._process_task(msg["payload"])
            self._send_result(result, parent_id=msg["message_id"])

        elif mtype == "revision_request":
            print(f"\n[ENGINEER] 🔁 Revision request from {msg['from_agent']}")
            feedback = msg["payload"].get("feedback", "")
            original = msg["payload"].get("original_result", {})
            result   = self._revise(original, feedback)
            self._send_result(result, parent_id=msg["message_id"])

        else:
            print(f"[ENGINEER] ℹ️  Ignoring message type '{mtype}'")

    # ──────────────────────────────────────────
    #  Core task processing
    # ──────────────────────────────────────────
    def _process_task(self, payload: dict) -> dict:
        product_spec = payload.get("product_spec", {})
        idea         = payload.get("idea", "")

        # Step 1: Generate HTML with LLM
        html_code = self._generate_landing_page(idea, product_spec)

        # Step 2: GitHub actions
        pr_url, issue_url, pr_number = self._github_actions(html_code, product_spec)

        return {
            "html_code":  html_code,
            "pr_url":     pr_url,
            "pr_number":  pr_number,
            "issue_url":  issue_url,
            "branch":     BRANCH_NAME,
            "file":       "index.html",
        }

    def _revise(self, original: dict, feedback: str) -> dict:
        """Regenerate landing page with CEO feedback incorporated."""
        print(f"[ENGINEER] 🧠 Revising landing page based on: '{feedback}'")
        html_code = self._revise_html(original.get("html_code", ""), feedback)

        # Update the file on GitHub
        try:
            github_api.create_file(
                filepath="index.html",
                content=html_code,
                branch=BRANCH_NAME,
                commit_message="Revise landing page based on CEO feedback",
            )
            print("[ENGINEER] ✅ Revised HTML committed to GitHub.")
        except Exception as e:
            print(f"[ENGINEER] ⚠️  Could not update GitHub file: {e}")

        return {
            **original,
            "html_code": html_code,
        }

    # ──────────────────────────────────────────
    #  LLM: generate HTML landing page
    # ──────────────────────────────────────────
    def _generate_landing_page(self, idea: str, spec: dict) -> str:
        print("[ENGINEER] 🧠 Generating HTML landing page with LLM...")

        value_prop = spec.get("value_proposition", "")
        features   = spec.get("features", [])
        personas   = spec.get("personas", [])

        features_text = "\n".join(
            f"- {f['name']}: {f['description']}" for f in features[:5]
        ) if features else "- Study Schedule Generator\n- Deadline Tracker\n- Workload Balancer"

        prompt = f"""You are an expert front-end developer. Create a COMPLETE, modern, single-page HTML landing page for this startup:

Idea: "{idea}"
Value Proposition: "{value_prop}"

Features:
{features_text}

REQUIREMENTS:
1. Single file: everything in one HTML file (inline CSS + inline JS)
2. Modern design: dark gradient background, glass morphism cards, smooth animations
3. Sections:
   - Hero section with headline, sub-headline, and CTA button
   - Features section (3–5 cards with icons using emoji)
   - How It Works section (3 steps)
   - Pricing section (Free vs Premium)
   - Footer with copyright
4. Color palette: indigo/purple gradient (#6366f1 to #8b5cf6)
5. Google Fonts: Inter (loaded via @import)
6. Responsive (works on mobile + desktop)
7. CSS animations: fade-in on load, hover effects on cards
8. No external JS libraries. Pure HTML/CSS/JS only.
9. Include a working email signup form (no backend needed, just show alert on submit)

Return ONLY the complete HTML code. No explanation. No markdown fences. Start with <!DOCTYPE html>."""

        html = send_prompt(prompt, temperature=0.4, max_tokens=4096,
                           system_prompt="You are an expert front-end developer. Return only clean HTML code, nothing else.")

        # Clean up any accidental markdown
        html = re.sub(r"^```(?:html)?", "", html.strip(), flags=re.MULTILINE).strip()
        html = re.sub(r"```$", "", html.strip()).strip()
        if not html.startswith("<!"):
            # Extract HTML block
            m = re.search(r"<!DOCTYPE html>.*", html, re.DOTALL | re.IGNORECASE)
            if m:
                html = m.group()

        print(f"[ENGINEER] ✅ Landing page generated ({len(html)} chars).")
        return html

    def _revise_html(self, original_html: str, feedback: str) -> str:
        """Use LLM to revise the HTML based on feedback."""
        prompt = f"""You are a front-end developer revising an HTML landing page.

CEO Feedback: "{feedback}"

Original HTML (first 2000 chars):
{original_html[:2000]}

Revise the HTML to address the feedback. Return the COMPLETE revised HTML file.
Start with <!DOCTYPE html>. No markdown, no fences."""

        html = send_prompt(prompt, temperature=0.3, max_tokens=4096,
                           system_prompt="You are an expert front-end developer. Return only clean HTML code.")
        html = re.sub(r"^```(?:html)?", "", html.strip(), flags=re.MULTILINE).strip()
        html = re.sub(r"```$", "", html.strip()).strip()
        return html

    # ──────────────────────────────────────────
    #  GitHub Actions
    # ──────────────────────────────────────────
    def _github_actions(self, html_code: str, spec: dict) -> tuple[str, str, int]:
        """
        Execute all GitHub operations:
          1. Create branch
          2. Create/commit index.html
          3. Create issue
          4. Open PR

        Returns (pr_url, issue_url, pr_number)
        """
        print("[ENGINEER] 🐙 Starting GitHub operations...")
        pr_url    = ""
        issue_url = ""
        pr_number = 0
        import os as _os, requests as _req

        _repo  = _os.getenv("GITHUB_REPO", "")
        _base  = _os.getenv("GITHUB_BRANCH", "main")
        _owner = _repo.split("/")[0] if "/" in _repo else _repo

        # 0. Ensure base branch exists (repo may be completely empty)
        #    If main doesn't exist yet, seed it with a README so PR creation works.
        try:
            _check = _req.get(
                f"https://api.github.com/repos/{_repo}/git/ref/heads/{_base}",
                headers=github_api._headers(),
                timeout=10,
            )
            if _check.status_code == 404:
                print(f"[ENGINEER] ⚡ Base branch '{_base}' missing — seeding with README...")
                github_api.create_file(
                    filepath="README.md",
                    content=(
                        f"# AI Study Planner\n\n"
                        f"> {spec.get('value_proposition', 'AI-powered study planning for university students.')}\n\n"
                        "Built with LaunchMind — the AI-powered multi-agent startup accelerator.\n"
                    ),
                    branch=_base,
                    commit_message="chore: Initialize repository [LaunchMind]",
                )
                print(f"[ENGINEER] ✅ Base branch '{_base}' initialized.")
                time.sleep(1)
            elif _check.status_code == 200:
                print(f"[ENGINEER] ✅ Base branch '{_base}' exists.")
        except Exception as _e:
            print(f"[ENGINEER] ⚠️  Base branch check failed: {_e}")

        # 1. Create feature branch
        try:
            github_api.create_branch(BRANCH_NAME)
        except Exception as e:
            err_str = str(e)
            if "already exists" in err_str.lower() or "422" in err_str:
                print(f"[ENGINEER] ℹ️  Branch '{BRANCH_NAME}' already exists, continuing...")
            elif "409" in err_str:
                print(f"[ENGINEER] ℹ️  Branch creation conflict — branch likely exists already.")
            else:
                print(f"[ENGINEER] ⚠️  Branch creation failed: {e}")

        # Small delay to let GitHub process the new branch
        time.sleep(1)


        # 2. Commit index.html
        try:
            github_api.create_file(
                filepath="index.html",
                content=html_code,
                branch=BRANCH_NAME,
                commit_message="feat: Add AI Study Planner landing page [LaunchMind]",
            )
        except Exception as e:
            print(f"[ENGINEER] ⚠️  File commit failed: {e}")

        # 3. Create GitHub Issue
        try:
            issue = github_api.create_issue(
                title="Initial landing page for AI Study Planner",
                body=(
                    "## Summary\n\n"
                    "This issue tracks the initial landing page created by the LaunchMind Engineer Agent.\n\n"
                    "## What was built\n"
                    "- Modern responsive HTML landing page\n"
                    "- Sections: Hero, Features, How It Works, Pricing, Footer\n"
                    "- Pure HTML/CSS/JS — no framework dependencies\n\n"
                    "## Product Spec Reference\n"
                    f"**Value Proposition:** {spec.get('value_proposition', 'N/A')}\n\n"
                    "Linked PR will be opened automatically by the Engineer Agent."
                ),
                labels=["landing-page", "auto-generated"],
            )
            issue_url = issue.get("html_url", "")
        except Exception as e:
            print(f"[ENGINEER] ⚠️  Issue creation failed: {e}")

        # 4. Find existing PR or open a new one
        import os as _os, requests as _req

        _repo  = _os.getenv("GITHUB_REPO", "")
        _owner = _repo.split("/")[0] if "/" in _repo else _repo

        # --- 4a. Search for any existing PR for this branch (open OR closed) ---
        try:
            _list_resp = _req.get(
                f"https://api.github.com/repos/{_repo}/pulls",
                headers=github_api._headers(),
                params={"head": f"{_owner}:{BRANCH_NAME}", "state": "all"},
                timeout=10,
            )
            _existing = _list_resp.json() if _list_resp.status_code == 200 else []
            if isinstance(_existing, list) and _existing:
                pr_url    = _existing[0].get("html_url", "")
                pr_number = _existing[0].get("number", 0)
                print(f"[ENGINEER] ℹ️  Found existing PR #{pr_number}: {pr_url}")
        except Exception as _e:
            print(f"[ENGINEER] ⚠️  PR search error: {_e}")

        # --- 4b. Only create a new PR if none was found ---
        if not pr_url:
            _base_candidates = [_os.getenv("GITHUB_BRANCH", "main"), "main", "master"]
            for _base in _base_candidates:
                try:
                    pr = github_api.create_pr(
                        title="feat: AI Study Planner Landing Page [LaunchMind]",
                        body=(
                            "## 🚀 LaunchMind — Automated Pull Request\n\n"
                            "This PR was created automatically by the **LaunchMind Engineer Agent**.\n\n"
                            "### What's included\n"
                            "- ✅ Complete HTML landing page (`index.html`)\n"
                            "- ✅ Responsive design with modern UI\n"
                            "- ✅ Inline CSS animations and glassmorphism cards\n\n"
                            f"### Related Issue\n"
                            f"Closes #{issue_url.split('/')[-1] if issue_url else 'N/A'}\n\n"
                            "### 🤖 Generated by\n"
                            "LaunchMind Multi-Agent System — Engineer Agent\n"
                        ),
                        head_branch=BRANCH_NAME,
                        base_branch=_base,
                    )
                    pr_url    = pr.get("html_url", "")
                    pr_number = pr.get("number", 0)
                    print(f"[ENGINEER] ✅ PR #{pr_number} created: {pr_url}")
                    break
                except Exception as _e:
                    _es = str(_e)
                    if "422" in _es or "already exists" in _es.lower():
                        # Race condition: another process created it; re-try fetch
                        try:
                            _r2 = _req.get(
                                f"https://api.github.com/repos/{_repo}/pulls",
                                headers=github_api._headers(),
                                params={"head": f"{_owner}:{BRANCH_NAME}", "state": "all"},
                                timeout=10,
                            )
                            _prs2 = _r2.json() if _r2.status_code == 200 else []
                            if isinstance(_prs2, list) and _prs2:
                                pr_url    = _prs2[0].get("html_url", "")
                                pr_number = _prs2[0].get("number", 0)
                                print(f"[ENGINEER] ℹ️  Race-fetched PR #{pr_number}: {pr_url}")
                                break
                        except Exception:
                            pass
                    elif "404" in _es:
                        print(f"[ENGINEER] ⚠️  Base branch '{_base}' not found, trying next...")
                        continue
                    else:
                        print(f"[ENGINEER] ⚠️  PR creation failed with base '{_base}': {_e}")
                        break

        print(f"[ENGINEER] ✅ GitHub operations complete.")
        print(f"[ENGINEER]    PR:    {pr_url}")
        print(f"[ENGINEER]    Issue: {issue_url}")
        return pr_url, issue_url, pr_number

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
        print("[ENGINEER] 📤 Result sent to CEO.")
