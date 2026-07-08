import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "galxy_db")
    
    FLASK_ENV = os.getenv("FLASK_ENV", "production").lower()
    
    JWT_SECRET = os.getenv("JWT_SECRET")
    if FLASK_ENV == "development":
        if not JWT_SECRET:
            JWT_SECRET = "galxy_secret_key_123456_change_me"
    else:
        if not JWT_SECRET or JWT_SECRET == "galxy_secret_key_123456_change_me":
            raise RuntimeError("CRITICAL SECURITY ERROR: JWT_SECRET must be set explicitly in non-development mode.")
            
    JWT_ACCESS_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "60"))
    PORT = int(os.getenv("PORT", "5000"))
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:5173")
