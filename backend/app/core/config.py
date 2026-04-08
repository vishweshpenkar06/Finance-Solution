from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/finance_db"
    ALPHA_VANTAGE_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    SECRET_KEY: str = "secret-key-change-in-production"
    DEBUG: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings():
    return Settings()
