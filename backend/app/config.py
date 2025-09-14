from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional, List
import os
import logging
import json

class Settings(BaseSettings):
    # Application
    APP_NAME: str = Field(default="Biodata Assistant", description="Application name")
    VERSION: str = Field(default="1.0.0", description="Application version")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # Database
    DATABASE_URL: str = Field(default="sqlite:///./biodata.db", description="Database connection URL")

    # Redis / Background Tasks
    REDIS_URL: Optional[str] = Field(default=None, description="Redis connection URL for Celery")
    CELERY_BROKER_URL: Optional[str] = Field(default=None, description="Celery broker URL")
    CELERY_RESULT_BACKEND: Optional[str] = Field(default=None, description="Celery result backend URL")
    
    # API Keys
    AGENTMAIL_API_KEY: Optional[str] = Field(default=None, description="AgentMail API key")
    AGENTMAIL_DOMAIN: Optional[str] = Field(default=None, description="AgentMail domain")
    AGENTMAIL_WEBHOOK_SECRET: Optional[str] = Field(default=None, description="AgentMail webhook secret")
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, description="Anthropic API key")
    
    # Security
    SECRET_KEY: str = Field(default="change-me-in-production", description="Secret key for security")
    CORS_ORIGINS: str = Field(default="http://localhost:3000,http://localhost:8080", description="CORS allowed origins")

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
    BROWSER_SERVICE_URL: str = Field(default="http://browser-service:3000", description="Browser service URL")
    
    # Requester Information
    REQUESTER_EMAIL: str = Field(default="kevin.yar@omics-os.com", description="Default requester email")
    REQUESTER_NAME: str = Field(default="Kevin Yar", description="Default requester name")
    REQUESTER_TITLE: str = Field(default="CEO", description="Default requester title")

    # LinkedIn Credentials
    LINKEDIN_EMAIL: Optional[str] = Field(default=None, description="LinkedIn login email")
    LINKEDIN_PW: Optional[str] = Field(default=None, description="LinkedIn login password")
    LINKEDIN_COMPANY_URL: Optional[str] = Field(default=None, description="LinkedIn company URL for employee search")
    LINKEDIN_OUTREACH_ENABLED: bool = Field(default=False, description="Enable LinkedIn outreach (safety flag)")

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, description="Rate limit per minute")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Background Task Configuration
    ENABLE_BACKGROUND_TASKS: bool = Field(default=True, description="Enable background task processing")
    GITHUB_PROSPECTING_ENABLED: bool = Field(default=True, description="Enable automated GitHub prospecting")
    EMAIL_MONITORING_ENABLED: bool = Field(default=True, description="Enable automated email monitoring")
    AUTOMATED_OUTREACH_ENABLED: bool = Field(default=False, description="Enable automated outreach (requires approval)")

    # GitHub Prospecting Settings
    GITHUB_TARGET_REPOS: str = Field(default="scverse/scanpy,scverse/anndata", description="Target GitHub repositories for prospecting")
    GITHUB_MAX_ISSUES_PER_REPO: int = Field(default=25, description="Maximum issues to fetch per repository")
    GITHUB_PROSPECTING_SCHEDULE_HOUR: int = Field(default=9, description="Hour to run daily prospecting (UTC)")

    # Email Monitoring Settings
    EMAIL_MONITORING_INTERVAL_SECONDS: int = Field(default=30, description="Email monitoring check interval in seconds")
    OUTREACH_PROCESSING_INTERVAL_MINUTES: int = Field(default=5, description="Outreach queue processing interval in minutes")
    
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
