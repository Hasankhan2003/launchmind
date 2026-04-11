"""
utils/llm.py - Groq LLM Interface for LaunchMind

Provides a single reusable function:
    send_prompt(prompt, temperature, max_tokens, system_prompt) -> str

Handles:
  - Groq API authentication via environment variable
  - Graceful error handling with retries
  - Model selection (llama-3.3-70b-versatile)
"""

import os
import time
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 4096
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

_client: Groq | None = None


def _get_client() -> Groq:
    """Lazily initialise and return the Groq client."""
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise EnvironmentError(
                "GROQ_API_KEY not found. Please set it in your .env file."
            )
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def send_prompt(
    prompt: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    system_prompt: str = "You are a helpful AI assistant working inside a multi-agent startup system called LaunchMind.",
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Send a prompt to the Groq LLM and return the response text.

    Args:
        prompt:        The user-facing prompt / instruction.
        temperature:   Sampling temperature (0.0 = deterministic, 1.0 = creative).
        max_tokens:    Maximum tokens in the completion.
        system_prompt: System-level instruction for the model.
        model:         Groq model identifier.

    Returns:
        The model's response as a plain string.

    Raises:
        RuntimeError if all retries are exhausted.
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
            return text

        except Exception as exc:
            last_error = exc
            print(
                f"[LLM] Attempt {attempt}/{MAX_RETRIES} failed: {exc}. "
                f"{'Retrying...' if attempt < MAX_RETRIES else 'Giving up.'}"
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

    raise RuntimeError(f"LLM request failed after {MAX_RETRIES} retries: {last_error}")


def send_prompt_json(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    system_prompt: str = "You are a helpful AI assistant. Always respond with valid JSON only. No markdown, no explanation, just the JSON object.",
) -> str:
    """
    Convenience wrapper that instructs the model to return pure JSON.
    Lower temperature for more consistent structured output.
    """
    return send_prompt(
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=system_prompt,
    )
