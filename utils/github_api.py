"""
utils/github_api.py - GitHub REST API wrapper for LaunchMind

Provides:
  - create_branch(branch_name, base_branch)
  - create_file(branch, filepath, content, message)
  - create_issue(title, body)
  - create_pr(title, body, head_branch, base_branch)
  - add_pr_comment(pr_number, body)

All functions use the GitHub REST API v3 via the `requests` library.
"""

import os
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO  = os.getenv("GITHUB_REPO")          # e.g. "username/repo-name"
BASE_BRANCH  = os.getenv("GITHUB_BRANCH", "main") # default base branch

API_BASE = "https://api.github.com"

def _headers() -> dict:
    """Return authenticated request headers."""
    if not GITHUB_TOKEN:
        raise EnvironmentError("GITHUB_TOKEN is not set in the environment.")
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo_url(path: str = "") -> str:
    """Build a full API URL for the configured repo."""
    if not GITHUB_REPO:
        raise EnvironmentError("GITHUB_REPO is not set in the environment.")
    return f"{API_BASE}/repos/{GITHUB_REPO}{path}"


# ─────────────────────────────────────────────
#  Public Functions
# ─────────────────────────────────────────────

def create_branch(branch_name: str, base_branch: str = BASE_BRANCH) -> dict:
    """
    Create a new branch from `base_branch`.

    Returns the created ref object from GitHub, or raises on error.
    """
    print(f"[GitHub] Creating branch '{branch_name}' from '{base_branch}'...")

    # 1. Get SHA of the base branch tip
    ref_resp = requests.get(
        _repo_url(f"/git/ref/heads/{base_branch}"),
        headers=_headers(),
        timeout=15,
    )
    ref_resp.raise_for_status()
    sha = ref_resp.json()["object"]["sha"]

    # 2. Create the new ref
    payload = {"ref": f"refs/heads/{branch_name}", "sha": sha}
    create_resp = requests.post(
        _repo_url("/git/refs"),
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    create_resp.raise_for_status()
    result = create_resp.json()
    print(f"[GitHub] ✓ Branch '{branch_name}' created.")
    return result


def create_file(
    filepath: str,
    content: str,
    branch: str,
    commit_message: str = "Add file via LaunchMind",
) -> dict:
    """
    Create (or update) a file in the repository on the specified branch.

    Args:
        filepath:       Repo-relative path, e.g. "index.html"
        content:        Raw file content (will be base64-encoded).
        branch:         Target branch name.
        commit_message: Git commit message.

    Returns the GitHub API response JSON.
    """
    print(f"[GitHub] Creating file '{filepath}' on branch '{branch}'...")

    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    # Check if file already exists (to get its SHA for updates)
    sha = None
    existing = requests.get(
        _repo_url(f"/contents/{filepath}"),
        headers=_headers(),
        params={"ref": branch},
        timeout=15,
    )
    if existing.status_code == 200:
        sha = existing.json().get("sha")

    payload = {
        "message": commit_message,
        "content": encoded,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha  # required for updates

    resp = requests.put(
        _repo_url(f"/contents/{filepath}"),
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"[GitHub] ✓ File '{filepath}' committed.")
    return result


def create_issue(title: str, body: str, labels: list[str] | None = None) -> dict:
    """
    Open a new GitHub Issue.

    Returns the created issue dict (including `number` and `html_url`).
    """
    print(f"[GitHub] Creating issue: '{title}'...")
    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    resp = requests.post(
        _repo_url("/issues"),
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"[GitHub] ✓ Issue #{result['number']} created: {result['html_url']}")
    return result


def create_pr(
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = BASE_BRANCH,
) -> dict:
    """
    Open a Pull Request from `head_branch` into `base_branch`.

    Returns the created PR dict (including `number` and `html_url`).
    """
    print(f"[GitHub] Opening PR: '{title}' ({head_branch} → {base_branch})...")
    payload = {
        "title": title,
        "body": body,
        "head": head_branch,
        "base": base_branch,
    }
    resp = requests.post(
        _repo_url("/pulls"),
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"[GitHub] ✓ PR #{result['number']} opened: {result['html_url']}")
    return result


def add_pr_comment(pr_number: int, body: str) -> dict:
    """
    Post a review comment on a Pull Request (issue comment on the PR thread).

    Returns the created comment dict.
    """
    print(f"[GitHub] Adding comment to PR #{pr_number}...")
    payload = {"body": body}
    resp = requests.post(
        _repo_url(f"/issues/{pr_number}/comments"),
        headers=_headers(),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"[GitHub] ✓ Comment added: {result['html_url']}")
    return result
