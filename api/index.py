import logging
from fastapi import FastAPI, Request, HTTPException
from lib.github_utils import get_pr_files
from lib.orchestrator import generate_readme_from_diff as orchestrator_generate_readme
# from lib.agent import run_sanjaya_agent  <-- Import Person 2's function later
import os
import json
import base64
import requests
import hmac
import hashlib
from typing import Dict, Any, Optional
from dataclasses import dataclass
from fastapi import FastAPI, Request, HTTPException
import uvicorn
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Environment variables
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
BRAIN_SERVICE_URL = os.environ["BRAIN_SERVICE_URL"]  # http://localhost:8002 (Person 2)
GITHUB_API_BASE = "https://api.github.com"
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")  # Optional

@dataclass
class PRResult:
    status: str
    new_pr_number: int
    new_pr_url: str

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def github_headers() -> Dict[str, str]:
    """Standard GitHub API headers."""
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "devflow-hands",
        "Content-Type": "application/json"
    }

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    if not GITHUB_WEBHOOK_SECRET:
        return True
    mac = hmac.new(GITHUB_WEBHOOK_SECRET.encode(), payload, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)

def generate_readme_from_diff(repo_full: str, pr_number: int, diff: list) -> str:
    """Delegate to local orchestrator which runs vector search + ghost writer."""
    logger.info("Calling local orchestrator for README generation")
    return orchestrator_generate_readme(repo_full, pr_number, diff)

# === GITHUB FUNCTIONS (KEEP THESE) ===
def get_repo_default_branch(repo_full: str) -> str:
    url = f"{GITHUB_API_BASE}/repos/{repo_full}"
    resp = requests.get(url, headers=github_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()["default_branch"]

def get_file_sha(repo_full: str, branch: str, path: str) -> Optional[str]:
    url = f"{GITHUB_API_BASE}/repos/{repo_full}/contents/{path}?ref={branch}"
    resp = requests.get(url, headers=github_headers(), timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()["sha"]

def create_or_update_file(repo_full: str, path: str, content: str, branch: str,
                         message: str, sha: Optional[str] = None) -> Dict[str, Any]:
    url = f"{GITHUB_API_BASE}/repos/{repo_full}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        "branch": branch
    }
    if sha:
        payload["sha"] = sha
    resp = requests.put(url, headers=github_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()

def create_branch(repo_full: str, new_branch: str, default_branch: str) -> None:
    ref_url = f"{GITHUB_API_BASE}/repos/{repo_full}/git/ref/heads/{default_branch}"
    ref_resp = requests.get(ref_url, headers=github_headers(), timeout=30)
    ref_resp.raise_for_status()
    default_sha = ref_resp.json()["object"]["sha"]
    
    create_url = f"{GITHUB_API_BASE}/repos/{repo_full}/git/refs"
    payload = {"ref": f"refs/heads/{new_branch}", "sha": default_sha}
    resp = requests.post(create_url, headers=github_headers(), json=payload, timeout=30)
    if resp.status_code == 422:
        logger.info("Branch %s already exists, continuing...", new_branch)
    else:
        resp.raise_for_status()

def create_pull_request(repo_full: str, head_branch: str, base_branch: str,
                       pr_number: int, title: str, body: str) -> Dict[str, Any]:
    url = f"{GITHUB_API_BASE}/repos/{repo_full}/pulls"
    payload = {
        "title": title,
        "head": head_branch,
        "base": base_branch,
        "body": body
    }
    resp = requests.post(url, headers=github_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()

def process_merged_pr(repo_full: str, pr_number: int, diff: list) -> PRResult:
    """
    SIMPLIFIED FLOW:
    Person 4 → You → Person 2 → GitHub PR
               ↓      ↓
            diff   AI README
    """
    logger.info("🤖 Processing PR #%s in %s", pr_number, repo_full)
    
    # 1. Call orchestrator to get per-file updates (mapping: path -> new content)
    updates = generate_readme_from_diff(repo_full, pr_number, diff)

    # 2. GitHub mechanics: create branch, write each updated file
    default_branch = get_repo_default_branch(repo_full)
    feature_branch = f"devflow/readme-pr-{pr_number}"

    logger.info("🌿 Creating branch %s from %s", feature_branch, default_branch)
    create_branch(repo_full, feature_branch, default_branch)

    if not updates:
        logger.warning("⚠️ Orchestrator produced no updates; nothing to commit.")
        return PRResult("no_changes", 0, "")

    files_written = []
    for path, new_content in updates.items():
        logger.info("✏️ Updating %s...", path)
        existing_sha = get_file_sha(repo_full, feature_branch, path)
        create_or_update_file(
            repo_full, path, new_content, feature_branch,
            f"docs(readme): auto-update from PR #{pr_number}", existing_sha
        )
        files_written.append(path)

    logger.info("🚀 Creating PR with updated docs...")
    pr = create_pull_request(
        repo_full, feature_branch, default_branch, pr_number,
        f"docs(readme): auto-update for PR #{pr_number}",
        f"Auto-generated documentation updates from PR #{pr_number}\n\nFiles updated ({len(files_written)}):\n" + "\n".join(files_written)
    )

    logger.info("✅ Success! New PR: %s", pr['html_url'])
    return PRResult("success", pr["number"], pr['html_url'])

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "GitHub PR Webhook API is running", "webhook_endpoint": "/webhook"}

@app.post("/webhook")
async def github_webhook(request: Request):
    payload = await request.json()
    
    # 1. FILTER: We only care about Pull Requests
    if "pull_request" not in payload:
        return {"msg": "Ignored: Not a PR event"}
    
    action = payload.get("action")
    pr = payload.get("pull_request")
    merged = pr.get("merged", False)
    
    # 2. GUARD: Only proceed if the PR was actually merged
    if action == "closed" and merged:
        logger.info(f"🚀 Merge Detected: PR #{pr['number']} - {pr['title']}")
        
        # 3. EXTRACTION: Get the repo details
        repo_full_name = payload["repository"]["full_name"] # e.g. "octocat/hello-world"
        pr_number = pr["number"]
        
        # 4. ACTION: Fetch the changed files (Your logic)
        changed_files = get_pr_files(repo_full_name, pr_number)
        logger.info(f"Captured changes for {len(changed_files)} files.")
        logger.info(f"Changed files: {changed_files}")
        
        process_merged_pr(repo_full_name, pr_number, changed_files)
        
        return {
            "status": "success", 
            "event": "merged", 
            "files_processed": len(changed_files)
        }
        
    return {"msg": "Ignored: PR not merged"}