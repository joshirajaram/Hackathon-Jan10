import os
import logging
import warnings
from fireworks.client import Fireworks

# Suppress aiohttp unclosed session warnings
warnings.filterwarnings("ignore", message=".*Unclosed client session.*")

def read_file(filepath):
    with open(filepath, 'r') as file:
        return file.read()

def draft_readme_update(diff, current_chunk):
    # Configure logger (follow pattern used in `api/index.py`)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    SYSTEM_PROMPT = """
    ### SYSTEM PROMPT: DOCUMENTATION NAVIGATOR
You are a Surgical Documentation Agent. Your goal is to update the README based on a code DIFF and a DEPENDENCY MAP.

### CONTEXT:
1. **CODE DIFF**: [The technical changes]
2. **DEPENDENCY MAP (from MongoDB)**: 
   $dependency_chunks
   (This tells you exactly which README sections are impacted by the files in the diff.)

### YOUR TASK:
1. **Identify Targets**: Based on the DEPENDENCY MAP, list the specific README sections that need modification.
2. **Surgical Edit**: Update ONLY those sections. 
3. **Consistency Check**: Ensure the new technical details from the DIFF are integrated into the sections identified by the MAP.

### CONSTRAINTS:
- **Do Not Drift**: If the MAP says only the "API" section is impacted, do not touch the "Usage" section even if you think you should. Trust the MAP.
- **Maintain Flow**: Even though the update is surgical, ensure the transition between the old text and the new update is seamless.

RULES:
KEEP these sections if they exist and are unchanged:
✓ Badges (stars, license, CI status)
✓ Project title + description
✓ Table of contents
✓ License footer

UPDATE these in the readme.md based on changes:
- Features list
- Installation (new deps)
- Quickstart/Usage
- API endpoints
- Screenshots/GIFs (describe)

ADD these if missing:
- New feature sections
- New commands
- Environment variables

 OUTPUT FORMAT (MUST be valid Markdown):
```markdown
 [Project Name]
[![Stars][stars]][repo] [![License][license]][license]
> [1-sentence project description - update if scope changed]

Features
- [Updated list with new features from PR]

Installation
```bash
[Updated install commands with new deps]

Quick Start
bash
npm run dev   or whatever the new start command is

API / Usage
text
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth`  | POST   | JWT login   |  [NEW from PR]
Contributing
[Keep existing or standard template]
License
[Keep existing]

 CONSTRAINTS:
•	REPLACE entire README (don't say "update section X")
•	Use exactly the same badges/TOC structure from old_readme
•	Keep tone and style consistent with old_readme
•	NEVER delete screenshots/badges/license
•	DO NOT DELETE any sections unless explicitly told by the DIFF
•	If no changes needed, return the original README exactly
•	Be concise; avoid fluff
•	Use markdown code blocks for commands/tables
•	Use the same section headings as the original README
•	When adding new sections, follow the existing README style
•	Always include working code blocks (no placeholders)
•	Max 2000 lines (concise but complete)
•	No "I updated..." commentary
•	No breaking existing sections unnecessarily
    """
    logger.debug("SYSTEM PROMPT: %s", SYSTEM_PROMPT)

    # Create client
    client = Fireworks(api_key=os.environ.get("FIREWORKS_API_KEY"))
    try:
        response = client.chat.completions.create(
            model="accounts/fireworks/models/llama-v3p3-70b-instruct",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"DIFF:\n{diff}\n\nCURRENT SECTION:\n{current_chunk}"}
            ],
            temperature=0.1
        )
        result = response.choices[0].message.content
        
        # Attempt to close internal aiohttp session
        try:
            if hasattr(client, '_client') and hasattr(client._client, 'close'):
                client._client.close()
            elif hasattr(client, 'client') and hasattr(client.client, 'close'):
                client.client.close()
        except:
            pass
            
        return result
    except Exception as e:
        logger.error(f"Fireworks API call failed: {e}")
        # Still attempt cleanup
        try:
            if hasattr(client, '_client') and hasattr(client._client, 'close'):
                client._client.close()
        except:
            pass
        raise
