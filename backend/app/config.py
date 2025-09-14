from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
import os
import logging
import json

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
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"

    def get_cors_origins(self) -> List[str]:
        """
        Return CORS origins as a list, parsing comma-separated or JSON array strings.
        """
        v = self.CORS_ORIGINS
        if not v:
            return ["http://localhost:3000", "http://localhost:8080"]
        s = v.strip()
        if s.startswith("["):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    return [str(i).strip() for i in arr]
            except Exception:
                pass
        return [i.strip() for i in s.split(",") if i.strip()]
    
    # Browser Service
    BROWSER_SERVICE_URL: str = "http://browser-service:3000"
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Pydantic v2 settings config (replaces deprecated class Config)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

# Initialize settings
settings = Settings()

def apply_env_from_settings(s: Settings) -> None:
    """
    Mirror important API keys from .env (loaded by pydantic-settings) into process
    environment for third-party SDKs that read directly from os.environ.
    Does not override variables already present in the environment.
    """
    mapping = {
        "AGENTMAIL_API_KEY": s.AGENTMAIL_API_KEY,
        "AGENTMAIL_DOMAIN": s.AGENTMAIL_DOMAIN,
        "OPENAI_API_KEY": s.OPENAI_API_KEY,
        "ANTHROPIC_API_KEY": s.ANTHROPIC_API_KEY,
    }
    for k, v in mapping.items():
        if v and not os.environ.get(k):
            os.environ[k] = str(v)

apply_env_from_settings(settings)
