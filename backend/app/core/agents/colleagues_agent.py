from __future__ import annotations

import json
import logging
import re
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, EmailStr, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.bedrock import BedrockConverseModel
from app.core.utils.provenance import log_provenance
from app.config import settings

# Browser-Use (Python) — MUST be used for LinkedIn search
from browser_use import Agent as BrowserAgent
from browser_use import Browser, BrowserProfile
from browser_use.llm import ChatAWSBedrock


logger = logging.getLogger(__name__)


class ColleagueSearchParams(BaseModel):
    company: str
    departments: List[str] = ["Bioinformatics", "Genomics", "Oncology", "Data Science"]
    keywords: List[str] = []  # e.g. ["cancer","genomics","data"]


class InternalContact(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    job_title: str
    department: Optional[str] = None
    linkedin_url: Optional[str] = None
    relevance_score: float = Field(ge=0, le=1)
    reason_for_contact: str


class Contact(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    job_title: str
    department: Optional[str] = None
    linkedin_url: Optional[str] = None
    relevance_score: float = Field(ge=0, le=1)
    reason_for_contact: str


class Contacts(BaseModel):
    items: List[Contact]

model = BedrockConverseModel( "us.anthropic.claude-sonnet-4-20250514-v1:0")

colleagues_agent = Agent[ColleagueSearchParams, List[InternalContact]](
    model,
    deps_type=ColleagueSearchParams,
    output_type=List[InternalContact],
    instructions=(
        "You are an internal collaboration facilitator. "
        "Find relevant colleagues who might have access to cancer research data. "
        "Focus on wet-lab departments, bioinformatics teams, and data custodians. "
        "Prioritize titles: Research Scientist, Bioinformatician, Data Manager, Lab Manager, Principal Investigator, Oncology. "
        "Normalize output to JSON with fields: name, job_title, department, linkedin_url, email(optional), relevance_score, reason_for_contact."
    ),
)


def _extract_json_list(text: str) -> List[Dict[str, Any]]:
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            return data["results"]
    except Exception:
        pass

    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return []
    return []


async def _run_browser_use_task(task: str) -> List[Dict[str, Any]]:
    if BrowserAgent is None or Browser is None or ChatAWSBedrock is None:
        logger.warning("browser_use not available; returning empty colleague results")
        return []

    profile = BrowserProfile(
        minimum_wait_page_load_time=0.5,
        wait_between_actions=0.5,
        headless=False,
        keep_alive=False,
        timeout=600
    )
    browser = Browser(browser_profile=profile)
    llm = ChatAWSBedrock(
        model="us.anthropic.claude-sonnet-4-20250514-v1:0",
        aws_region="us-east-1",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    agent = BrowserAgent(
        task=task,
        browser=browser,
        llm=llm,
        flash_mode=True,
        output_model_schema=Contacts,
        extend_system_message=(
            "Return strictly as a JSON object with key 'items' containing an array of objects. "
            "Each object must have keys: name, job_title, department, linkedin_url, email, relevance_score, reason_for_contact."
        ),
    )
    try:
        result = await agent.run()

        parsed: List[Dict[str, Any]] = []

        # Prefer Browser-Use structured output when available
        if hasattr(result, "structured_output") and getattr(result, "structured_output"):
            so = getattr(result, "structured_output")
            if isinstance(so, BaseModel):
                data_obj = so.model_dump()
            elif isinstance(so, dict):
                data_obj = so
            else:
                try:
                    data_obj = json.loads(str(so))
                except Exception:
                    data_obj = {}

            items = data_obj.get("items") or []
            for it in items:
                if isinstance(it, BaseModel):
                    it = it.model_dump()
                if isinstance(it, dict):
                    parsed.append(it)
        else:
            # Fallback to legacy text parsing
            if isinstance(result, str):
                parsed = _extract_json_list(result)
            else:
                text = ""
                if isinstance(result, dict):
                    text = result.get("final_result") or result.get("result") or ""
                parsed = _extract_json_list(text)

        return parsed
    except Exception as e:
        logger.error(f"Browser-Use LinkedIn task failed: {e}")
        return []
    finally:
        try:
            await browser.kill()
        except Exception:
            pass


@colleagues_agent.tool
async def search_linkedin_employees(ctx: RunContext[ColleagueSearchParams]) -> List[Dict[str, Any]]:
    """
    Search company employees on LinkedIn using LinkedInScraper (Browser-Use under the hood).
    """
    from app.core.scrapers.linkedin_scraper import LinkedInScraper

    scraper = LinkedInScraper(headless=not bool(getattr(settings, "DEBUG", False)))
    kw = list(ctx.deps.keywords or [])
    results = await scraper.find_company_employees(
        company=ctx.deps.company,
        departments=ctx.deps.departments,
        keywords=kw,
        max_results=10,
    )

    await log_provenance(
        actor="colleagues_agent",
        action="searched_linkedin",
        details={"company": ctx.deps.company, "found_count": len(results)},
    )
    return results


async def linkedin_sign_in() -> Dict[str, Any]:
    """
    Ensure the LinkedIn session is signed in before running internal searches.
    Returns:
        {"ok": bool, "status": one of "success" | "missing_credentials" | "checkpoint_required" | "invalid_credentials" | "error" | "unavailable"}
    """
    from app.core.scrapers.linkedin_scraper import LinkedInScraper

    # Validate minimal config
    if not (settings.LINKEDIN_EMAIL and settings.LINKEDIN_PW and settings.LINKEDIN_COMPANY_URL):
        status = "missing_credentials"
        await log_provenance(
            actor="colleagues_agent",
            action="linkedin_sign_in",
            details={"ok": False, "status": status},
        )
        return {"ok": False, "status": status}

    scraper = LinkedInScraper(headless=not bool(getattr(settings, "DEBUG", False)))
    ok, status = await scraper.ensure_logged_in()

    await log_provenance(
        actor="colleagues_agent",
        action="linkedin_sign_in",
        details={"ok": ok, "status": status},
    )
    return {"ok": ok, "status": status}


async def start_linkedin_login_session() -> Dict[str, Any]:
    """
    Open a persistent LinkedIn login session and keep the browser open so the user can log in manually.
    Returns:
        {"ok": bool, "status": "opened"|"unavailable"|"error", "error": Optional[str]}
    Notes:
        - Does NOT submit credentials; only opens the login page and keeps the browser alive.
        - Session persistence relies on LinkedInScraper keep_alive BrowserProfile and user_data_dir.
    """
    from app.core.scrapers.linkedin_scraper import LinkedInScraper

    scraper = LinkedInScraper(headless=not bool(getattr(settings, "DEBUG", False)))
    res = await scraper.open_login_page(keep_open=True)

    await log_provenance(
        actor="colleagues_agent",
        action="linkedin_manual_login_started",
        details={"ok": bool(res.get("ok")), "status": res.get("status")},
    )
    return res


async def search_linkedin_direct(
    company: str,
    departments: List[str],
    keywords: List[str],
    max_results: int = 10,
    login_preferred: bool = True,
    use_existing_session: bool = False,
) -> List[Dict[str, Any]]:
    """
    Deterministic LinkedIn search that can attempt a sign-in-first workflow and returns structured JSON.
    - If login_preferred and credentials exist, try a logged-in, non-action contact scrape.
    - Otherwise fall back to public search without login.
    """
    from app.core.scrapers.linkedin_scraper import LinkedInScraper

    scraper = LinkedInScraper(headless=not bool(getattr(settings, "DEBUG", False)))

    raw: List[Dict[str, Any]] = []
    login_status = "skipped"

    # 1) Prefer manual, already-open session if requested
    if use_existing_session:
        try:
            raw = await scraper.get_logged_in_contacts(
                company=company,
                departments=departments,
                keywords=keywords or [],
                max_results=max_results,
                skip_login_check=True,
            )
            login_status = "manual_session"
        except Exception:
            raw = []
            login_status = "manual_session_error"

    # 2) If no manual session results, optionally attempt agentic sign-in if enabled (backward-compat)
    if not raw:
        if login_preferred and settings.LINKEDIN_EMAIL and settings.LINKEDIN_PW and settings.LINKEDIN_COMPANY_URL:
            try:
                ok, status = await scraper.ensure_logged_in()
                login_status = status
                if ok:
                    raw = await scraper.get_logged_in_contacts(
                        company=company,
                        departments=departments,
                        keywords=keywords or [],
                        max_results=max_results,
                    )
                else:
                    # Fallback to public search
                    raw = await scraper.find_company_employees(
                        company=company,
                        departments=departments,
                        keywords=keywords or [],
                        max_results=max_results,
                        login=False,
                    )
            except Exception:
                # Hard fallback to public search
                raw = await scraper.find_company_employees(
                    company=company,
                    departments=departments,
                    keywords=keywords or [],
                    max_results=max_results,
                    login=False,
                )
        else:
            # 3) Public search without login
            raw = await scraper.find_company_employees(
                company=company,
                departments=departments,
                keywords=keywords or [],
                max_results=max_results,
                login=False,
            )

    results: List[Dict[str, Any]] = []
    for r in raw or []:
        results.append(
            {
                "name": r.get("name"),
                "job_title": r.get("job_title"),
                "department": r.get("department"),
                "company": r.get("company") or company,
                "linkedin_url": r.get("linkedin_url"),
                "email": r.get("email"),
                "email_suggestions": r.get("email_suggestions") or [],
                "relevance_score": float(max(0.0, min(1.0, float(r.get("relevance_score") or 0)))),
                "reason_for_contact": "Matches provided keywords/departments",
            }
        )

    await log_provenance(
        actor="colleagues_agent",
        action="searched_linkedin_direct",
        details={"company": company, "found_count": len(results), "login_preferred": login_preferred, "login_status": login_status},
    )
    return results


async def linkedin_outreach_direct(
    title_keyword: str,
    send_messages: bool = False,
    message_template: Optional[str] = None,
    send_connection_note: bool = False,
    connection_note_template: Optional[str] = None,
    max_actions: int = 5,
    dry_run: bool = True,
) -> List[Dict[str, Any]]:
    """
    Direct LinkedIn outreach for colleagues with specific title filtering.
    
    Args:
        title_keyword: Job title to search for (e.g., "Bioinformatics", "Data Scientist")
        send_messages: Send messages to already-connected profiles
        message_template: Custom message template (max 600 chars)
        send_connection_note: Include note with connection requests
        connection_note_template: Custom connection note (max 280 chars)
        max_actions: Maximum outreach actions to perform
        dry_run: Preview actions without sending (safety default)
    
    Returns:
        List of outreach action results
    """
    from app.core.scrapers.linkedin_scraper import LinkedInScraper
    
    if not settings.LINKEDIN_EMAIL or not settings.LINKEDIN_PW or not settings.LINKEDIN_COMPANY_URL:
        logger.warning("LinkedIn credentials missing for outreach")
        return [{"error": "LinkedIn credentials not configured", "action": "config_error"}]
    
    # Default templates for cancer research context
    default_message = (
        "Hi! I'm working on cancer research data discovery and would love to connect. "
        "We're building tools to help researchers find relevant biological datasets faster. "
        "Would you be interested in discussing potential collaboration opportunities?"
    )
    
    default_connection_note = (
        "Hi! I'm working on cancer research data discovery tools and would love to connect "
        "to discuss potential collaboration opportunities."
    )
    
    scraper = LinkedInScraper(headless=not bool(getattr(settings, "DEBUG", False)))
    results = await scraper.find_company_employees(
        company="",  # Not used for logged-in workflow
        departments=[],  # Using title_keyword instead
        keywords=[],
        max_results=0,  # Not used for outreach
        login=True,
        title_keyword=title_keyword,
        send_messages=send_messages,
        message_template=message_template or default_message,
        send_connection_note=send_connection_note,
        connection_note_template=connection_note_template or default_connection_note,
        max_actions=max_actions,
        dry_run=dry_run,
    )
    
    await log_provenance(
        actor="colleagues_agent",
        action="linkedin_outreach",
        details={
            "title_keyword": title_keyword,
            "actions_attempted": len(results),
            "dry_run": dry_run,
            "max_actions": max_actions,
        },
    )
    
    return results


@colleagues_agent.tool
async def enrich_contact_info(ctx: RunContext[ColleagueSearchParams], employee: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich employee data with email suggestions based on common patterns if email missing.
    """
    if not employee.get("email"):
        name = (employee.get("name") or "").lower().strip()
        parts = [p for p in re.split(r"[^\w]+", name) if p]
        domain = re.sub(r"[^a-z0-9]", "", (ctx.deps.company or "").lower()) + ".com" if ctx.deps.company else None
        suggestions: List[str] = []
        if domain and len(parts) >= 2:
            suggestions = [
                f"{parts[0]}.{parts[-1]}@{domain}",
                f"{parts[0][0]}{parts[-1]}@{domain}",
                f"{parts[0]}@{domain}",
            ]
        employee["email_suggestions"] = suggestions

    employee.setdefault("reason_for_contact", "Potential internal data owner for cancer research datasets.")
    # Keep relevance_score in [0,1]
    try:
        rs = float(employee.get("relevance_score", 0))
        employee["relevance_score"] = max(0.0, min(1.0, rs))
    except Exception:
        employee["relevance_score"] = 0.5

    return employee
