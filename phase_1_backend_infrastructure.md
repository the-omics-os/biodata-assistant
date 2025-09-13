# Phase 1: Backend Infrastructure & Core Setup

## Overview
Establish the foundational backend infrastructure using FastAPI, including database models, API structure, and core configuration for the biodata-assistant system that solves cancer researchers' data acquisition pain points.

## Goals
- Set up FastAPI application with proper project structure
- Create SQLite database models for hackathon MVP
- Implement core configuration and environment management
- Establish API versioning and routing structure
- Set up basic logging and error handling

## Directory Structure
```
biodata-assistant/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI application entry point
│   │   ├── config.py               # Configuration management
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── router.py       # Main API router
│   │   │   │   ├── search.py       # Dataset search endpoints
│   │   │   │   ├── contacts.py     # Contact discovery endpoints
│   │   │   │   ├── outreach.py     # Email outreach endpoints
│   │   │   │   ├── webhooks.py     # Webhook receivers
│   │   │   │   ├── status.py       # Task status endpoints
│   │   │   │   └── datasets.py     # Dataset management endpoints
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── database.py         # Database connection
│   │   │   ├── security.py         # Security utilities
│   │   │   └── logging.py          # Logging configuration
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── database.py         # SQLAlchemy models
│   │   │   ├── schemas.py          # Pydantic schemas
│   │   │   └── enums.py            # Enum definitions
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── exceptions.py       # Custom exceptions
│   ├── requirements.txt
│   └── .env.example
└── docker-compose.yml
```

## Database Schema

### Tables

#### users
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    job_title TEXT,
    department TEXT,
    company TEXT,
    source TEXT DEFAULT 'manual', -- 'linkedin'|'manual'|'mock'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### datasets
```sql
CREATE TABLE datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL, -- 'GEO'|'PRIDE'|'ENSEMBL'|'INTERNAL'
    accession TEXT, -- e.g., GSE12345
    title TEXT NOT NULL,
    description TEXT,
    modalities TEXT[], -- ['scRNA-seq','proteomics']
    cancer_types TEXT[], -- ['lung adenocarcinoma', 'NSCLC']
    organism TEXT, -- 'Homo sapiens'
    sample_size INTEGER,
    download_url TEXT,
    access_type TEXT, -- 'public'|'request'|'restricted'
    owner_email TEXT,
    owner_name TEXT,
    publication_url TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### outreach_requests
```sql
CREATE TABLE outreach_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID REFERENCES datasets(id),
    requester_email TEXT NOT NULL,
    requester_name TEXT,
    contact_email TEXT NOT NULL,
    contact_name TEXT,
    status TEXT NOT NULL DEFAULT 'draft', -- 'draft'|'queued'|'sent'|'delivered'|'replied'|'closed'
    email_subject TEXT,
    email_body TEXT,
    thread_id TEXT,
    message_id TEXT,
    agentmail_id TEXT,
    approval_required BOOLEAN DEFAULT FALSE,
    approved_at TIMESTAMP,
    approved_by TEXT,
    sent_at TIMESTAMP,
    replied_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### provenance
```sql
CREATE TABLE provenance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor TEXT NOT NULL, -- user email or system component
    action TEXT NOT NULL, -- 'search_initiated'|'dataset_found'|'outreach_sent'|etc
    resource_type TEXT, -- 'dataset'|'outreach'|'user'
    resource_id UUID,
    details JSONB,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### tasks
```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type TEXT NOT NULL, -- 'search'|'find_contact'|'send_email'
    status TEXT NOT NULL DEFAULT 'pending', -- 'pending'|'running'|'completed'|'failed'
    user_email TEXT,
    input_data JSONB,
    output_data JSONB,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Core Components

### 1. Configuration Management (app/config.py)
```python
from pydantic_settings import BaseSettings
from typing import Optional

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
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    
    # Browser Service
    BROWSER_SERVICE_URL: str = "http://browser-service:3000"
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    class Config:
        env_file = ".env"

settings = Settings()
```

