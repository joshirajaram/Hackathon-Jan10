"""
Knowledge Graph

Builds and queries a knowledge graph with entities, relationships, and code elements.
"""

import os
import json
from typing import List, Dict, Optional
from .core.clients import get_db, get_fireworks_client

def extract_code_entities(text: str) -> dict:
    """Extract code entities (functions, endpoints, classes) from text"""
    try:
        fw_client = get_fireworks_client()
        # Try standard Fireworks model format
        model_id = "fireworks/llama-v3-8b-instruct"
        
        prompt = f"""Extract all code-related entities from this documentation text.
        
        TEXT: "{text}"
        
        Return ONLY a JSON object with:
        1. "functions": List of function/method names mentioned
        2. "endpoints": List of API endpoints mentioned
        3. "classes": List of class names mentioned
        4. "variables": List of important variable/parameter names
        5. "dependencies": List of external services/libraries mentioned
        
        If none found, return empty lists.
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
        return {"functions": [], "endpoints": [], "classes": [], "variables": [], "dependencies": []}

def build_graph(repo_path: str, repo_name: str):
    """Build knowledge graph from markdown files"""
    db = get_db()
    
    # Collections
    entities_col = db["knowledge_entities"]
    relationships_col = db["knowledge_relationships"]
    code_entities_col = db["code_entities"]
    section_index_col = db["section_index"]
    
    # Clear existing data
    print(f"🗑️  Clearing existing graph for {repo_name}...")
    entities_col.delete_many({"repo_name": repo_name})
    relationships_col.delete_many({"repo_name": repo_name})
    code_entities_col.delete_many({"repo_name": repo_name})
    section_index_col.delete_many({"repo_name": repo_name})
    
    # Find markdown files
    md_files = []
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.lower().endswith('.md'):
                md_files.append(os.path.join(root, file))
    
    if not md_files:
        print(f"⚠ No .md files found in {repo_path}")
        return {"entities": 0, "code_entities": 0, "relationships": 0, "sections": 0}
    
    all_entities = []
    all_relationships = []
    code_entities_dict = {}
    section_index = []
    
    # Process files
    for file_path in md_files:
        print(f"  Processing: {file_path}")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"  ⚠ Error: {e}")
            continue
        
        sections = [s for s in content.split("\n## ") if s.strip()]
        
        for i, section in enumerate(sections):
            header = section.split("\n")[0] if i > 0 else "Introduction"
            full_text = f"## {section}" if i > 0 else section
            section_id = f"{repo_name}:{file_path}:{header}"
            
            # Extract code entities
            entities = extract_code_entities(full_text)
            
            # Create section entity
            section_entity = {
                "entity_id": section_id,
                "entity_type": "section",
                "repo_name": repo_name,
                "file_path": file_path,
                "section_name": header,
                "section_index": i,
                "content": full_text,
                "metadata": {"total_sections_in_file": len(sections), "position": i}
            }
            all_entities.append(section_entity)
            
            # Create code entities (deduplicated)
            for func in entities.get("functions", []):
                entity_id = f"{repo_name}:function:{func}"
                if entity_id not in code_entities_dict:
                    code_entities_dict[entity_id] = {
                        "entity_id": entity_id,
                        "entity_type": "function",
                        "name": func,
                        "repo_name": repo_name,
                        "related_sections": [],
                        "file_path": file_path,
                        "metadata": {"extracted_from": []}
                    }
                code_entities_dict[entity_id]["related_sections"].append(section_id)
                if header not in code_entities_dict[entity_id]["metadata"]["extracted_from"]:
                    code_entities_dict[entity_id]["metadata"]["extracted_from"].append(header)
                
                all_relationships.append({
                    "type": "describes",
                    "from_entity_id": section_id,
                    "to_entity_id": entity_id,
                    "repo_name": repo_name,
                    "relationship_type": "section_describes_function"
                })
            
            # Similar for endpoints and classes...
            for endpoint in entities.get("endpoints", []):
                entity_id = f"{repo_name}:endpoint:{endpoint}"
                if entity_id not in code_entities_dict:
                    code_entities_dict[entity_id] = {
                        "entity_id": entity_id,
                        "entity_type": "endpoint",
                        "name": endpoint,
                        "repo_name": repo_name,
                        "related_sections": [],
                        "file_path": file_path,
                        "metadata": {"extracted_from": []}
                    }
                code_entities_dict[entity_id]["related_sections"].append(section_id)
                all_relationships.append({
                    "type": "describes",
                    "from_entity_id": section_id,
                    "to_entity_id": entity_id,
                    "repo_name": repo_name,
                    "relationship_type": "section_describes_endpoint"
                })
            
            # Section index
            section_index.append({
                "repo_name": repo_name,
                "section_id": section_id,
                "file_path": file_path,
                "section_name": header,
                "searchable_text": f"{header} {full_text[:200]}"
            })
    
    # Insert into MongoDB
    all_code_entities = list(code_entities_dict.values())
    
    if all_entities:
        entities_col.insert_many(all_entities)
    if all_code_entities:
        code_entities_col.insert_many(all_code_entities)
    if all_relationships:
        relationships_col.insert_many(all_relationships)
    if section_index:
        section_index_col.insert_many(section_index)
    
    stats = {
        "entities": len(all_entities),
        "code_entities": len(all_code_entities),
        "relationships": len(all_relationships),
        "sections": len(section_index)
    }
    
    print(f"✅ Graph built: {stats['entities']} entities, {stats['code_entities']} code entities, {stats['relationships']} relationships")
    return stats

# Query functions
def get_sections_by_file(repo_name: str, file_path: str) -> List[Dict]:
    """Get all sections for a file"""
    db = get_db()
    return list(db["knowledge_entities"].find({
        "repo_name": repo_name,
        "entity_type": "section",
        "file_path": file_path
    }, {"_id": 0}))

def get_code_entities_by_section(repo_name: str, section_id: str) -> List[Dict]:
    """Get code entities for a section"""
    db = get_db()
    relationships = list(db["knowledge_relationships"].find({
        "repo_name": repo_name,
        "from_entity_id": section_id,
        "type": "describes"
    }))
    entity_ids = [rel["to_entity_id"] for rel in relationships]
    if not entity_ids:
        return []
    return list(db["code_entities"].find({
        "entity_id": {"$in": entity_ids},
        "repo_name": repo_name
    }, {"_id": 0}))

def get_file_structure(repo_name: str) -> Dict:
    """Get complete file structure"""
    db = get_db()
    sections = list(db["knowledge_entities"].find({
        "repo_name": repo_name,
        "entity_type": "section"
    }, {"_id": 0}))
    
    structure = {}
    for section in sections:
        file_path = section["file_path"]
        if file_path not in structure:
            structure[file_path] = []
        structure[file_path].append({
            "section_name": section["section_name"],
            "section_id": section["entity_id"],
            "section_index": section.get("metadata", {}).get("position", 0)
        })
    
    for file_path in structure:
        structure[file_path].sort(key=lambda x: x["section_index"])
    
    return structure
