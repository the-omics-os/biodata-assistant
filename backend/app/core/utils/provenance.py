from __future__ import annotations

from typing import Optional, Dict, Any
from datetime import datetime
import logging

from sqlalchemy.exc import OperationalError
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
    Async-friendly provenance logger with auto-init fallback.
    If the provenance table is missing, attempt to initialize the DB and retry once.
    Never raises; provenance must not break primary workflows.
    """
    payload: Dict[str, Any] = {
        "actor": actor,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details or {},
        "ip_address": ip_address,
        "user_agent": user_agent,
        "created_at": datetime.utcnow(),
    }

    session = SessionLocal()
    try:
        record = Provenance(**payload)
        session.add(record)
        session.commit()
        return
    except Exception as e:
        # Detect "no such table" and attempt auto-init + single retry
        msg = ""
        try:
            msg = str(e).lower()
        except Exception:
            msg = ""
        missing_table = ("no such table" in msg) or isinstance(e, OperationalError)

        if missing_table:
            try:
                from app.core.database import init_db
                await init_db()
                try:
                    # retry once with a fresh record
                    record = Provenance(**payload)
                    session.add(record)
                    session.commit()
                    return
                except Exception as e2:
                    logger.error(f"Provenance retry failed after init: {e2}")
                    try:
                        session.rollback()
                    except Exception:
                        pass
            except Exception as init_err:
                logger.error(f"DB init failed during provenance logging: {init_err}")

        # Final fallback: log and swallow
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
