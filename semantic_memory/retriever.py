"""
Semantic Retriever

Finds relevant documentation sections using vector similarity search.
"""

from .core.clients import get_db, get_voyage_client

def find_relevant_doc(diff_text: str, repo_name: str = "blastradius-demo", limit: int = 1):
    """
    Find relevant documentation section for a code diff
    
    Args:
        diff_text: Code diff text to search for
        repo_name: Repository name to filter by
        limit: Number of results to return
    
    Returns:
        dict or list: Most relevant document(s) with file_path, content, score
    """
    db = get_db()
    collection = db["readme_chunks"]
    vo = get_voyage_client()
    
    # Embed the code diff as a query
    query_vector = vo.embed(
        [diff_text],
        model="voyage-code-3",
        input_type="query"
    ).embeddings[0]
    
    # Vector search pipeline
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": 50,
                "limit": limit,
                "filter": {"repo_name": repo_name}
            }
        },
        {
            "$project": {
                "_id": 0,
                "file_path": 1,
                "repo_name": 1,
                "section_name": 1,
                "content": 1,
                "rich_text_for_embedding": 1,
                "metadata": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]
    
    try:
        results = list(collection.aggregate(pipeline))
    except Exception as e:
        error_msg = str(e)
        # Provide helpful error message for common issues
        if "vector_index" in error_msg or "index" in error_msg.lower():
            raise ValueError(
                f"Vector search index not found or not configured. "
                f"Error: {error_msg[:200]}. "
                f"Make sure 'vector_index' exists in MongoDB Atlas for collection 'readme_chunks'."
            ) from e
        elif "localhost" in error_msg or "Connection refused" in error_msg:
            raise ValueError(
                f"MongoDB connection issue: {error_msg[:200]}. "
                f"Make sure MONGO_URI points to MongoDB Atlas (not localhost)."
            ) from e
        else:
            raise
    
    if not results:
        return None if limit == 1 else []
    
    return results[0] if limit == 1 else results
