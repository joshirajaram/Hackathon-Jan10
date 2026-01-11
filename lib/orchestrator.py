import os
import logging
import base64
from typing import List, Dict, Any
import requests

from . import vector_search
from . import ghost_writer

logger = logging.getLogger(__name__)


def _build_combined_diff(diff: List[Dict[str, Any]]) -> str:
    parts = []
    for f in diff:
        filename = f.get("filename", "unknown")
        patch = f.get("patch") or ""
        parts.append(f"FILE: {filename}\nPATCH:\n{patch}\n---\n")
    return "\n".join(parts)


def _get_readme_from_github(repo_full: str) -> str:
    """Fetch README.md from the repository default branch via GitHub API.

    Returns the decoded markdown string, or an empty string if not found.
    """
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo_full}/readme"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 404:
        logger.info("README.md not found for %s", repo_full)
        return ""
    resp.raise_for_status()
    data = resp.json()
    content_b64 = data.get("content", "")
    encoding = data.get("encoding", "base64")
    if encoding != "base64":
        logger.warning("Unexpected encoding for README: %s", encoding)
    try:
        decoded = base64.b64decode(content_b64).decode("utf-8")
    except Exception:
        logger.exception("Failed to decode README content")
        return ""
    return decoded


def _get_file_from_github(repo_full: str, path: str) -> str:
    """Fetch an arbitrary file's content from the repo (decoded). Returns empty string on error."""
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo_full}/contents/{path}"
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 404:
        logger.info("File not found: %s in %s", path, repo_full)
        return ""
    try:
        resp.raise_for_status()
        data = resp.json()
        content_b64 = data.get("content", "")
        encoding = data.get("encoding", "base64")
        if encoding != "base64":
            logger.warning("Unexpected encoding for %s: %s", path, encoding)
        return base64.b64decode(content_b64).decode("utf-8")
    except Exception:
        logger.exception("Failed to fetch or decode %s from %s", path, repo_full)
        return ""


def generate_readme_from_diff(repo_full: str, pr_number: int, diff: List[Dict[str, Any]]) -> str:
    """Orchestrator: run vector search, call ghost_writer to draft README, return new README markdown.

    Steps:
    - Build a combined diff text from changed files
    - Run `vector_search.find_relevant_docs` to log the files that look relevant
    - Fetch the current `README.md` from GitHub
    - Call `ghost_writer.draft_readme_update(diff_text, current_readme)` to get updated README
    - Return the updated README markdown
    """
    logger.info("Orchestrator: generating README for %s PR#%s", repo_full, pr_number)
    diff_text = _build_combined_diff(diff)

    # Derive repo_name used in knowledge graph (use repo slug)
    repo_name = repo_full.split("/")[-1]
    file_updates = {}

    try:
        hits = vector_search.find_relevant_docs(diff_text, "blastradius-demo", top_k=12)
        logger.info("Vector search top hits: %s", hits[:12])
    except Exception:
        logger.exception("Vector search failed; no files to update")
        hits = []

    # Each hit is (file_path, score). For each file, fetch current contents and call ghost_writer.
    for fp, score in hits:
        logger.info("Processing candidate file: %s (score=%.4f)", fp, score)
        current_content = _get_file_from_github(repo_full, fp)
        try:
            new_content = ghost_writer.draft_readme_update(diff_text, current_content)
            if new_content and new_content.strip() != current_content.strip():
                file_updates[fp] = new_content
            else:
                logger.info("No change returned for %s; skipping", fp)
        except Exception:
            logger.exception("ghost_writer failed for %s; skipping", fp)

    # If no per-file updates found, as a fallback attempt to update top-level README
    if not file_updates:
        logger.info("No file-level updates produced; attempting top-level README fallback")
        current_readme = _get_readme_from_github(repo_full)
        try:
            draft = ghost_writer.draft_readme_update(diff_text, current_readme)
            if draft and draft.strip() != current_readme.strip():
                file_updates["README.md"] = draft
        except Exception:
            logger.exception("Fallback README update failed; returning empty mapping")

    return file_updates
