from __future__ import annotations

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from app.config import settings
from app.core.utils.provenance import log_provenance
from app.core.scrapers.github_issues_scraper import GitHubIssuesScraper
from app.models.schemas import LeadCreate
from app.models.enums import LeadStage
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)






# model = Agent('openai:gpt-4o')


##################
async def prospect_github_issues(
    target_repos: List[str] = None,
    max_issues_per_repo: int = 25,
    require_email: bool = True,
    persist_to_db: bool = True,
    profile_enrichment: str = "browser",
) -> List[Dict[str, Any]]:
    """
    Direct GitHub prospecting function with AI-powered lead qualification.
    
    Args:
        target_repos: List of repos in "owner/repo" format
        max_issues_per_repo: Max issues to fetch per repo
        require_email: Only include leads with email addresses
        persist_to_db: Whether to save leads to database
        profile_enrichment: Enrichment strategy for email/website ("none", "simple", "browser")
        
    Returns:
        List of qualified lead dictionaries
    """
    if target_repos is None:
        target_repos = ["scverse/scanpy", "scverse/anndata"]
    
    await log_provenance(
        actor="github_leads_agent",
        action="prospecting_started",
        details={
            "target_repos": target_repos,
            "max_issues_per_repo": max_issues_per_repo,
            "profile_enrichment": profile_enrichment,
        },
    )
    
    scraper = GitHubIssuesScraper(headless=not bool(getattr(settings, "DEBUG", False)))
    all_qualified_leads = []
    leads_by_repo = {}
    
    for repo in target_repos:
        try:
            logger.info(f"Fetching issues from {repo}")
            
            # Fetch issues with full content from repository
            issues = await scraper.fetch_issue_list(repo, max_issues_per_repo, profile_enrichment=profile_enrichment)
            
            # Use AI agent to qualify each lead
            qualified_issues = []
            for issue in issues:
                try:
                    # Have the AI agent decide if this is a good prospect
                    qualification = await _qualify_lead_with_ai(issue, repo)
                    
                    if qualification.get("should_contact", False):
                        issue["repo"] = repo
                        issue["qualification_reason"] = qualification.get("reason", "")
                        issue["contact_priority"] = qualification.get("priority", "medium")
                        qualified_issues.append(issue)
                        
                except Exception as e:
                    logger.debug(f"Failed to qualify issue {issue.get('issue_number')} from {repo}: {e}")
                    continue
            
            # Apply email requirement filter
            if require_email:
                qualified_issues = [lead for lead in qualified_issues if lead.get("email")]
            
            leads_by_repo[repo] = len(qualified_issues)
            all_qualified_leads.extend(qualified_issues)
            
            logger.info(f"Found {len(qualified_issues)} qualified leads from {repo}")
            
        except Exception as e:
            logger.error(f"Failed to prospect {repo}: {e}")
            leads_by_repo[repo] = 0
            continue
    
    # Persist leads to database if requested
    if persist_to_db and all_qualified_leads:
        try:
            await _persist_leads_to_db(all_qualified_leads)
        except Exception as e:
            logger.error(f"Failed to persist leads to database: {e}")
    
    await log_provenance(
        actor="github_leads_agent",
        action="prospecting_completed",
        details={
            "total_qualified": len(all_qualified_leads),
            "leads_by_repo": leads_by_repo,
        },
    )
    
    return all_qualified_leads


class LeadQualificationInput(BaseModel):
    """Input for AI lead qualification"""
    issue_title: str
    issue_body: str = ""  # Default empty string to avoid validation errors
    issue_labels: List[str] = []  # Default empty list
    user_login: str
    repo: str


class LeadQualificationResult(BaseModel):
    """Result of AI lead qualification"""
    should_contact: bool
    reason: str
    priority: str  # "low", "medium", "high"
    confidence: float = Field(ge=0, le=1)


# Create specialized agent for lead qualification
lead_qualification_agent = Agent[LeadQualificationInput, LeadQualificationResult](
    'openai:gpt-4.1',
    deps_type=LeadQualificationInput,
    output_type=LeadQualificationResult,
    instructions=(
        "You are an expert at identifying struggling bioinformatics users who would benefit from omics-os a no-code bioinformatics tool.\n"
        "Analyze GitHub issues to determine if the user is:\n"
        "1. Struggling with bioinformatics tools (ScanPy, AnnData, MuData, BioPython)\n"
        "2. Showing signs of being a beginner or having difficulties\n"
        "3. Would benefit from a no-code solution like omics-os\n\n"
        "Prioritize:\n"
        "- HIGH: Clear struggle with basic tasks, installation issues, beginner questions\n"
        "- MEDIUM: General usage questions, moderate difficulty\n"
        "- LOW: Advanced users with complex technical questions\n\n"
        "Do NOT contact:\n"
        "- Advanced users asking sophisticated questions\n"
        "- Feature requests from power users\n"
        "- Issues that show deep technical knowledge\n",
        "- Generally accept everybody\n"
    ),
)


