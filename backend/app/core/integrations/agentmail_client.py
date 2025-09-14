from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# AgentMail SDK (async + sync) with defensive import
try:
    from agentmail import AsyncAgentMail, AgentMail  # type: ignore
    from agentmail.core.api_error import ApiError  # type: ignore
except Exception:  # pragma: no cover - allow resilience in dev environments
    AsyncAgentMail = None  # type: ignore[assignment]
    AgentMail = None  # type: ignore[assignment]

    class ApiError(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int = 500, body: Any = None) -> None:
            super().__init__(str(body))
            self.status_code = status_code
            self.body = body


class EmailMessage(BaseModel):
    """Email message structure"""
    to: EmailStr
    from_email: EmailStr
    subject: str
    body: str
    metadata: Dict[str, Any] = {}
    attachments: List[Dict[str, Any]] = []


class AgentMailClient:
    """
    AgentMail client wrapper using the AsyncAgentMail SDK.
    Reference: agentmail-doc.md - Async client usage, retries, raw response.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        api_key = settings.AGENTMAIL_API_KEY or ""
        self.enabled = bool(api_key and AsyncAgentMail is not None)

        self.client = None
        self.sync_client = None
        if self.enabled:
            try:
                self.client = AsyncAgentMail(api_key=api_key, timeout=timeout)  # type: ignore[call-arg]
            except Exception as e:
                logger.warning(f"Failed to initialize AsyncAgentMail: {e}")
                self.client = None
                self.enabled = False

            try:
                if AgentMail is not None:
                    self.sync_client = AgentMail(api_key=api_key)  # type: ignore[call-arg]
            except Exception as e:
                logger.debug(f"Failed to initialize sync AgentMail (optional): {e}")
                self.sync_client = None

    async def send_email(self, message: EmailMessage, max_retries: int = 2) -> Dict[str, Any]:
        """
        Send email with retry logic.
        If SDK/API key not available, simulate a successful send for MVP demos.
        """
        if not self.enabled or self.client is None:
            logger.warning("AgentMail SDK disabled or API key missing; simulating send.")
            await self._log_provenance(
                action="email_simulated_send",
                details={
                    "to": str(message.to),
                    "subject": message.subject,
                },
            )
            return {
                "success": True,
                "message_id": "simulated-message-id",
                "thread_id": "simulated-thread-id",
                "status": "sent",
                "headers": {},
            }

        try:
            # Prefer raw response to access headers + structured data
            with_raw = self.client.messages.with_raw_response  # type: ignore[attr-defined]
            response = await with_raw.create(  # type: ignore[call-arg]
                to=str(message.to),
                from_email=str(message.from_email),
                subject=message.subject,
                body=message.body,
                metadata=message.metadata,
                attachments=message.attachments or None,
                request_options={"max_retries": max_retries, "timeout_in_seconds": 20},
            )

            headers = dict(getattr(response, "headers", {}) or {})
            data = getattr(response, "data", None)

            msg_id = getattr(data, "id", None)
            thread_id = getattr(data, "thread_id", None)

            await self._log_provenance(
                action="email_sent",
                details={
                    "to": str(message.to),
                    "subject": message.subject,
                    "message_id": msg_id,
                    "thread_id": thread_id,
                },
            )

            return {
                "success": True,
                "message_id": msg_id,
                "thread_id": thread_id,
                "status": "sent",
                "headers": headers,
            }

        except ApiError as e:  # type: ignore[misc]
            logger.error(f"AgentMail API error: {getattr(e, 'status_code', 'n/a')}, body={getattr(e, 'body', '')}")
            await self._log_provenance(
                action="email_failed",
                details={
                    "to": str(message.to),
                    "subject": message.subject,
                    "status_code": getattr(e, "status_code", None),
                    "error": str(getattr(e, "body", "")),
                },
            )
            return {
                "success": False,
                "status": "failed",
                "error": str(getattr(e, "body", "")),
                "status_code": getattr(e, "status_code", None),
            }
        except Exception as e:
            logger.error(f"AgentMail unexpected error: {e}")
            await self._log_provenance(
                action="email_failed",
                details={"to": str(message.to), "subject": message.subject, "error": str(e)},
            )
            return {"success": False, "status": "failed", "error": str(e)}

    async def create_inbox(self) -> Dict[str, Any]:
        """Create a new inbox for receiving replies."""
        if not self.enabled or self.client is None:
            return {"success": True, "inbox_id": "simulated-inbox", "email": "inbox@example.com"}

        try:
            inbox = await self.client.inboxes.create()  # type: ignore[union-attr]
            return {
                "success": True,
                "inbox_id": getattr(inbox, "id", None),
                "email": getattr(inbox, "email", None),
            }
        except ApiError as e:  # type: ignore[misc]
            return {"success": False, "error": str(getattr(e, "body", ""))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_messages(self, inbox_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List messages in an inbox (optionally filter by inbox_id)."""
        if not self.enabled or self.client is None:
            return []

        try:
            params: Dict[str, Any] = {"inbox_id": inbox_id} if inbox_id else {}
            messages = await self.client.messages.list(**params)  # type: ignore[union-attr]
            out: List[Dict[str, Any]] = []
            for msg in messages:
                out.append(
                    {
                        "id": getattr(msg, "id", None),
                        "from": getattr(msg, "from_email", None),
                        "subject": getattr(msg, "subject", None),
                        "received_at": getattr(msg, "received_at", None),
                        "thread_id": getattr(msg, "thread_id", None),
                    }
                )
            return out
        except ApiError as e:  # type: ignore[misc]
            logger.error(f"Error listing messages: {getattr(e, 'body', '')}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing messages: {e}")
            return []

    async def _log_provenance(self, action: str, details: Dict[str, Any]) -> None:
        """Log email actions for audit trail"""
        try:
            from app.core.utils.provenance import log_provenance
            await log_provenance(
                actor="agentmail_client",
                action=action,
                resource_type="email",
                details=details,
            )
        except Exception as e:
            logger.debug(f"Provenance logging failed: {e}")
