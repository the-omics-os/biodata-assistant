from __future__ import annotations

from typing import Dict, Any, Optional


def generate_email_template(template_type: str, **kwargs: Any) -> Dict[str, str]:
    """
    Generate professional email templates with a cancer research focus.

    Usage:
    - data_request:
        required kwargs:
            dataset_title, requester_name, requester_title, contact_name, project_description
        optional kwargs:
            organization, outreach_id
    - follow_up:
        required kwargs:
            original_request_date, dataset_title, contact_name, requester_name
    - thank_you:
        required kwargs:
            contact_name, requester_name
        optional kwargs:
            next_steps

    Returns dict with keys: subject, body
    """
    templates = {
        "data_request": data_request_template,
        "follow_up": follow_up_template,
        "thank_you": thank_you_template,
    }
    generator = templates.get(template_type, data_request_template)
    return generator(**kwargs)


def data_request_template(
    dataset_title: str,
    requester_name: str,
    requester_title: str,
    contact_name: str,
    project_description: str,
    organization: Optional[str] = None,
    outreach_id: Optional[str] = None,
) -> Dict[str, str]:
    """
    Professional data request email focused on cancer research collaboration.
    """
    org_line = f" at {organization}" if organization else ""
    ref_line = f"\nReference ID: {outreach_id}" if outreach_id else ""

    subject = f"Request for access to \"{dataset_title}\" — Cancer Research Collaboration"

    body = f"""Dear {contact_name},

I am {requester_name}, a {requester_title}{org_line}. I am reaching out regarding the dataset "{dataset_title}" which appears highly relevant to our cancer research objectives.

Research context:
{project_description}

Data usage and compliance:
- Purpose: Cancer biomarker discovery and validation
- Analysis: Computational analysis only on de-identified data
- Compliance: We follow institutional governance and de-identification policies
- Attribution: We will properly cite and acknowledge all data sources

Request:
- Access to the dataset and associated metadata (where permissible)
- Any documentation or publications that may aid interpretation
- The appropriate process and any agreements (e.g., DUA) required for access

If there are specific procedures or forms required, I will gladly follow them. I can provide additional details or arrange a brief call if helpful.

Thank you for your time and for making this valuable resource available to the research community.

Best regards,
{requester_name}
{requester_title}{org_line}

---
This outreach was sent via the Biodata Assistant platform on behalf of {requester_name}.{ref_line}

Important: If this dataset contains clinical PHI or sensitive patient data, please do not send it directly via email. Kindly refer us to your data governance process for secure transfer.
"""

    return {"subject": subject, "body": body}


def follow_up_template(
    original_request_date: str,
    dataset_title: str,
    contact_name: str,
    requester_name: str,
    **_: Any,
) -> Dict[str, str]:
    """
    Follow-up email template after initial data request.
    """
    subject = f"Follow-up: Data access request for \"{dataset_title}\""

    body = f"""Dear {contact_name},

I hope you are well. I wanted to follow up on my request from {original_request_date} regarding access to the dataset "{dataset_title}".

I understand schedules are busy, and I wanted to check if:
- Any additional information is needed about our project
- There are specific procedures or forms we should complete
- Another colleague is the right point of contact for data access

We remain very interested in this dataset for our cancer research work and would appreciate your guidance on next steps.

Thank you for your time.

Best regards,
{requester_name}
"""
    return {"subject": subject, "body": body}


def thank_you_template(
    contact_name: str,
    requester_name: str,
    next_steps: Optional[str] = None,
    **_: Any,
) -> Dict[str, str]:
    """
    Thank-you email template after receiving data or guidance.
    """
    subject = "Thank you"

    extra = f"\nNext steps:\n{next_steps}\n" if next_steps else ""
    body = f"""Dear {contact_name},

Thank you for your assistance with our data access request. We appreciate the time and guidance you provided in support of our cancer research work.{extra}
Best regards,
{requester_name}
"""
    return {"subject": subject, "body": body}
