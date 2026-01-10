"""
Document Indexer

Indexes markdown files with optional Librarian Agent (Fireworks AI) for metadata extraction.
Supports both simple and smart indexing modes.
"""

import os
import json
from .core.clients import get_db, get_voyage_client, get_fireworks_client

def extract_metadata_with_ai(text: str) -> dict:
    """Extract metadata using Fireworks AI (Librarian Agent)"""
    try:
        fw_client = get_fireworks_client()
        # Try standard Fireworks model format
        model_id = "fireworks/llama-v3-8b-instruct"
        
        prompt = f"""Extract metadata from this Markdown section for a search engine.
        RAW TEXT: "{text}"
        
        Return ONLY a JSON object with:
        1. "summary": One sentence summary.
        2. "keywords": List of function names or endpoints.
        3. "clean_text": The text without junk.
        """
        
        response = fw_client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        # Gracefully fall back if Fireworks AI fails
        error_msg = str(e)
        if "404" in error_msg or "NOT_FOUND" in error_msg:
            # Model not available - use fallback
            pass
        return {"summary": "General section", "keywords": [], "clean_text": text}

def index_repo(repo_path: str, repo_name: str, use_librarian: bool = True):
    """
    Index all markdown files in a repository
    
    Args:
        repo_path: Path to directory containing .md files
        repo_name: Repository identifier
        use_librarian: If True, use Fireworks AI for metadata extraction
    """
    db = get_db()
    collection = db["readme_chunks"]
    vo = get_voyage_client()
    
    # Find all markdown files
    md_files = []
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.lower().endswith('.md'):
                md_files.append(os.path.join(root, file))
    
    if not md_files:
        print(f"⚠ No .md files found in {repo_path}")
        return
    
    print(f"📄 Found {len(md_files)} markdown file(s)")
    
    all_docs = []
    
    # Process each file
    for file_path in md_files:
        print(f"  Processing: {file_path}")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"  ⚠ Error reading {file_path}: {e}")
            continue
        
        # Split by sections (## headers)
        sections = [s for s in content.split("\n## ") if s.strip()]
        
        for i, section in enumerate(sections):
            header = section.split("\n")[0] if i > 0 else "Introduction"
            full_text = f"## {section}" if i > 0 else section
            
            # Extract metadata
            if use_librarian:
                meta = extract_metadata_with_ai(full_text)
                content_text = meta['clean_text']
                rich_text = f"File: {file_path}. Summary: {meta['summary']}. Keywords: {', '.join(meta.get('keywords', []))}. Content: {content_text}"
            else:
                content_text = full_text
                rich_text = f"File: {file_path}. Content: {content_text}"
                meta = {"summary": "", "keywords": []}
            
            all_docs.append({
                "repo_name": repo_name,
                "file_path": file_path,
                "section_name": header,
                "content": content_text,
                "rich_text_for_embedding": rich_text,
                "metadata": {
                    "section_index": i,
                    "summary": meta.get('summary', ''),
                    "keywords": meta.get('keywords', [])
                }
            })
    
    # Generate embeddings
    print(f"🔮 Generating embeddings for {len(all_docs)} sections...")
    embeddings = vo.embed(
        [d["rich_text_for_embedding"] for d in all_docs],
        model="voyage-code-3",
        input_type="document"
    ).embeddings
    
    for i, emb in enumerate(embeddings):
        all_docs[i]["embedding"] = emb
    
    # Store in MongoDB
    collection.delete_many({"repo_name": repo_name})
    collection.insert_many(all_docs)
    print(f"✅ Indexed {len(all_docs)} sections!")