### 2. FastAPI Application (app/main.py)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.v1.router import api_router
from app.config import settings
from app.core.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown
    pass

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")
```

### 3. Database Models (app/models/database.py)
```python
from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String)
    job_title = Column(String)
    department = Column(String)
    company = Column(String)
    source = Column(String, default="manual")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class Dataset(Base):
    __tablename__ = "datasets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String, nullable=False)
    accession = Column(String, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    modalities = Column(ARRAY(String))
    cancer_types = Column(ARRAY(String))
    organism = Column(String)
    sample_size = Column(Integer)
    download_url = Column(String)
    access_type = Column(String)
    owner_email = Column(String)
    owner_name = Column(String)
    publication_url = Column(String)
    metadata = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
```

### 4. Pydantic Schemas (app/models/schemas.py)
```python
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum

class DatasetSource(str, Enum):
    GEO = "GEO"
    PRIDE = "PRIDE"
    ENSEMBL = "ENSEMBL"
    INTERNAL = "INTERNAL"

class AccessType(str, Enum):
    PUBLIC = "public"
    REQUEST = "request"
    RESTRICTED = "restricted"

class OutreachStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    REPLIED = "replied"
    CLOSED = "closed"

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class DatasetCreate(BaseModel):
    source: DatasetSource
    accession: Optional[str] = None
    title: str
    description: Optional[str] = None
    modalities: List[str] = []
    cancer_types: List[str] = []
    organism: Optional[str] = "Homo sapiens"
    sample_size: Optional[int] = None
    download_url: Optional[str] = None
    access_type: AccessType = AccessType.PUBLIC
    owner_email: Optional[EmailStr] = None
    owner_name: Optional[str] = None
    publication_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}

class DatasetResponse(DatasetCreate):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

class SearchRequest(BaseModel):
    query: str = Field(..., description="Research question or search terms")
    modalities: Optional[List[str]] = Field(None, description="Filter by data modalities")
    cancer_types: Optional[List[str]] = Field(None, description="Filter by cancer types")
    sources: Optional[List[DatasetSource]] = Field(None, description="Databases to search")
    include_internal: bool = Field(True, description="Include internal datasets")
    max_results: int = Field(20, ge=1, le=100)

class OutreachRequest(BaseModel):
    dataset_id: UUID
    requester_email: EmailStr
    requester_name: str
    contact_email: EmailStr
    contact_name: Optional[str] = None
    email_subject: str
    email_body: str
    approval_required: bool = False

class TaskResponse(BaseModel):
    id: UUID
    type: str
    status: TaskStatus
    user_email: Optional[str]
    input_data: Optional[Dict[str, Any]]
    output_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
```

## API Endpoints

### Core Endpoints (Phase 1)

#### Health & Status
- `GET /health` - Health check endpoint
- `GET /api/v1/status` - API status and version info

#### Search
- `POST /api/v1/search` - Initiate dataset search
- `GET /api/v1/search/{task_id}` - Get search task status
- `GET /api/v1/search/{task_id}/results` - Get search results

#### Datasets
- `GET /api/v1/datasets` - List all datasets
- `GET /api/v1/datasets/{id}` - Get dataset details
- `POST /api/v1/datasets` - Manually add dataset
- `PUT /api/v1/datasets/{id}` - Update dataset
- `DELETE /api/v1/datasets/{id}` - Delete dataset

#### Tasks
- `GET /api/v1/tasks` - List all tasks
- `GET /api/v1/tasks/{id}` - Get task details
- `DELETE /api/v1/tasks/{id}` - Cancel task

## Implementation Priority

### Week 1 Sprint (Days 1-2 of Hackathon)
1. ✅ Set up project structure
2. ✅ Create database models and schemas
3. ✅ Implement core configuration
4. ✅ Set up FastAPI application with CORS
5. ✅ Create basic CRUD endpoints for datasets
6. ✅ Implement task tracking system
7. ✅ Add logging and error handling
8. ✅ Create Docker configuration

### Testing Checklist
- [ ] Database connection and migrations work
- [ ] All CRUD endpoints return proper responses
- [ ] Error handling returns appropriate status codes
- [ ] CORS headers allow frontend connection
- [ ] Environment variables load correctly
- [ ] Docker containers start successfully

## Dependencies (requirements.txt)
```
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
sqlalchemy==2.0.25
alembic==1.13.1
python-dotenv==1.0.0
httpx==0.26.0
redis==5.0.1
celery==5.3.4
python-multipart==0.0.6
```

## Docker Configuration (docker-compose.yml)
```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///./biodata.db
    volumes:
      - ./backend:/app
      - ./data:/app/data
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

## Next Phase
Phase 2 will implement the Pydantic AI agent system on top of this infrastructure, utilizing the documentation in `pydantic_doc.md`.
