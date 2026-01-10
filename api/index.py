import logging
from fastapi import FastAPI, Request, HTTPException
from lib.github_utils import get_pr_files
from semantic_memory import find_relevant_doc
import os
import json
import base64
import requests
import hmac
import hashlib
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
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

def find_relevant_docs_for_diffs(diffs: List[Dict], repo_name: str = "blastradius-demo") -> List[Dict]:
    """
    Use semantic memory to find relevant documentation sections for each code diff.
    
    Args:
        diffs: List of file diffs with 'patch' field
        repo_name: Repository name for filtering
    
    Returns:
        List of relevant documentation sections with file_path and content
    """
    relevant_docs = []
    
    for file_diff in diffs:
        patch = file_diff.get("patch", "")
        if not patch:
            continue
        
        try:
            # Use semantic memory to find relevant documentation
            result = find_relevant_doc(patch, repo_name=repo_name, limit=1)
            if result:
                relevant_docs.append({
                    "code_file": file_diff.get("filename", "unknown"),
                    "relevant_doc": {
                        "file_path": result.get("file_path"),
                        "section_name": result.get("section_name"),
                        "content": result.get("content"),
                        "score": result.get("score", 0)
                    }
                })
                logger.info(f"📚 Found relevant doc for {file_diff.get('filename')}: {result.get('file_path')} (score: {result.get('score', 0):.4f})")
        except Exception as e:
            logger.warning(f"⚠️  Error finding relevant doc for {file_diff.get('filename')}: {e}")
    
    return relevant_docs

def generate_readme_from_diff(repo_full: str, pr_number: int, diff: list, relevant_docs: List[Dict] = None) -> str:
    """
    Call Person 2's AI agent with diff and relevant documentation context.
    
    Args:
        repo_full: Repository full name
        pr_number: PR number
        diff: List of file diffs
        relevant_docs: Relevant documentation sections found via semantic memory
    """
    logger.info("Calling Person 2 AI Agent...")
    url = f"{BRAIN_SERVICE_URL}/generate-readme"
    payload = {
        "repo_full": repo_full,
        "pr_number": pr_number,
        "diff": diff,
        "relevant_docs": relevant_docs or []  # Pass semantic memory results
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["new_readme_markdown"]

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
        logger.info(f"Branch {new_branch} already exists, continuing...")
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
    COMPLETE FLOW:
    Person 4 → You (Semantic Memory) → Person 2 → GitHub PR
               ↓           ↓              ↓
            diff    Find relevant docs  AI README
    """
    try:
        logger.info(f"Processing PR #{pr_number} in {repo_full}")
        
        # 1. Use semantic memory to find relevant documentation sections
        logger.info("Searching semantic memory for relevant documentation...")
        # Normalize repo name to match how it's stored in MongoDB
        repo_name = repo_full.replace("/", "-").lower()
        relevant_docs = find_relevant_docs_for_diffs(diff, repo_name=repo_name)
        logger.info(f"📚 Found {len(relevant_docs)} relevant documentation sections")
        
        # 2. Call Person 2 AI agent with diff AND relevant docs
        new_readme = generate_readme_from_diff(repo_full, pr_number, diff, relevant_docs)
        
        # 3. GitHub mechanics
        default_branch = get_repo_default_branch(repo_full)
        feature_branch = f"devflow/readme-pr-{pr_number}"
        
        logger.info(f"🌿 Creating branch {feature_branch} from {default_branch}")
        create_branch(repo_full, feature_branch, default_branch)
        
        logger.info("✏️ Updating README.md...")
        existing_sha = get_file_sha(repo_full, feature_branch, "README.md")
        create_or_update_file(
            repo_full, "README.md", new_readme, feature_branch,
            f"docs(readme): auto-update from PR #{pr_number}", existing_sha
        )
        
        logger.info("🚀 Creating PR...")
        pr = create_pull_request(
            repo_full, feature_branch, default_branch, pr_number,
            f"docs(readme): auto-update for PR #{pr_number}",
            f"""Auto-generated README update from PR #{pr_number}

        **Files analyzed ({len(diff)}):**
        {[f.get('filename', 'unknown') for f in diff[:5]]}"""
        )
        
        logger.info(f"✅ Success! New PR: {pr['html_url']}")
        return PRResult("success", pr["number"], pr['html_url'])
    except Exception as e:
        logger.error(f"Failed to process PR #{pr_number}: {e}", exc_info=True)
        raise

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "GitHub PR Webhook API is running", "webhook_endpoint": "/webhook"}

@app.post("/webhook")
async def github_webhook(request: Request):
    try:
        # Get raw body for signature verification
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        
        # Verify webhook signature if secret is configured
        if GITHUB_WEBHOOK_SECRET and not verify_webhook_signature(body, signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
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
            repo_full_name = payload["repository"]["full_name"]  # e.g. "octocat/hello-world"
            pr_number = pr["number"]
            
            # 4. ACTION: Fetch the changed files
            changed_files = get_pr_files(repo_full_name, pr_number)
            logger.info(f"Captured changes for {len(changed_files)} files.")
            logger.debug(f"Changed files: {[f.get('filename') for f in changed_files]}")
            
            # 5. PROCESS: Use semantic memory and update docs
            result = process_merged_pr(repo_full_name, pr_number, changed_files)
            
            return {
                "status": "success",
                "event": "merged",
                "files_processed": len(changed_files),
                "new_pr_url": result.new_pr_url
            }
        
        return {"msg": "Ignored: PR not merged"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")