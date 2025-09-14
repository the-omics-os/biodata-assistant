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
        "product_invite": product_invite_template,
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


def product_invite_template(
    persona_name: str,
    persona_title: str,
    repo: str,
    issue_title: str,
    recipient_name: str,
    message_style: str = "casual",
    omics_os_url: str = "https://www.omics-os.com",
    **_: Any,
) -> Dict[str, str]:
    """
    Product invitation email template for GitHub issue prospects.
    Uses casual, empathetic tone with specific problem-solution examples.
    """
    # Extract repo name for friendlier reference
    repo_name = repo.split("/")[-1] if "/" in repo else repo
    
    subject = f"hei! saw your {repo_name} issue - maybe omics-os can help? 🧬"
    
    # Generate problem-specific solution examples
    solution_examples = _generate_solution_examples(issue_title, repo_name)
    
    # Casual, empathetic body with tailored solutions
    body = f"""hei {recipient_name}!

I saw you were struggling with "{issue_title}" in {repo_name}. I totally get it - those bioinformatics tools can be such a headache sometimes! 😅

I'm {persona_name}, a {persona_title}, and I wanted to let you know about omics-os - it's a no-code tool we built specifically to replace all that complexity with tools like ScanPy, AnnData, MuData, and BioPython.

{solution_examples}

Instead of wrestling with code and installations, you can just drag, drop, and analyze your data visually. It handles all the technical stuff behind the scenes.

Want to give it a try? Check it out at {omics_os_url}

Feel free to reach out if you have any questions - I'm happy to help!

cheers,
{persona_name}
{persona_title}

P.S. - No installation headaches, no Python environments to manage, just pure bioinformatics analysis ✨
"""
    
    return {"subject": subject, "body": body}


def _generate_solution_examples(issue_title: str, repo_name: str) -> str:
    """
    Generate specific solution examples based on the issue title and repo.
    Tailors the omics-os pitch to their exact problem.
    """
    issue_lower = issue_title.lower()
    
    # Installation/setup problems
    if any(keyword in issue_lower for keyword in ["install", "installation", "setup", "environment", "conda", "pip"]):
        return """For example, if you're dealing with installation headaches like this, in omics-os you'd just:
1. Upload your data file (drag & drop)
2. Choose your analysis workflow from our visual interface
3. Hit "Run" - no Python environments, no dependency conflicts, no version mismatches!"""
    
    # Data loading/format issues
    elif any(keyword in issue_lower for keyword in ["load", "read", "import", "file", "format", "h5ad", "csv", "matrix"]):
        return """For data loading issues like this, omics-os makes it super simple:
1. Just drag your file into the platform (any format - h5ad, CSV, Excel, you name it)
2. Our smart parser automatically detects the structure 
3. Your data appears in a clean, interactive table - ready for analysis!"""
    
    # Analysis/plotting problems  
    elif any(keyword in issue_lower for keyword in ["plot", "umap", "tsne", "cluster", "analysis", "visualiz", "graph"]):
        return """For analysis and plotting challenges like this, omics-os has you covered:
1. Select your loaded data with a click
2. Choose from pre-built analysis workflows (UMAP, clustering, DE analysis, etc.)
3. Get publication-ready plots instantly - no matplotlib debugging!"""
    
    # AnnData object manipulation
    elif any(keyword in issue_lower for keyword in ["anndata", "adata", "obs", "var", "obsm", "varm", "uns"]):
        return """For AnnData manipulation troubles like this, omics-os removes all the complexity:
1. Your data structure is visualized automatically
2. Add metadata, filter cells, or subset data with point-and-click
3. No more `.obs`, `.var`, `.obsm` confusion - just intuitive data management!"""
    
    # General scanpy/analysis issues
    elif any(keyword in issue_lower for keyword in ["scanpy", "sc.pp", "sc.tl", "sc.pl", "preprocessing", "normalize"]):
        return """For scanpy workflow issues like this, omics-os streamlines everything:
1. Upload your raw count matrix
2. Follow our guided preprocessing pipeline (filtering, normalization, scaling)
3. Run advanced analyses with visual parameter tuning - no cryptic function calls!"""
    
    # Error/debugging issues
    elif any(keyword in issue_lower for keyword in ["error", "bug", "fail", "crash", "exception", "traceback"]):
        return """For those frustrating errors like this, omics-os eliminates the debugging nightmare:
1. Our workflows are pre-tested and validated
2. Clear error messages (in plain English!) if something goes wrong
3. Built-in data validation catches issues before they become cryptic Python errors!"""
    
    # Documentation/help requests
    elif any(keyword in issue_lower for keyword in ["how to", "tutorial", "help", "example", "documentation", "guide"]):
        return """For questions like this, omics-os makes learning effortless:
1. Interactive tutorials built right into the platform
2. Contextual help tooltips on every feature
3. Example datasets and workflows to get you started immediately!"""
    
    # General/fallback
    else:
        return """For challenges like this, omics-os takes a completely different approach:
1. Visual, drag-and-drop interface instead of coding
2. Pre-built, validated workflows for common bioinformatics tasks
3. Instant results without debugging Python environments or wrestling with syntax!"""
