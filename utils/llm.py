"""
utils/llm.py - Groq LLM Interface for LaunchMind

Provides two reusable functions:
    send_prompt(...)      → str   (free-form text response)
    send_prompt_json(...) → str   (instructs model to return JSON only)

Handles:
  - Groq API authentication via GROQ_API_KEY environment variable
  - Configurable model via LLM_MODEL environment variable
  - Retry logic with exponential back-off
  - Rate-limit graceful degradation with cached fallbacks
"""

import os
import time
from groq import Groq
from dotenv import load_dotenv
from config import LLM_RETRIES, LLM_RETRY_DELAY, LLM_MODEL

load_dotenv()

# ─────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────
GROQ_API_KEY      = os.getenv("GROQ_API_KEY")
DEFAULT_MODEL     = LLM_MODEL
DEFAULT_TEMP      = 0.7
DEFAULT_MAX_TOKENS = 4096

MAX_RETRIES  = LLM_RETRIES
RETRY_DELAY  = LLM_RETRY_DELAY

_client: Groq | None = None
_response_cache: dict = {}   # simple in-memory cache for rate-limit fallback


# ─────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────

def _get_client() -> Groq:
    """Lazily initialise and return the Groq client (singleton)."""
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise EnvironmentError(
                "GROQ_API_KEY not found. Please add it to your .env file."
            )
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def _cache_key(prompt: str) -> int:
    return hash(prompt) % 10_000_000


# ─────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────

def send_prompt(
    prompt: str,
    temperature: float = DEFAULT_TEMP,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    system_prompt: str = (
        "You are a helpful AI assistant embedded in LaunchMind, "
        "an autonomous multi-agent startup accelerator system."
    ),
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Send a prompt to the Groq LLM and return the response text.

    Args:
        prompt:        The user instruction / question.
        temperature:   Sampling temperature (0 = deterministic, 1 = creative).
        max_tokens:    Maximum completion tokens.
        system_prompt: System-level role context for the model.
        model:         Groq model identifier.

    Returns:
        The model's response as a plain string.

    Raises:
        RuntimeError if all retries are exhausted and no fallback is available.
    """
    client = _get_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": prompt},
    ]

    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content.strip()

            # Cache for potential rate-limit fallback later
            _response_cache[_cache_key(prompt)] = text
            return text

        except Exception as exc:
            last_error = exc
            err_str    = str(exc).lower()
            is_rate    = "rate_limit" in err_str or "429" in err_str

            print(
                f"[LLM] ⚠  Attempt {attempt}/{MAX_RETRIES} failed: {exc}. "
                f"{'Retrying in {RETRY_DELAY * attempt}s…' if attempt < MAX_RETRIES else 'Applying fallback.'}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            elif is_rate:
                ck = _cache_key(prompt)
                if ck in _response_cache:
                    print("[LLM] ✓ Serving cached response (rate-limit fallback).")
                    return _response_cache[ck]
                print("[LLM] Generating built-in fallback response.")
                return _generate_fallback(prompt)

    raise RuntimeError(f"LLM request failed after {MAX_RETRIES} retries: {last_error}")


def send_prompt_json(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    system_prompt: str = (
        "You are a precise AI assistant embedded in LaunchMind. "
        "You ALWAYS respond with valid JSON only — no markdown, no code fences, "
        "no explanation, just the raw JSON object."
    ),
) -> str:
    """
    Convenience wrapper that strongly instructs the model to return pure JSON.
    Uses lower temperature for consistent structured output.
    """
    return send_prompt(
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=system_prompt,
    )


# ─────────────────────────────────────────────
#  Fallback responses (rate-limit / offline)
# ─────────────────────────────────────────────

def _generate_fallback(prompt: str) -> str:
    """Return a safe deterministic fallback when the LLM is unavailable."""
    p = prompt.lower()

    # Task decomposition (CEO kickoff)
    if "decompose" in p or "product_task" in p:
        return '''{
  "product_task": {
    "objective": "Define a comprehensive product strategy for AI Study Planner",
    "context": "AI-powered study scheduling for university students",
    "deliverables": ["value_proposition", "personas", "features", "user_stories"]
  },
  "engineer_task": {
    "objective": "Build a modern HTML landing page and set up GitHub infrastructure",
    "context": "Create public web presence for AI Study Planner",
    "deliverables": ["index.html", "GitHub PR", "GitHub Issue"]
  },
  "marketing_task": {
    "objective": "Create persuasive launch marketing content",
    "context": "Generate copy for early-adopter acquisition",
    "deliverables": ["tagline", "description", "cold_email", "social_posts"]
  }
}'''

    # CEO quality evaluation
    if "evaluat" in p or ("score" in p and "feedback" in p):
        return '{"score": 7, "feedback": "[Fallback] Default score — LLM temporarily unavailable."}'

    # Marketing content
    if "tagline" in p or "cold_email" in p or ("marketing" in p and "social" in p):
        return '''{
  "tagline": "Study Smart. Stress Less. Ace Every Exam.",
  "description": "AI Study Planner is an intelligent scheduling tool that converts your university syllabus and exam deadlines into a personalized daily study plan — eliminating guesswork and reducing academic stress.",
  "cold_email": {
    "subject": "🎓 Never Cram Again — AI Study Planner Is Here",
    "body": "Hi there,\\n\\nExam season is brutal. Between multiple courses, shifting deadlines, and the pressure to perform, most students spend more time worrying than actually studying.\\n\\nThat's exactly why we built AI Study Planner.\\n\\nYou upload your syllabus, set your exam dates, and our AI generates a realistic, balanced daily study plan — tailored to your pace and priorities.\\n\\nNo more all-nighters. No more last-minute panic. Just a clear path from today to exam day.\\n\\nWe're inviting a limited group of students to try it free. Reply to this email or click the link below to get started.\\n\\nBest,\\nThe AI Study Planner Team"
  },
  "social_posts": {
    "twitter": "📚 Exam stress? AI Study Planner turns your syllabus into a smart daily schedule. Study smarter, not harder. Try it free 👇 #StudyTips #AI #StudentLife",
    "linkedin": "University students face a hidden crisis: not lack of effort, but lack of direction.\\n\\nAI Study Planner solves this by converting your syllabus and exam deadlines into a personalized, day-by-day study roadmap.\\n\\nThe result? Less stress, better retention, and more confidence walking into every exam.\\n\\nWould you have benefited from a tool like this during your studies?",
    "instagram": "✨ No more Sunday-night dread! 📚\\n\\nAI Study Planner creates your perfect study schedule — automatically. Just add your syllabus + exam dates and let AI do the rest. 🧠⚡\\n\\n#StudySmart #AIStudyPlanner #UniversityLife #ExamPrep #StudentHacks #StudyMotivation #AcademicSuccess"
  }
}'''

    # Product specification
    if "product" in p or "specification" in p or "persona" in p:
        return '''{
  "startup_name": "AI Study Planner",
  "value_proposition": "AI Study Planner eliminates the stress of exam preparation by automatically converting any university syllabus and set of exam deadlines into a personalized, balanced daily study schedule — so students always know exactly what to study and when.",
  "personas": [
    {"name": "Alex", "role": "Overwhelmed Freshman", "pain_point": "Juggling 6 courses with overlapping deadlines and no system to prioritize study time"},
    {"name": "Sara", "role": "High-Achieving Pre-Med", "pain_point": "Needs efficient, evidence-based study plans to maximize retention across dense material"},
    {"name": "Jordan", "role": "Working Student", "pain_point": "Has only 3-4 hours per day to study and needs every minute to count"}
  ],
  "features": [
    {"name": "Syllabus Import", "description": "Upload or paste your course syllabus; AI extracts topics and weights.", "priority": "high"},
    {"name": "Smart Schedule Generator", "description": "Creates a daily study plan balancing all courses based on exam proximity.", "priority": "high"},
    {"name": "Deadline Tracker", "description": "Visual countdown to every exam and assignment due date.", "priority": "high"},
    {"name": "Daily Focus Mode", "description": "Shows only today's study tasks to reduce decision fatigue.", "priority": "medium"},
    {"name": "Progress Analytics", "description": "Tracks completed topics and predicts readiness score per subject.", "priority": "medium"}
  ],
  "user_stories": [
    "As an overwhelmed student, I want to upload my syllabus so that I get a structured daily study plan without manual planning.",
    "As a working student, I want to set my available hours per day so that the AI builds a realistic schedule I can actually follow.",
    "As an exam preparer, I want to see a readiness score per subject so that I know where to focus my remaining time.",
    "As a procrastinator, I want daily push reminders so that I start studying before it's too late."
  ],
  "monetization": "Freemium — core scheduling is free; Premium ($9.99/mo) unlocks analytics, calendar sync, and AI-powered topic summaries.",
  "tone": "Empathetic, motivating, and calm — like a knowledgeable study buddy, not a corporate tool."
}'''

    # HTML fallback
    if "html" in p or "landing" in p:
        return (
            "<!DOCTYPE html><html lang='en'><head><title>AI Study Planner</title>"
            "<style>body{font-family:sans-serif;background:#1e1b4b;color:#fff;text-align:center;padding:60px}"
            "h1{font-size:3rem;color:#818cf8}p{color:#c7d2fe}</style></head>"
            "<body><h1>🚀 AI Study Planner</h1>"
            "<p>Study smarter. Stress less. Ace every exam.</p></body></html>"
        )

    return '[Fallback: LLM temporarily unavailable]'