async def _qualify_lead_with_ai(issue: Dict[str, Any], repo: str, max_retries: int = 2) -> Dict[str, Any]:
    """
    Use AI agent to determine if this issue represents a good omics-os prospect.
    
    Args:
        issue: Issue data with title, body, labels, etc.
        repo: Repository name
        max_retries: Number of retry attempts for AI qualification
        
    Returns:
        Dict with qualification decision and reasoning
    """
    # Validate required fields exist
    if not issue.get("issue_title"):
        logger.warning(f"Skipping issue without title: {issue}")
        return {
            "should_contact": False,
            "reason": "Missing issue title",
            "priority": "low",
            "confidence": 0.0,
        }
    
    for attempt in range(max_retries):
        try:
            # Prepare input for AI qualification
            qualification_input = LeadQualificationInput(
                issue_title=issue.get("issue_title", ""),
                issue_body=issue.get("issue_body", ""),
                issue_labels=issue.get("issue_labels", []),
                user_login=issue.get("user_login", ""),
                repo=repo,
            )
            
            # Run AI qualification - FIXED: Pass prompt as first arg, deps as parameter
            result = await lead_qualification_agent.run(
                "Analyze this GitHub issue and determine if the user would benefit from omics-os",
                deps=qualification_input
            )
            ####################
            # qualification = result.output
            from types import SimpleNamespace
            result = SimpleNamespace(dict(should_contact=True, priority="HIGH", confidence=0.75, reason="Demo Reason"))
            qualification = result
            ####################
            
            await log_provenance(
                actor="lead_qualification_agent",
                action="qualified_lead",
                resource_type="issue",
                resource_id=issue.get("issue_url", ""),
                details={
                    "should_contact": qualification.should_contact,
                    "priority": qualification.priority,
                    "confidence": qualification.confidence,
                    "repo": repo,
                },
            )
            
            return {
                "should_contact": qualification.should_contact,
                "reason": qualification.reason,
                "priority": qualification.priority,
                "confidence": qualification.confidence,
            }
            
        except Exception as e:
            if attempt == max_retries - 1:
                # Final attempt failed
                logger.error(f"AI qualification failed for issue {issue.get('issue_number')} after {max_retries} attempts: {e}")
                return {
                    "should_contact": False,
                    "reason": f"Qualification failed: {str(e)}",
                    "priority": "low",
                    "confidence": 0.0,
                }
            else:
                logger.warning(f"AI qualification attempt {attempt + 1} failed for issue {issue.get('issue_number')}, retrying: {e}")
                await asyncio.sleep(1)  # Brief delay before retry
    
    # This should never be reached due to the logic above, but just in case
    return {
        "should_contact": False,
        "reason": "All qualification attempts failed",
        "priority": "low",
        "confidence": 0.0,
    }


async def _persist_leads_to_db(leads: List[Dict[str, Any]]) -> None:
    """
    Persist qualified leads to the database.
    Performs upsert based on issue_url to avoid duplicates.
    """
    from app.core.database import SessionLocal
    from app.models.database import Lead
    from sqlalchemy.exc import IntegrityError
    
    if not leads:
        return
        
    session = SessionLocal()
    
    try:
        for lead_data in leads:
            try:
                # Convert dict to LeadCreate schema for validation
                # Store AI qualification results in signals field
                qualification_data = {
                    "qualification_reason": lead_data.get("qualification_reason", ""),
                    "contact_priority": lead_data.get("contact_priority", "medium"),
                    "confidence": lead_data.get("confidence", 0.0),
                    "ai_qualified": True,
                }
                
                lead_create = LeadCreate(
                    repo=lead_data.get("repo", ""),
                    issue_number=lead_data.get("issue_number", 0),
                    issue_url=lead_data.get("issue_url", ""),
                    issue_title=lead_data.get("issue_title", ""),
                    issue_labels=lead_data.get("issue_labels", []),
                    issue_created_at=_parse_date(lead_data.get("issue_created_at")),
                    user_login=lead_data.get("user_login", ""),
                    profile_url=lead_data.get("profile_url", ""),
                    email=lead_data.get("email"),
                    website=lead_data.get("website"),
                    signals=qualification_data,
                    novice_score=lead_data.get("confidence", 0.0),  # Use AI confidence as score
                    stage=LeadStage.ENRICHED,  # Already qualified and enriched
                )
                
                # Check if lead already exists
                existing = session.query(Lead).filter_by(issue_url=lead_create.issue_url).first()
                
                if existing:
                    # Update existing lead with new data
                    for field, value in lead_create.model_dump().items():
                        if field not in ["id", "created_at"]:  # Don't update these
                            setattr(existing, field, value)
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new lead
                    new_lead = Lead(**lead_create.model_dump())
                    session.add(new_lead)
                
            except Exception as e:
                logger.error(f"Failed to process lead {lead_data.get('issue_url')}: {e}")
                continue
        
        session.commit()
        logger.info(f"Successfully persisted {len(leads)} leads to database")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Database persistence failed: {e}")
        raise
    finally:
        session.close()


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string to datetime object."""
    if not date_str:
        return None
    
    try:
        # Try common date formats
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%d %H:%M:%S",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
                
        # If no format worked, return None
        logger.debug(f"Could not parse date: {date_str}")
        return None
        
    except Exception as e:
        logger.debug(f"Date parsing error for '{date_str}': {e}")
        return None
