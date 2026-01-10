import os
from dotenv import load_dotenv
from pymongo import MongoClient
import voyageai
import time

# Setup Clients
load_dotenv()

api_key = os.getenv("VOYAGE_API_KEY")
if not api_key:
    raise ValueError("VOYAGE_API_KEY not found! Check your .env file.")

vo = voyageai.Client(api_key=api_key)

# vo = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))
client = MongoClient(os.getenv("MONGO_URI"))
db = client["BlastRadius"]
collection = db["readme_chunks"]

def initialize_documentation(file_path, repo_name):
    with open(file_path, "r") as f:
        content = f.read()

    sections = content.split("\n## ")
    texts_to_embed = []
    metadata = []

    for i, section in enumerate(sections):
        header = section.split("\n")[0] if i > 0 else "Introduction"
        full_text = f"## {section}" if i > 0 else section
        texts_to_embed.append(full_text)
        metadata.append({"header": header, "index": i})

    print(f"Sending all {len(texts_to_embed)} sections in ONE batch to Voyage...")
    
    # This counts as ONLY 1 request!
    emb_res = vo.embed(texts_to_embed, model="voyage-code-3")
    
    documents = []
    for i, embedding in enumerate(emb_res.embeddings):
        documents.append({
            "repo_name": repo_name,
            "section_name": metadata[i]["header"],
            "content": texts_to_embed[i],
            "embedding": embedding,
            "metadata": {"section_index": metadata[i]["index"]}
        })

    collection.delete_many({"repo_name": repo_name})
    collection.insert_many(documents)
    print("Successfully indexed all sections!")

if __name__ == "__main__":
    # Test it with your project's README or a dummy README
    initialize_documentation("README.md", "blastradius-demo")