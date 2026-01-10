"""
BlastRadius Semantic Memory Module

Simplified, modular semantic memory system for documentation indexing and retrieval.
"""

from .indexer import index_repo
from .retriever import find_relevant_doc
from .graph import build_graph, get_sections_by_file, get_code_entities_by_section, get_file_structure

__all__ = [
    'index_repo',
    'find_relevant_doc',
    'build_graph',
    'get_sections_by_file',
    'get_code_entities_by_section',
    'get_file_structure'
]
