from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, ForeignKey, Text, Float
from sqlalchemy.sql import func
from app.core.database import Base
import uuid

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String)
    job_title = Column(String)
    department = Column(String)
    company = Column(String)
    source = Column(String, default="manual")  # 'linkedin'|'manual'|'mock'
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class Dataset(Base):
    __tablename__ = "datasets"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String, nullable=False)  # 'GEO'|'PRIDE'|'ENSEMBL'|'INTERNAL'
    accession = Column(String, index=True)  # e.g., GSE12345
    title = Column(String, nullable=False)
    description = Column(Text)
    modalities = Column(JSON)  # List of strings: ['scRNA-seq','proteomics']
    cancer_types = Column(JSON)  # List of strings: ['lung adenocarcinoma', 'NSCLC']
    organism = Column(String)  # 'Homo sapiens'
    sample_size = Column(Integer)
    download_url = Column(String)
    access_type = Column(String)  # 'public'|'request'|'restricted'
    owner_email = Column(String)
    owner_name = Column(String)
    publication_url = Column(String)
    extra_metadata = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class OutreachRequest(Base):
    __tablename__ = "outreach_requests"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id = Column(String, ForeignKey("datasets.id"))
    requester_email = Column(String, nullable=False)
    requester_name = Column(String)
    contact_email = Column(String, nullable=False)
    contact_name = Column(String)
    status = Column(String, nullable=False, default="draft")
    email_subject = Column(String)
    email_body = Column(Text)
    thread_id = Column(String)
    message_id = Column(String)
    agentmail_id = Column(String)
    approval_required = Column(Boolean, default=False)
    approved_at = Column(DateTime)
    approved_by = Column(String)
    sent_at = Column(DateTime)
    replied_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class Provenance(Base):
    __tablename__ = "provenance"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor = Column(String, nullable=False)  # user email or system component
    action = Column(String, nullable=False)  # 'search_initiated'|'dataset_found'|'outreach_sent'|etc
    resource_type = Column(String)  # 'dataset'|'outreach'|'user'
    resource_id = Column(String)
    details = Column(JSON)
    ip_address = Column(String)
    user_agent = Column(String)
    created_at = Column(DateTime, server_default=func.now())

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String, nullable=False)  # 'search'|'find_contact'|'send_email'
    status = Column(String, nullable=False, default="pending")  # 'pending'|'running'|'completed'|'failed'
    user_email = Column(String)
    input_data = Column(JSON)
    output_data = Column(JSON)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class Lead(Base):
    __tablename__ = "leads"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String, nullable=False, default="github-issues")  # 'github-issues'
    repo = Column(String, nullable=False)  # 'scverse/scanpy' | 'scverse/anndata'
    issue_number = Column(Integer, nullable=False)
    issue_url = Column(String, nullable=False, unique=True, index=True)
    issue_title = Column(String, nullable=False)
    issue_labels = Column(JSON, default=lambda: [])  # List of strings
    issue_created_at = Column(DateTime, nullable=True)
    user_login = Column(String, nullable=False)
    profile_url = Column(String, nullable=False)
    email = Column(String, nullable=True)
    website = Column(String, nullable=True)
    signals = Column(JSON, default=lambda: {})  # Scoring signals dict
    novice_score = Column(Float, nullable=False, default=0.0)  # 0.0 to 1.0
    stage = Column(String, nullable=False, default="new")  # LeadStage values
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
