import os
import math
from typing import List, Tuple, Optional

import pymongo
import logging
import voyageai

logger = logging.getLogger(__name__)


def get_mongo_db():
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    client = pymongo.MongoClient(uri)
    db_name = os.environ.get("MONGO_DB", "BlastRadius")
    return client[db_name]


def embed_text(text: str) -> List[float]:
    """Return an embedding for `text` using Voyage AI's embeddings API.

    Falls back to a deterministic local hashed-vector if no API key is set
    (useful for offline testing). The production path expects `VOYAGE_API_KEY`
    to be set and an available `voyage-code-3` (1024-dim) or similar model.
    """
    # Use Voyage AI for embeddings
    voyage_key = os.environ.get("VOYAGE_API_KEY")
    model = os.environ.get("EMBEDDING_MODEL", "voyage-code-3")
    if voyage_key:
        try:
            vo = voyageai.Client(api_key=voyage_key)
            embedding = vo.embed([text], model=model, input_type="query").embeddings[0]
            return embedding
        except Exception as e:
            logger.exception(f"Voyage AI embedding call failed: {e}; falling back to local embedding")

    # Local deterministic fallback (for dev without any API keys)
    vec = [0.0] * 128
    for i, ch in enumerate(text[:4096]):
        vec[i % 128] += (ord(ch) % 97) / 97.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _cosine_sim(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return -1.0
    # allow differing dimensions by using min length
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(a[i] * a[i] for i in range(n)))
    nb = math.sqrt(sum(b[i] * b[i] for i in range(n)))
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


def find_relevant_docs(diff_text: str, repo_name: str, top_k: int = 6, min_score: Optional[float] = None) -> List[Tuple[str, float]]:
    """Return a list of `(file_path, score)` ordered by relevance for `diff_text`.

    This loads embeddings from the `readme_chunks` collection for `repo_name`,
    computes cosine similarity against an embedding for `diff_text`, and
    returns the top-k file paths to consider updating.

    Notes:
    - Documents may contain multiple chunks from the same file; results are
      aggregated by `file_path` (max score wins) to produce file-level ranking.
    - For production with large repos, replace the in-process scoring with a
      proper vector index (MongoDB Atlas `$vectorSearch`, Milvus, Pinecone, etc.).
    """
    db = get_mongo_db()
    col = db["readme_chunks"]

    query = {"repo_name": repo_name, "embedding": {"$exists": True}}
    projection = {"file_path": 1, "embedding": 1}
    cursor = col.find(query, projection)

    query_emb = embed_text(diff_text)

    # Score each chunk and keep the best score per file_path
    best_scores = {}
    for doc in cursor:
        emb = doc.get("embedding")
        if not emb:
            continue
        score = _cosine_sim(query_emb, emb)
        fp = doc.get("file_path")
        if fp is None:
            continue
        prev = best_scores.get(fp)
        if prev is None or score > prev:
            best_scores[fp] = score

    # Convert to sorted list
    results = sorted(best_scores.items(), key=lambda kv: kv[1], reverse=True)

    if min_score is not None:
        results = [r for r in results if r[1] >= min_score]

    return results[:top_k]


if __name__ == "__main__":
    # Quick manual test: set env MONGO_URI and OPENAI_API_KEY as needed.
    sample_diff = "Added new authentication parameter `api_key` to the login endpoint."
    logger.info("Searching for relevant docs...")
    hits = find_relevant_docs(sample_diff, repo_name=os.environ.get("REPO_NAME", "blastradius-demo"))
    for path, score in hits:
        logger.info("%0.4f\t%s", score, path)
