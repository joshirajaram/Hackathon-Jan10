# Semantic Memory Module

Simplified, modular semantic memory system for BlastRadius.

## Structure

```
semantic_memory/
├── core/           # Client initialization (MongoDB, Voyage AI, Fireworks AI)
├── indexer.py      # Document indexing (replaces initializer + simple_init)
├── retriever.py    # Vector similarity search
└── graph.py        # Knowledge graph (replaces graph_builder + graph_queries)
```

## Quick Start

### Initialize Everything

```bash
python init_semantic_memory.py
```

### Or Use Programmatically

```python
from semantic_memory import index_repo, find_relevant_doc, build_graph

# Index documents
index_repo("sample_repo", "blastradius-demo", use_librarian=True)

# Build knowledge graph
build_graph("sample_repo", "blastradius-demo")

# Find relevant docs
result = find_relevant_doc(code_diff_text)
```

## API

### `index_repo(repo_path, repo_name, use_librarian=True)`
Index all markdown files in a directory.
- `use_librarian=True`: Use Fireworks AI for metadata extraction
- `use_librarian=False`: Simple indexing without AI

### `find_relevant_doc(diff_text, repo_name="blastradius-demo", limit=1)`
Find relevant documentation section for a code diff.

### `build_graph(repo_path, repo_name)`
Build knowledge graph with entities and relationships.

### Graph Queries
```python
from semantic_memory import get_sections_by_file, get_code_entities_by_section, get_file_structure

# Get sections for a file
sections = get_sections_by_file("blastradius-demo", "sample_repo/README.md")

# Get code entities in a section
entities = get_code_entities_by_section("blastradius-demo", section_id)

# Get file structure
structure = get_file_structure("blastradius-demo")
```

## MongoDB Collections

- `readme_chunks` - Vector search documents
- `knowledge_entities` - All entities (sections, functions, etc.)
- `knowledge_relationships` - Relationships between entities
- `code_entities` - Extracted code elements
- `section_index` - Fast text search index
