import os
import logging
from fireworks.client import Fireworks

def read_file(filepath):
    with open(filepath, 'r') as file:
        return file.read()

def draft_readme_update(diff, current_chunk):
    client = Fireworks(api_key=os.environ.get("FIREWORKS_API_KEY"))
    
    # Configure logger (follow pattern used in `api/index.py`)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    SYSTEM_PROMPT = read_file("../prompts/ghost_writer_prompt.txt")
    logger.debug("SYSTEM PROMPT: %s", SYSTEM_PROMPT)

    response = client.chat.completions.create(
        model="accounts/fireworks/models/llama-v3p1-70b-instruct",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"DIFF:\n{diff}\n\nCURRENT SECTION:\n{current_chunk}"}
        ],
        temperature=0.1
    )
    return response.choices[0].message.content
