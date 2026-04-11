"""
agents/engineer_agent.py - Engineer Agent for LaunchMind

ROLE:
  Full-stack Engineer at a startup accelerator. Expert in HTML/CSS/JS
  and GitHub workflow automation.

RESPONSIBILITIES:
  1. Receive the product spec + task from the CEO Agent
  2. Use LLM to generate a complete, modern single-file HTML landing page
  3. Execute REAL GitHub operations in sequence:
       a. Ensure the base branch exists (seed README if empty repo)
       b. Create a feature branch
       c. Commit index.html to that branch
       d. Open a GitHub Issue tracking the landing page
       e. Open a Pull Request from the feature branch
  4. Return PR URL, Issue URL, branch, and the HTML code to CEO
  5. Handle revision_request: regenerate HTML, commit update, return revised result
"""

import json
import re
import time
import os
import requests as _req
from message_bus import MessageBus, build_message
from utils.llm import send_prompt, send_prompt_json
from utils import github_api
from config import GITHUB_BRANCH_NAME

AGENT_NAME  = "ENGINEER"
BRANCH_NAME = GITHUB_BRANCH_NAME


class EngineerAgent:
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
            print(f"\n[ENGINEER] 📬 Task received from {msg['from_agent']}")
            result = self._process_task(msg["payload"])
            self._send_result(result, parent_id=msg["message_id"])

        elif mtype == "revision_request":
            print(f"\n[ENGINEER] 🔁 Revision request from {msg['from_agent']}")
            feedback = msg["payload"].get("feedback", "")
            original = msg["payload"].get("original_result", {})
            result   = self._revise(original, feedback)
            self._send_result(result, parent_id=msg["message_id"])

        else:
            print(f"[ENGINEER] ℹ  Ignoring '{mtype}' from {msg['from_agent']}")

    # ──────────────────────────────────────────
    #  Core task processing
    # ──────────────────────────────────────────
    def _process_task(self, payload: dict) -> dict:
        spec  = payload.get("product_spec", {})
        idea  = payload.get("idea", "")

        html_code                   = self._generate_landing_page(idea, spec)
        pr_url, issue_url, pr_number = self._github_actions(html_code, spec)

        return {
            "html_code":  html_code,
            "pr_url":     pr_url,
            "pr_number":  pr_number,
            "issue_url":  issue_url,
            "branch":     BRANCH_NAME,
            "file":       "index.html",
            "html_length": len(html_code),
        }

    def _revise(self, original: dict, feedback: str) -> dict:
        """Regenerate landing page with feedback incorporated, recommit to GitHub."""
        print(f"[ENGINEER] 🧠 Revising landing page — feedback: '{feedback[:120]}'")
        html_code = self._revise_html(original.get("html_code", ""), feedback)

        try:
            github_api.create_file(
                filepath="index.html",
                content=html_code,
                branch=BRANCH_NAME,
                commit_message="fix: Revise landing page based on CEO/QA feedback [LaunchMind]",
            )
            print("[ENGINEER] ✅ Revised HTML committed to GitHub.")
        except Exception as e:
            print(f"[ENGINEER] ⚠  Could not commit revision to GitHub: {e}")

        return {**original, "html_code": html_code, "html_length": len(html_code)}

    # ──────────────────────────────────────────
    #  LLM: generate HTML landing page
    # ──────────────────────────────────────────
    def _generate_landing_page(self, idea: str, spec: dict) -> str:
        print("[ENGINEER] 🧠 Generating HTML landing page (LLM)…")

        value_prop = spec.get("value_proposition", "")
        features   = spec.get("features", [])
        personas   = spec.get("personas", [])
        tone       = spec.get("tone", "empathetic and motivating")
        monetization = spec.get("monetization", "Freemium model")

        features_text = "\n".join(
            f"- {f['name']} [{f.get('priority','?').upper()}]: {f['description']}"
            for f in features[:6]
        ) if features else "- Smart Schedule Generator\n- Deadline Tracker\n- Progress Analytics"

        persona_text = "\n".join(
            f"- {p.get('name','User')} ({p.get('role','Student')}): {p.get('pain_point','')}"
            for p in personas[:3]
        ) if personas else "- University students overwhelmed by exam prep"

        prompt = f"""You are an expert front-end developer and UI designer. Create a COMPLETE, production-quality, single-file HTML landing page for this startup.

Startup: "AI Study Planner"
Startup Idea: "{idea}"
Value Proposition: "{value_prop}"
Brand Tone: {tone}

Target Users:
{persona_text}

Key Features to Highlight:
{features_text}

Pricing: {monetization}

━━━ TECHNICAL REQUIREMENTS ━━━
1. Single self-contained file: ALL CSS inline in <style>, ALL JS inline in <script>
2. Google Fonts: Import 'Inter' via @import at top of <style>
3. Color system:
   - Primary gradient: #6366f1 → #8b5cf6 (indigo to violet)
   - Dark background: #0f0f1a
   - Card background: rgba(255,255,255,0.05) with 1px rgba(255,255,255,0.1) border
   - Text: #f1f5f9 (primary), #94a3b8 (secondary)
4. Full responsive design (mobile-first, works at 320px and above)

━━━ REQUIRED SECTIONS (in order) ━━━
1. <nav> — sticky navbar with logo + "Get Started Free" button
2. <section id="hero"> — large headline, sub-headline matching value prop, email signup form + CTA, subtle animated gradient orb in background
3. <section id="features"> — grid of feature cards (use emoji icons), each card has glass-morphism style
4. <section id="how-it-works"> — 3-step numbered process (Upload Syllabus → AI Creates Plan → Study with Confidence)
5. <section id="pricing"> — 2-column card layout (Free vs Premium), highlight Premium card
6. <section id="testimonials"> — 2-3 short quotes from the target personas (fictional but realistic)
7. <footer> — copyright, tagline, social links (emoji-based)

━━━ CSS ANIMATION REQUIREMENTS ━━━
- fadeInUp animation on page load for hero content
- Smooth hover: cards lift 8px with box-shadow increase
- CTA button: pulse glow effect
- Navbar: backdrop-filter blur when scrolled (use JS scroll listener)
- Feature cards: subtle shimmer/gradient border on hover

━━━ JS REQUIREMENTS ━━━
- Email signup form: preventDefault + show success message "🎉 You're on the list! We'll be in touch soon."
- Smooth scroll for nav anchor links
- Navbar background transition on scroll

━━━ SEMANTIC HTML ━━━
- Use: <header>, <nav>, <main>, <section>, <article>, <footer>
- Each section has a unique id
- Buttons have descriptive aria-label attributes

Return ONLY the complete HTML. Start with <!DOCTYPE html>. No markdown, no fences, no explanation."""

        html = send_prompt(
            prompt,
            temperature=0.3,
            max_tokens=4096,
            system_prompt=(
                "You are an expert front-end developer. "
                "Return only complete, clean, production-ready HTML code. "
                "Nothing else — no explanations, no markdown fences."
            ),
        )

        # Strip any accidental markdown wrapping
        html = re.sub(r"^```(?:html)?", "", html.strip(), flags=re.MULTILINE).strip()
        html = re.sub(r"```$", "", html.strip()).strip()
        if not html.lower().startswith("<!"):
            m = re.search(r"<!DOCTYPE html>.*", html, re.DOTALL | re.IGNORECASE)
            if m:
                html = m.group()

        print(f"[ENGINEER] ✅ HTML landing page generated ({len(html):,} chars).")
        return html

    def _revise_html(self, original_html: str, feedback: str) -> str:
        """Use LLM to revise the HTML based on CEO/QA feedback."""
        prompt = f"""You are an expert front-end developer revising an HTML landing page.

Feedback to address:
"{feedback}"

Original HTML (first 2500 chars):
{original_html[:2500]}

Instructions:
1. Address EVERY point in the feedback
2. Maintain the existing design language (dark theme, indigo/violet palette, glassmorphism)
3. Return the COMPLETE revised HTML file
4. Ensure semantic HTML elements are used (header, nav, main, section, footer)
5. Keep all existing sections; only improve what the feedback mentions

Return ONLY the complete HTML. Start with <!DOCTYPE html>. No markdown, no fences."""

        html = send_prompt(
            prompt,
            temperature=0.25,
            max_tokens=4096,
            system_prompt="You are an expert front-end developer. Return only clean, complete HTML code.",
        )
        html = re.sub(r"^```(?:html)?", "", html.strip(), flags=re.MULTILINE).strip()
        html = re.sub(r"```$", "", html.strip()).strip()
        return html

    # ──────────────────────────────────────────
    #  GitHub Operations
    # ──────────────────────────────────────────
    def _github_actions(self, html_code: str, spec: dict) -> tuple[str, str, int]:
        """
        Execute full GitHub workflow:
          0. Ensure base branch exists
          1. Create feature branch
          2. Commit index.html
          3. Create Issue
          4. Find existing PR or open a new one

        Returns (pr_url, issue_url, pr_number)
        """
        print("[ENGINEER] 🐙 Starting GitHub operations…")
        pr_url    = ""
        issue_url = ""
        pr_number = 0

        _repo  = os.getenv("GITHUB_REPO", "")
        _base  = os.getenv("GITHUB_BRANCH", "main")
        _owner = _repo.split("/")[0] if "/" in _repo else _repo

        # ── 0. Ensure base branch exists ──
        try:
            check = _req.get(
                f"https://api.github.com/repos/{_repo}/git/ref/heads/{_base}",
                headers=github_api._headers(),
                timeout=10,
            )
            if check.status_code == 404:
                print(f"[ENGINEER] ⚡ Base branch '{_base}' missing — seeding with README…")
                github_api.create_file(
                    filepath="README.md",
                    content=(
                        f"# AI Study Planner\n\n"
                        f"> {spec.get('value_proposition', 'AI-powered study planning for university students.')}\n\n"
                        "Built with **LaunchMind** — the AI-powered multi-agent startup accelerator.\n"
                    ),
                    branch=_base,
                    commit_message="chore: Initialize repository [LaunchMind]",
                )
                time.sleep(1)
                print(f"[ENGINEER] ✅ Base branch '{_base}' seeded.")
            else:
                print(f"[ENGINEER] ✅ Base branch '{_base}' exists.")
        except Exception as e:
            print(f"[ENGINEER] ⚠  Base branch check failed: {e}")

        # ── 1. Create feature branch ──
        try:
            github_api.create_branch(BRANCH_NAME)
        except Exception as e:
            err = str(e)
            if "already exists" in err.lower() or "422" in err or "409" in err:
                print(f"[ENGINEER] ℹ  Branch '{BRANCH_NAME}' already exists — continuing.")
            else:
                print(f"[ENGINEER] ⚠  Branch creation failed: {e}")
        time.sleep(1)

        # ── 2. Commit index.html ──
        try:
            github_api.create_file(
                filepath="index.html",
                content=html_code,
                branch=BRANCH_NAME,
                commit_message="feat: Add AI Study Planner landing page [LaunchMind]",
            )
        except Exception as e:
            print(f"[ENGINEER] ⚠  File commit failed: {e}")

        # ── 3. Create GitHub Issue ──
        try:
            issue = github_api.create_issue(
                title="feat: AI Study Planner — Initial Landing Page",
                body=(
                    "## 🚀 Landing Page — LaunchMind Auto-Generated\n\n"
                    "This issue tracks the initial HTML landing page created by the **LaunchMind Engineer Agent**.\n\n"
                    "### What was built\n"
                    "- ✅ Complete single-file HTML landing page (`index.html`)\n"
                    "- ✅ Sections: Hero · Features · How It Works · Pricing · Testimonials · Footer\n"
                    "- ✅ Responsive design with dark theme and glassmorphism cards\n"
                    "- ✅ CSS animations and hover effects\n"
                    "- ✅ Email signup form with JS validation\n\n"
                    "### Product Spec Reference\n"
                    f"**Value Proposition:** {spec.get('value_proposition', 'N/A')}\n\n"
                    "### Linked Resources\n"
                    f"- Branch: `{BRANCH_NAME}`\n"
                    "- PR: opened automatically by Engineer Agent\n\n"
                    "---\n"
                    "_Auto-created by 🤖 LaunchMind Engineer Agent_"
                ),
                labels=["landing-page", "auto-generated", "launchmind"],
            )
            issue_url = issue.get("html_url", "")
        except Exception as e:
            print(f"[ENGINEER] ⚠  Issue creation failed: {e}")

        # ── 4a. Check for existing PR ──
        try:
            r = _req.get(
                f"https://api.github.com/repos/{_repo}/pulls",
                headers=github_api._headers(),
                params={"head": f"{_owner}:{BRANCH_NAME}", "state": "all"},
                timeout=10,
            )
            existing = r.json() if r.status_code == 200 else []
            if isinstance(existing, list) and existing:
                pr_url    = existing[0].get("html_url", "")
                pr_number = existing[0].get("number", 0)
                print(f"[ENGINEER] ℹ  Existing PR #{pr_number} found: {pr_url}")
        except Exception as e:
            print(f"[ENGINEER] ⚠  PR lookup error: {e}")

        # ── 4b. Open new PR if none found ──
        if not pr_url:
            issue_number = issue_url.split("/")[-1] if issue_url else "N/A"
            for base_candidate in [_base, "main", "master"]:
                try:
                    pr = github_api.create_pr(
                        title="feat: AI Study Planner Landing Page [LaunchMind]",
                        body=(
                            "## 🚀 LaunchMind — Auto-Generated Pull Request\n\n"
                            "This PR was created automatically by the **LaunchMind Engineer Agent**.\n\n"
                            "### ✅ What's included\n"
                            "- Complete HTML landing page (`index.html`)\n"
                            "- Responsive dark-theme design with glassmorphism cards\n"
                            "- CSS animations (fadeInUp, hover lift, CTA glow)\n"
                            "- Semantic HTML with accessibility attributes\n"
                            "- Email signup form with JS validation\n\n"
                            f"### 🔗 Related Issue\n"
                            f"Closes #{issue_number}\n\n"
                            "### 🤖 Generated by\n"
                            "LaunchMind Multi-Agent System — Engineer Agent\n\n"
                            "---\n"
                            "_This PR was opened autonomously. QA Agent will post review comments._"
                        ),
                        head_branch=BRANCH_NAME,
                        base_branch=base_candidate,
                    )
                    pr_url    = pr.get("html_url", "")
                    pr_number = pr.get("number", 0)
                    print(f"[ENGINEER] ✅ PR #{pr_number} opened: {pr_url}")
                    break
                except Exception as e:
                    err = str(e)
                    if "422" in err or "already exists" in err.lower():
                        # Race condition — re-fetch
                        try:
                            r2 = _req.get(
                                f"https://api.github.com/repos/{_repo}/pulls",
                                headers=github_api._headers(),
                                params={"head": f"{_owner}:{BRANCH_NAME}", "state": "all"},
                                timeout=10,
                            )
                            prs2 = r2.json() if r2.status_code == 200 else []
                            if isinstance(prs2, list) and prs2:
                                pr_url    = prs2[0].get("html_url", "")
                                pr_number = prs2[0].get("number", 0)
                                print(f"[ENGINEER] ℹ  Race-fetched PR #{pr_number}: {pr_url}")
                                break
                        except Exception:
                            pass
                    elif "404" in err:
                        print(f"[ENGINEER] ⚠  Base '{base_candidate}' not found, trying next…")
                        continue
                    else:
                        print(f"[ENGINEER] ⚠  PR creation failed (base={base_candidate}): {e}")
                        break

        print(f"[ENGINEER] ✅ GitHub operations complete.")
        print(f"[ENGINEER]    PR:    {pr_url or 'N/A'}")
        print(f"[ENGINEER]    Issue: {issue_url or 'N/A'}")
        return pr_url, issue_url, pr_number

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
        print("[ENGINEER] 📤 Result sent to CEO.")
