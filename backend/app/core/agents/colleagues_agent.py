from __future__ import annotations

import json
import logging
import re
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, EmailStr, Field
from pydantic_ai import Agent, RunContext
from app.core.utils.provenance import log_provenance

# Browser-Use (Python) — MUST be used for LinkedIn search
try:
    from browser_use import Agent as BrowserAgent
    from browser_use import Browser, BrowserProfile, ChatOpenAI
except Exception:  # pragma: no cover
    BrowserAgent = None  # type: ignore[assignment]
    Browser = None  # type: ignore[assignment]
    BrowserProfile = None  # type: ignore[assignment]
    ChatOpenAI = None  # type: ignore[assignment]

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


colleagues_agent = Agent[ColleagueSearchParams, List[InternalContact]](
    "openai:gpt-4o",
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
    if BrowserAgent is None or Browser is None or ChatOpenAI is None:
        logger.warning("browser_use not available; returning empty colleague results")
        return []

    profile = BrowserProfile(
        minimum_wait_page_load_time=0.1,
        wait_between_actions=0.2,
        headless=False,
        keep_alive=False,
    )
    browser = Browser(browser_profile=profile)
    llm = ChatOpenAI(model="gpt-4.1-mini")

    agent = BrowserAgent(
        task=task,
        browser=browser,
        llm=llm,
        flash_mode=True,
        extend_system_message=(
            "Return results strictly as a compact JSON array with keys: "
            "name, job_title, department, linkedin_url, email, relevance_score, reason_for_contact."
        ),
    )
    try:
        result = await agent.run()
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
    Search company employees on LinkedIn via Browser-Use, returning raw dicts.
    """
    kw = list({*(ctx.deps.keywords or []), "cancer", "genomics", "data"})
    task = (
        "1. Open https://www.linkedin.com/ "
        f"2. Search employees at \"{ctx.deps.company}\" "
        f"3. Filter by departments {ctx.deps.departments} and keywords {kw} "
        "4. Collect top profiles: name, job_title, department (if visible), profile URL, infer email if visible or leave null "
        "5. Score relevance 0–1 based on oncology/bioinformatics/data ownership "
        "6. Return strictly a JSON array"
    )
    results = await _run_browser_use_task(task)
    await log_provenance(
        actor="colleagues_agent",
        action="searched_linkedin",
        details={"company": ctx.deps.company, "found_count": len(results)},
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
