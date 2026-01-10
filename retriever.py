import os
from pymongo import MongoClient
import voyageai
from dotenv import load_dotenv

load_dotenv()

def find_relevant_doc(diff_text):
    client = MongoClient(os.getenv("MONGO_URI"))
    # Use the EXACT db and collection names from your successful script
    collection = client["BlastRadius"]["readme_chunks"]
    vo = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))

    # Embed the incoming code change
    query_vector = vo.embed([diff_text], model="voyage-code-3", input_type="query").embeddings[0]

    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index", 
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": 50,
                "limit": 1
            }
        },
        {
            "$project": {
                "_id": 0,
                "content": 1,
                "section_name": 1,
                "score": { "$meta": "vectorSearchScore" }
            }
        }
    ]

    results = list(collection.aggregate(pipeline))
    return results[0] if results else None