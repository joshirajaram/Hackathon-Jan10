#!/usr/bin/env python3
"""
Initialize Semantic Memory System

Single entry point for setting up the complete semantic memory system.
"""

from semantic_memory import index_repo, build_graph

if __name__ == "__main__":
    repo_name = "blastradius-demo"
    repo_path = "sample_repo"
    use_librarian = True  # Set to False for simple indexing
    
    print("="*60)
    print("INITIALIZING SEMANTIC MEMORY SYSTEM")
    print("="*60)
    
    print(f"\n📚 Step 1: Indexing documents...")
    print(f"   Mode: {'Smart (with Librarian Agent)' if use_librarian else 'Simple'}")
    index_repo(repo_path, repo_name, use_librarian=use_librarian)
    
    print(f"\n🕸️  Step 2: Building knowledge graph...")
    stats = build_graph(repo_path, repo_name)
    
    print("\n" + "="*60)
    print("SEMANTIC MEMORY SYSTEM READY")
    print("="*60)
    print(f"\nSummary:")
    print(f"   - Vector search documents: indexed")
    print(f"   - Knowledge entities: {stats['entities']}")
    print(f"   - Code entities: {stats['code_entities']}")
    print(f"   - Relationships: {stats['relationships']}")
