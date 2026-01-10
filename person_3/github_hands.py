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

# === PERSON 2 INTEGRATION (ONLY) ===
def generate_readme_from_diff(repo_full: str, pr_number: int, diff: str) -> str:
    """Call Person 2's AI agent with diff."""
    print("💭 Calling Person 2 AI Agent...")
    url = f"{BRAIN_SERVICE_URL}/generate-readme"
    payload = {
        "repo_full": repo_full,
        "pr_number": pr_number,
        "diff": diff
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
        print(f"Branch {new_branch} already exists, continuing...")
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

# === YOUR MAIN FUNCTION (Person 4 calls this) ===
def process_merged_pr(repo_full: str, pr_number: int, diff: str) -> PRResult:
    """
    SIMPLIFIED FLOW:
    Person 4 → You → Person 2 → GitHub PR
               ↓      ↓
            diff   AI README
    """
    print(f"🤖 Processing PR #{pr_number} in {repo_full}")
    
    # 1. Call Person 2 AI agent with diff
    new_readme = generate_readme_from_diff(repo_full, pr_number, diff)
    
    # 2. GitHub mechanics
    default_branch = get_repo_default_branch(repo_full)
    feature_branch = f"devflow/readme-pr-{pr_number}"
    
    print(f"🌿 Creating branch {feature_branch} from {default_branch}")
    create_branch(repo_full, feature_branch, default_branch)
    
    print("✏️ Updating README.md...")
    existing_sha = get_file_sha(repo_full, feature_branch, "README.md")
    create_or_update_file(
        repo_full, "README.md", new_readme, feature_branch,
        f"docs(readme): auto-update from PR #{pr_number}", existing_sha
    )
    
    print("🚀 Creating PR...")
    pr = create_pull_request(
        repo_full, feature_branch, default_branch, pr_number,
        f"docs(readme): auto-update for PR #{pr_number}",
        f"""Auto-generated README update based on changes in PR #{pr_number}

        Generated by DevFlow AI agent (Person 2).

        **Changes analyzed:** First 500 chars of diff...""")
    
    print(f"✅ Success! New PR: {pr['html_url']}")
    return PRResult("success", pr["number"], pr['html_url'])

# === WEBHOOK SERVER ===
app = FastAPI(title="DevFlow Hands Service (Person 3)")

@app.post("/webhook/github")
async def github_webhook(request: Request):
    """GitHub webhook endpoint for merged PRs."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    
    if signature and not verify_webhook_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    event = request.headers.get("X-GitHub-Event")
    if event != "pull_request":
        return {"status": "ignored", "event": event}
    
    payload = json.loads(body)
    action = payload.get("action")
    pr = payload.get("pull_request", {})
    
    if action == "closed" and pr.get("merged", False):
        repo_full = payload["repository"]["full_name"]
        pr_number = pr["number"]
        
        # Get PR diff (Person 4 provides this)
        diff_url = f"{GITHUB_API_BASE}/repos/{repo_full}/pulls/{pr_number}"
        diff_resp = requests.get(diff_url, headers=github_headers())
        diff_resp.raise_for_status()
        diff_data = diff_resp.json()
        
        # Extract diff or use patch URL
        diff = diff_data.get("diff_url", f"PR #{pr_number} changes")
        
        try:
            result = process_merged_pr(repo_full, pr_number, diff)
            return {
                "status": "success",
                "new_pr_number": result.new_pr_number,
                "new_pr_url": result.new_pr_url
            }
        except Exception as e:
            print(f"❌ Error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    return {"status": "skipped", "action": action}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
