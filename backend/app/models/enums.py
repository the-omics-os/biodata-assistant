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

class TaskType(str, Enum):
    SEARCH = "search"
    FIND_CONTACT = "find_contact"
    SEND_EMAIL = "send_email"
