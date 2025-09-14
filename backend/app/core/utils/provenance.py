from __future__ import annotations

from typing import Optional, Dict, Any
from datetime import datetime
import logging

from app.core.database import SessionLocal
from app.models.database import Provenance

logger = logging.getLogger(__name__)


async def log_provenance(
    actor: str,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """
    Async-friendly provenance logger.
    Uses a synchronous SQLAlchemy session under the hood (acceptable for short writes).
    """
    session = SessionLocal()
    try:
        record = Provenance(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.utcnow(),
        )
        session.add(record)
        session.commit()
    except Exception as e:
        # Do not raise — provenance must not break primary workflows
        logger.error(f"Failed to write provenance: {e}")
        try:
            session.rollback()
        except Exception:
            pass
    finally:
        try:
            session.close()
        except Exception:
            pass
