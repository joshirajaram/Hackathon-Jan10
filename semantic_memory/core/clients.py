"""
Centralized client management for MongoDB, Voyage AI, and Fireworks AI
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient
import voyageai
from openai import OpenAI

load_dotenv()

# Lazy initialization - clients created on first use
_mongo_client = None
_voyage_client = None
_fireworks_client = None

def get_mongo_client():
    """Get MongoDB client (lazy initialization)"""
    global _mongo_client
    if _mongo_client is None:
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("MONGO_URI not found! Check your .env file.")
        
        # Validate connection string format
        if "localhost" in mongo_uri or "127.0.0.1" in mongo_uri:
            raise ValueError(
                "MONGO_URI appears to point to localhost. "
                "Vector search requires MongoDB Atlas. "
                "Use a connection string like: mongodb+srv://user:pass@cluster.mongodb.net/"
            )
        
        _mongo_client = MongoClient(mongo_uri)
    return _mongo_client

def get_db():
    """Get BlastRadius database"""
    return get_mongo_client()["BlastRadius"]

def get_voyage_client():
    """Get Voyage AI client (lazy initialization)"""
    global _voyage_client
    if _voyage_client is None:
        api_key = os.getenv("VOYAGE_API_KEY")
        if not api_key:
            raise ValueError("VOYAGE_API_KEY not found! Check your .env file.")
        _voyage_client = voyageai.Client(api_key=api_key)
    return _voyage_client

def get_fireworks_client():
    """Get Fireworks AI client (lazy initialization)"""
    global _fireworks_client
    if _fireworks_client is None:
        api_key = os.getenv("FIREWORKS_API_KEY")
        if not api_key:
            raise ValueError("FIREWORKS_API_KEY not found! Check your .env file.")
        _fireworks_client = OpenAI(
            base_url="https://api.fireworks.ai/inference/v1",
            api_key=api_key
        )
    return _fireworks_client
