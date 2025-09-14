from pydantic_settings import BaseSettings
from typing import Optional, List

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Biodata Assistant"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "sqlite:///./biodata.db"
    
    # API Keys
    AGENTMAIL_API_KEY: Optional[str] = None
    AGENTMAIL_DOMAIN: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # Security
    SECRET_KEY: str = "change-me-in-production"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]
    
    # Browser Service
    BROWSER_SERVICE_URL: str = "http://browser-service:3000"
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    class Config:
        env_file = ".env"

settings = Settings()
