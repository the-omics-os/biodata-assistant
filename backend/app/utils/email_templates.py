from __future__ import annotations

from typing import Dict, Optional


def generate_email_template(
    template_type: str,
    dataset_title: str,
    requester_name: str,
    requester_title: str,
    contact_name: str,
    project_description: str,
    organization: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generate a professional outreach email template focused on cancer research data requests.
    Returns a dict with 'subject' and 'body'.
    """
    org_line = f" at {organization}" if organization else ""

    if template_type == "data_request":
        subject = f"Data access request regarding \"{dataset_title}\" for cancer research"
        body = f"""Dear {contact_name},

I hope this message finds you well. My name is {requester_name}, {requester_title}{org_line}. 
We are conducting a study focused on cancer research, and your dataset "{dataset_title}" appears to be highly relevant to our objectives.

Project overview:
- Research focus: {project_description}
- Anticipated impact: advancing insights in oncology (e.g., P53/TP53, lung adenocarcinoma, TNBC, breast cancer)
- Data modalities of interest: genomics/transcriptomics/proteomics/imaging/microbiome (as applicable)

Request:
- Access to the dataset and associated metadata (where permissible)
- Any documentation or publications that may aid interpretation
- Preferred access method and any required forms/approvals

Compliance & handling:
- We follow strict data governance policies; no PHI or sensitive patient identifiers will be requested or handled without appropriate approvals.
- Data will be stored on secure, access-controlled systems, and used solely for the stated research objectives.
- If a Data Use Agreement (DUA) or additional review is required, we are happy to comply.

If you could share next steps or the appropriate process to request access, we would greatly appreciate it. 
Thank you for your time and for making this valuable resource available to the research community.

Best regards,
{requester_name}
{requester_title}{org_line}
"""
        return {"subject": subject, "body": body}

    # Default fallback
    subject = f"Request regarding \"{dataset_title}\""
    body = f"""Dear {contact_name},

My name is {requester_name}, {requester_title}{org_line}. I am reaching out regarding "{dataset_title}".
Could you advise on the appropriate process to request access and any required documentation?

Best regards,
{requester_name}
{requester_title}{org_line}
"""
    return {"subject": subject, "body": body}
