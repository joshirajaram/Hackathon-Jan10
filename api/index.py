import logging
from fastapi import FastAPI, Request, HTTPException
from lib.github_utils import get_pr_diffs, get_pr_files
# from lib.agent import run_sanjaya_agent  <-- Import Person 2's function later

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        
        # 5. HANDOFF: Call the Agent (Person 2's Logic)
        # result = run_sanjaya_agent(repo_full_name, changed_files)
        
        return {
            "status": "success", 
            "event": "merged", 
            "files_processed": len(changed_files)
        }
        
    return {"msg": "Ignored: PR not merged"}