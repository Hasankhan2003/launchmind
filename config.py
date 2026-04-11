"""
config.py - Configuration for LaunchMind Multi-Agent System

Centralized settings to avoid magic numbers scattered throughout the codebase.
Override via environment variables where applicable.
"""

import os

# ─────────────────────────────────────────────
#  Startup Idea (overridable via env or CLI)
# ─────────────────────────────────────────────
DEFAULT_STARTUP_IDEA = (
    "Build a startup called 'AI Study Planner' that helps university students "
    "convert their syllabus and exam deadlines into a personalized daily study plan "
    "using AI-driven scheduling and smart recommendations."
)

# ─────────────────────────────────────────────
#  Main Loop Configuration
# ─────────────────────────────────────────────
TICK_DELAY = 1.0         # seconds between processing ticks
MAX_TICKS  = 150         # safety cap (~2.5 min at 1.0s/tick)

# ─────────────────────────────────────────────
#  Quality Evaluation Configuration
# ─────────────────────────────────────────────
# CEO evaluates each agent output on a 0-10 scale.
# Outputs scoring BELOW this threshold trigger a revision_request.
QUALITY_THRESHOLD = 7        # realistic: LLM outputs typically 7-9
MAX_REVISIONS_PER_AGENT = 2  # max CEO-driven revision rounds per agent

# ─────────────────────────────────────────────
#  LLM Configuration
# ─────────────────────────────────────────────
LLM_MODEL       = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_RETRIES     = 3
LLM_RETRY_DELAY = 2   # seconds (multiplied by attempt number)

# ─────────────────────────────────────────────
#  Message / File Configuration
# ─────────────────────────────────────────────
HISTORY_FILE = "message_history.json"

# ─────────────────────────────────────────────
#  Marketing Configuration
# ─────────────────────────────────────────────
MAX_TAGLINE_WORDS = 10

# ─────────────────────────────────────────────
#  GitHub Configuration
# ─────────────────────────────────────────────
GITHUB_BRANCH_NAME = os.getenv("GITHUB_FEATURE_BRANCH", "feature/landing-page")
