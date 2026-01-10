import os
from github import Github

# Setup GitHub Client
# Ensure GITHUB_TOKEN is in your Vercel Environment Variables
g = Github(os.getenv("GITHUB_TOKEN"))

def get_pr_files(repo_name, pr_number):
    """
    Returns a list of changed files with their raw diffs.
    """
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    
    files_data = []
    
    # Get all files in this PR
    for file in pr.get_files():
        # Optimization: Skip assets, lockfiles, or images
        if file.filename.endswith(('.png', '.jpg', '.lock', '.json')):
            continue
            
        files_data.append({
            "filename": file.filename,
            "status": file.status,      # 'added', 'modified', 'removed'
            "patch": file.patch,        # THE GOLD: This is the actual diff text
            "raw_url": file.raw_url     # Link to full file content if needed
        })
        
    return files_data