from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.enums import DatasetSource, AccessType, OutreachStatus, TaskStatus, TaskType

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
    extra_metadata: Optional[Dict[str, Any]] = {}

class DatasetResponse(DatasetCreate):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class SearchRequest(BaseModel):
    query: str = Field(..., description="Research question or search terms")
    modalities: Optional[List[str]] = Field(None, description="Filter by data modalities")
    cancer_types: Optional[List[str]] = Field(None, description="Filter by cancer types")
    sources: Optional[List[DatasetSource]] = Field(None, description="Databases to search")
    include_internal: bool = Field(True, description="Include internal datasets")
    max_results: int = Field(20, ge=1, le=100)

class SearchResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str

class OutreachRequest(BaseModel):
    dataset_id: str
    requester_email: EmailStr
    requester_name: str
    contact_email: EmailStr
    contact_name: Optional[str] = None
    email_subject: str
    email_body: str
    approval_required: bool = False

class OutreachResponse(BaseModel):
    id: str
    dataset_id: str
    requester_email: str
    requester_name: Optional[str]
    contact_email: str
    contact_name: Optional[str]
    status: OutreachStatus
    email_subject: Optional[str]
    email_body: Optional[str]
    created_at: datetime
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class TaskResponse(BaseModel):
    id: str
    type: str
    status: TaskStatus
    user_email: Optional[str]
    input_data: Optional[Dict[str, Any]]
    output_data: Optional[Dict[str, Any]]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    job_title: Optional[str] = None
    department: Optional[str] = None
    company: Optional[str] = None
    source: str = "manual"

class UserResponse(UserCreate):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime
