import os
import logging
from fireworks.client import Fireworks

def read_file(filepath):
    with open(filepath, 'r') as file:
        return file.read()

def judge_verify_update(diff, draft):
    client = Fireworks(api_key=os.environ.get("FIREWORKS_API_KEY"))
    
    # Prompt the 8B model to be highly critical
    JUDGE_PROMPT = f"""
    Review this documentation update against the code diff. 
    Does it introduce false information? (Yes/No)
    Is it missing any new parameters shown in the diff? (Yes/No)
    
    DIFF: {diff}
    DRAFT: {draft}
    
    Return ONLY: PASS or FAIL: [Reason]
    """

    response = client.chat.completions.create(
        model="accounts/fireworks/models/llama-v3p1-8b-instruct",
        messages=[{"role": "user", "content": JUDGE_PROMPT}]
    )
    
    verdict = response.choices[0].message.content
    # Ensure logger exists (in case this function is used standalone)
    logger = logging.getLogger(__name__)
    logger.info("JUDGE VERDICT: %s", verdict)
    return verdict.startswith("PASS"), verdict