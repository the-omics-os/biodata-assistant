from __future__ import annotations

import logging
from typing import Dict, Optional

from pydantic import BaseModel, EmailStr
from pydantic_ai import Agent, RunContext, ModelRetry
from app.config import settings
from app.core.utils.provenance import log_provenance
from app.utils.email_templates import generate_email_template

# AgentMail SDK
try:
    from agentmail import AsyncAgentMail
    from agentmail.core.api_error import ApiError
except Exception:  # pragma: no cover
    AsyncAgentMail = None  # type: ignore[assignment]
    ApiError = Exception  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class EmailOutreachParams(BaseModel):
    dataset_id: str
    dataset_title: str
    requester_name: str
    requester_email: EmailStr
    requester_title: str
    contact_name: str
    contact_email: EmailStr
    project_description: str
    urgency: str = "normal"  # 'low'|'normal'|'high'


class EmailResult(BaseModel):
    success: bool
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    status: str
    requires_approval: bool = False
    error_message: Optional[str] = None


email_agent = Agent[EmailOutreachParams, EmailResult](
    "openai:gpt-4o",
    deps_type=EmailOutreachParams,
    output_type=EmailResult,
    instructions=(
        "You are a professional scientific communication specialist.\n"
        "Compose clear, respectful outreach emails for data access requests.\n"
        "Emphasize:\n"
        "- Research purpose and cancer research impact\n"
        "- Data handling compliance and ethics\n"
        "- Professional courtesy and collaboration\n"
        "- Clear next steps\n\n"
        "Flag for approval if:\n"
        "- Dataset hints at PHI/sensitive content\n"
        "- Contact appears to be senior management\n"
        "- Multiple datasets requested simultaneously\n"
    ),
)


@email_agent.tool
async def compose_email(ctx: RunContext[EmailOutreachParams]) -> Dict[str, str]:
    """Generate professional email content with cancer research focus."""
    template = generate_email_template(
        template_type="data_request",
        dataset_title=ctx.deps.dataset_title,
        requester_name=ctx.deps.requester_name,
        requester_title=ctx.deps.requester_title,
        contact_name=ctx.deps.contact_name,
        project_description=ctx.deps.project_description,
    )
    if ctx.deps.urgency == "high":
        template["subject"] = f"[URGENT] {template['subject']}"

    await log_provenance(
        actor="email_agent",
        action="compose_email",
        resource_type="outreach",
        resource_id=ctx.deps.dataset_id,
        details={"subject": template.get("subject", "")},
    )
    return template


def _requires_human_approval(params: EmailOutreachParams) -> bool:
    """Simple PHI and seniority gating."""
    sensitive_keywords = ["phi", "clinical", "patient", "identifiable"]
    if any(kw in params.dataset_title.lower() for kw in sensitive_keywords):
        return True

    senior_titles = ["CEO", "CTO", "Director", "VP", "Head of", "Chief", "President"]
    if any(title.lower() in params.contact_name.lower() for title in senior_titles):
        return True

    return False


@email_agent.tool(retries=2)
async def send_via_agentmail(ctx: RunContext[EmailOutreachParams], email_content: Dict[str, str]) -> Dict[str, Optional[str]]:
    """Send email through AgentMail API."""
    if _requires_human_approval(ctx.deps):
        await log_provenance(
            actor=ctx.deps.requester_email,
            action="outreach_requires_approval",
            resource_type="outreach",
            resource_id=ctx.deps.dataset_id,
            details={"contact": ctx.deps.contact_email},
        )
        # Return a status that indicates approval queueing
        return {"success": False, "status": "pending_approval", "message_id": None, "thread_id": None}  # type: ignore[return-value]

    if AsyncAgentMail is None or not settings.AGENTMAIL_API_KEY:
        # No SDK or API key configured: simulate queued/sent state for dev
        logger.warning("AgentMail SDK or API key missing; simulating send.")
        await log_provenance(
            actor=ctx.deps.requester_email,
            action="outreach_simulated_send",
            resource_type="outreach",
            resource_id=ctx.deps.dataset_id,
            details={"recipient": ctx.deps.contact_email, "subject": email_content.get("subject", "")},
        )
        return {"success": True, "status": "sent", "message_id": "dev-simulated", "thread_id": "dev-thread"}  # type: ignore[return-value]

    client = AsyncAgentMail(api_key=settings.AGENTMAIL_API_KEY)
    try:
        resp = await client.messages.create(
            to=str(ctx.deps.contact_email),
            from_email=str(ctx.deps.requester_email),
            subject=email_content.get("subject", ""),
            body=email_content.get("body", ""),
            metadata={
                "dataset_id": ctx.deps.dataset_id,
                "thread_type": "data_request",
                "requester": str(ctx.deps.requester_email),
            },
        )
        await log_provenance(
            actor=ctx.deps.requester_email,
            action="sent_outreach",
            resource_type="outreach",
            resource_id=ctx.deps.dataset_id,
            details={"recipient": str(ctx.deps.contact_email), "message_id": getattr(resp, "id", None)},
        )
        return {
            "success": True,
            "status": "sent",
            "message_id": getattr(resp, "id", None),
            "thread_id": getattr(resp, "thread_id", None),
        }
    except ApiError as e:  # type: ignore[misc]
        # Retry on rate limiting or transient errors via ModelRetry
        body = getattr(e, "body", "")
        status = getattr(e, "status_code", 500)
        await log_provenance(
            actor=ctx.deps.requester_email,
            action="outreach_failed",
            resource_type="outreach",
            resource_id=ctx.deps.dataset_id,
            details={"recipient": str(ctx.deps.contact_email), "status_code": status, "body": str(body)},
        )
        if int(status) in (408, 429) or (500 <= int(status) < 600):
            raise ModelRetry("AgentMail transient error, retrying")
        return {"success": False, "status": "failed", "message_id": None, "thread_id": None}  # type: ignore[return-value]
    except Exception as e:
        await log_provenance(
            actor=ctx.deps.requester_email,
            action="outreach_failed",
            resource_type="outreach",
            resource_id=ctx.deps.dataset_id,
            details={"recipient": str(ctx.deps.contact_email), "error": str(e)},
        )
        if "rate" in str(e).lower():
            raise ModelRetry("Rate limited, will retry")
        return {"success": False, "status": "failed", "message_id": None, "thread_id": None}  # type: ignore[return-value]
