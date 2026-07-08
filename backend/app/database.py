import os
# pyrefly: ignore [missing-import]
from pymongo import MongoClient

# Fetch environment variables for MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB", "galxy")

# Global MongoClient and Database instance
client = None
db = None

def get_db():
    """
    Returns the database instance. Initializes it if it hasn't been set up.
    """
    global client, db
    if db is None:
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB_NAME]
    return db

def close_db():
    """
    Closes the connection to MongoDB if it is open.
    """
    global client, db
    if client is not None:
        client.close()
        client = None
        db = None
