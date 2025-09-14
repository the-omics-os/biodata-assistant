from __future__ import annotations

import logging
from typing import Dict, Optional

from pydantic import BaseModel, EmailStr
from pydantic_ai import Agent, RunContext, ModelRetry
from pydantic_ai.models.bedrock import BedrockConverseModel
from app.config import settings
from app.core.utils.provenance import log_provenance
from app.utils.email_templates import generate_email_template
from app.core.integrations.agentmail_client import AgentMailClient, EmailMessage

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


class ProductInviteParams(BaseModel):
    lead_id: str
    repo: str
    issue_title: str
    recipient_name: str
    recipient_email: EmailStr
    persona_name: str
    persona_title: str
    persona_from_email: EmailStr
    message_style: str = "casual"
    omics_os_url: str = "https://www.omics-os.com"

model =BedrockConverseModel( "us.anthropic.claude-sonnet-4-20250514-v1:0")

email_agent = Agent[EmailOutreachParams, EmailResult](
    'openai:gpt-4.1',
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
    """Send email via AgentMailClient (AsyncAgentMail wrapper)."""
    if _requires_human_approval(ctx.deps):
        await log_provenance(
            actor=ctx.deps.requester_email,
            action="outreach_requires_approval",
            resource_type="outreach",
            resource_id=ctx.deps.dataset_id,
            details={"contact": ctx.deps.contact_email},
        )
        return {"success": False, "status": "pending_approval", "message_id": None, "thread_id": None}  # type: ignore[return-value]

    client = AgentMailClient()
    message = EmailMessage(
        to=ctx.deps.contact_email,
        from_email=ctx.deps.requester_email,
        subject=email_content.get("subject", ""),
        body=email_content.get("body", ""),
        metadata={
            "dataset_id": ctx.deps.dataset_id,
            "thread_type": "data_request",
            "requester": str(ctx.deps.requester_email),
        },
    )

    result = await client.send_email(message)

    if result.get("success"):
        await log_provenance(
            actor=ctx.deps.requester_email,
            action="sent_outreach",
            resource_type="outreach",
            resource_id=ctx.deps.dataset_id,
            details={"recipient": str(ctx.deps.contact_email), "message_id": result.get("message_id")},
        )
        return {
            "success": True,
            "status": "sent",
            "message_id": result.get("message_id"),  # type: ignore[return-value]
            "thread_id": result.get("thread_id"),  # type: ignore[return-value]
        }

    # Failure path with transient retry signaling
    status_code = result.get("status_code")
    error = result.get("error", "")

    await log_provenance(
        actor=ctx.deps.requester_email,
        action="outreach_failed",
        resource_type="outreach",
        resource_id=ctx.deps.dataset_id,
        details={"recipient": str(ctx.deps.contact_email), "status_code": status_code, "error": str(error)},
    )

    try:
        if status_code is not None:
            sc = int(status_code)
            if sc in (408, 429) or (500 <= sc < 600):
                raise ModelRetry("AgentMail transient error, retrying")
        if "rate" in str(error).lower():
            raise ModelRetry("Rate limited, will retry")
    except Exception:
        # If conversion fails, ignore and return failed
        pass

    return {"success": False, "status": "failed", "message_id": None, "thread_id": None}  # type: ignore[return-value]


async def send_outreach_direct(params: EmailOutreachParams) -> Dict[str, Optional[str]]:
    """
    Deterministic email send that bypasses the LLM agent and returns structured JSON.
    - Composes the email using our template utilities
    - Applies PHI/seniority gate
    - Sends via AgentMailClient
    - Returns a dict compatible with EmailResult fields
    """
    # PHI / seniority gate
    if _requires_human_approval(params):
        await log_provenance(
            actor=params.requester_email,
            action="outreach_requires_approval",
            resource_type="outreach",
            resource_id=params.dataset_id,
            details={"contact": params.contact_email},
        )
        return {
            "success": False,
            "status": "pending_approval",
            "message_id": None,
            "thread_id": None,
            "error_message": None,
        }

    # Compose
    template = generate_email_template(
        template_type="data_request",
        dataset_title=params.dataset_title,
        requester_name=params.requester_name,
        requester_title=params.requester_title,
        contact_name=params.contact_name,
        project_description=params.project_description,
    )
    if params.urgency == "high":
        template["subject"] = f"[URGENT] {template.get('subject','')}"

    # Send
    client = AgentMailClient()
    message = EmailMessage(
        to=params.contact_email,
        from_email=params.requester_email,
        subject=template.get("subject", ""),
        body=template.get("body", ""),
        metadata={
            "dataset_id": params.dataset_id,
            "thread_type": "data_request",
            "requester": str(params.requester_email),
        },
    )

    result = await client.send_email(message)

    if result.get("success"):
        await log_provenance(
            actor=params.requester_email,
            action="sent_outreach",
            resource_type="outreach",
            resource_id=params.dataset_id,
            details={"recipient": str(params.contact_email), "message_id": result.get("message_id")},
        )
        return {
            "success": True,
            "status": "sent",
            "message_id": result.get("message_id"),
            "thread_id": result.get("thread_id"),
            "error_message": None,
        }

    # Failure
    await log_provenance(
        actor=params.requester_email,
        action="outreach_failed",
        resource_type="outreach",
        resource_id=params.dataset_id,
        details={"recipient": str(params.contact_email), "status_code": result.get("status_code"), "error": str(result.get("error"))},
    )
    return {
        "success": False,
        "status": "failed",
        "message_id": None,
        "thread_id": None,
        "error_message": str(result.get("error")) if result.get("error") else None,
    }


# Create a separate agent for product invitations
product_invite_agent = Agent[ProductInviteParams, EmailResult](
    model,
    deps_type=ProductInviteParams,
    output_type=EmailResult,
    instructions=(
        "You are a casual, empathetic outreach specialist for omics-os.\n"
        "You help struggling bioinformatics users discover our no-code solution.\n"
        "Your tone is:\n"
        "- Casual and friendly ('hei!', emojis)\n"
        "- Empathetic (acknowledge their struggle)\n"
        "- Helpful without being pushy\n"
        "- Technical but approachable\n\n"
        "Always maintain the casual, helpful persona matching the 'hei I saw you were struggling...' style.\n"
    ),
)


@product_invite_agent.tool
async def compose_product_invite(ctx: RunContext[ProductInviteParams]) -> Dict[str, str]:
    """Generate casual product invitation email for GitHub issue prospects."""
    template = generate_email_template(
        template_type="product_invite",
        persona_name=ctx.deps.persona_name,
        persona_title=ctx.deps.persona_title,
        repo=ctx.deps.repo,
        issue_title=ctx.deps.issue_title,
        recipient_name=ctx.deps.recipient_name,
        message_style=ctx.deps.message_style,
        omics_os_url=ctx.deps.omics_os_url,
    )

    await log_provenance(
        actor="product_invite_agent",
        action="compose_product_invite",
        resource_type="lead",
        resource_id=ctx.deps.lead_id,
        details={"subject": template.get("subject", ""), "repo": ctx.deps.repo},
    )
    return template


@product_invite_agent.tool(retries=2)
async def send_product_invite_via_agentmail(ctx: RunContext[ProductInviteParams], email_content: Dict[str, str]) -> Dict[str, Optional[str]]:
    """Send product invitation email via AgentMail using persona's from_email."""
    client = AgentMailClient()
    message = EmailMessage(
        to=ctx.deps.recipient_email,
        from_email=ctx.deps.persona_from_email,
        subject=email_content.get("subject", ""),
        body=email_content.get("body", ""),
        metadata={
            "lead_id": ctx.deps.lead_id,
            "thread_type": "product_invite",
            "persona": ctx.deps.persona_name,
            "repo": ctx.deps.repo,
        },
    )

    result = await client.send_email(message)

    if result.get("success"):
        await log_provenance(
            actor=ctx.deps.persona_from_email,
            action="sent_product_invite",
            resource_type="lead",
            resource_id=ctx.deps.lead_id,
            details={"recipient": str(ctx.deps.recipient_email), "message_id": result.get("message_id"), "persona": ctx.deps.persona_name},
        )
        return {
            "success": True,
            "status": "sent",
            "message_id": result.get("message_id"),  # type: ignore[return-value]
            "thread_id": result.get("thread_id"),  # type: ignore[return-value]
        }

    # Failure path with transient retry signaling
    status_code = result.get("status_code")
    error = result.get("error", "")

    await log_provenance(
        actor=ctx.deps.persona_from_email,
        action="product_invite_failed",
        resource_type="lead",
        resource_id=ctx.deps.lead_id,
        details={"recipient": str(ctx.deps.recipient_email), "status_code": status_code, "error": str(error)},
    )

    try:
        if status_code is not None:
            sc = int(status_code)
            if sc in (408, 429) or (500 <= sc < 600):
                raise ModelRetry("AgentMail transient error, retrying")
        if "rate" in str(error).lower():
            raise ModelRetry("Rate limited, will retry")
    except Exception:
        # If conversion fails, ignore and return failed
        pass

    return {"success": False, "status": "failed", "message_id": None, "thread_id": None}  # type: ignore[return-value]


async def send_product_invite_direct(params: ProductInviteParams) -> Dict[str, Optional[str]]:
    """
    Deterministic product invite send that bypasses the LLM agent and returns structured JSON.
    - Composes the casual invite using product_invite_template 
    - Sends via AgentMailClient using persona's from_email
    - Returns a dict compatible with EmailResult fields
    """
    # Compose casual email
    template = generate_email_template(
        template_type="product_invite",
        persona_name=params.persona_name,
        persona_title=params.persona_title,
        repo=params.repo,
        issue_title=params.issue_title,
        recipient_name=params.recipient_name,
        message_style=params.message_style,
        omics_os_url=params.omics_os_url,
    )

    # Send via AgentMail using persona's from_email
    client = AgentMailClient()
    message = EmailMessage(
        to=params.recipient_email,
        from_email=params.persona_from_email,
        subject=template.get("subject", ""),
        body=template.get("body", ""),
        metadata={
            "lead_id": params.lead_id,
            "thread_type": "product_invite",
            "persona": params.persona_name,
            "repo": params.repo,
        },
    )

    result = await client.send_email(message)

    if result.get("success"):
        await log_provenance(
            actor=params.persona_from_email,
            action="sent_product_invite",
            resource_type="lead",
            resource_id=params.lead_id,
            details={"recipient": str(params.recipient_email), "message_id": result.get("message_id"), "persona": params.persona_name},
        )
        return {
            "success": True,
            "status": "sent",
            "message_id": result.get("message_id"),
            "thread_id": result.get("thread_id"),
            "error_message": None,
        }

    # Failure
    await log_provenance(
        actor=params.persona_from_email,
        action="product_invite_failed",
        resource_type="lead",
        resource_id=params.lead_id,
        details={"recipient": str(params.recipient_email), "status_code": result.get("status_code"), "error": str(result.get("error"))},
    )
    return {
        "success": False,
        "status": "failed",
        "message_id": None,
        "thread_id": None,
        "error_message": str(result.get("error")) if result.get("error") else None,
    }
