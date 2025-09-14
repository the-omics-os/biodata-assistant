from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, ModelRetry
from app.core.utils.provenance import log_provenance
from app.config import settings
from app.core.scrapers.geo_scraper import GEOScraper

# Browser-Use (Python) — MUST be used for scraping
try:
    from browser_use import Agent as BrowserAgent
    from browser_use import Browser, BrowserProfile, ChatOpenAI
except Exception:  # pragma: no cover - allow import-time resilience
    BrowserAgent = None  # type: ignore[assignment]
    Browser = None  # type: ignore[assignment]
    BrowserProfile = None  # type: ignore[assignment]
    ChatOpenAI = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class DatabaseSearchParams(BaseModel):
    query: str
    database: str  # 'GEO'|'PRIDE'|'ENSEMBL'
    filters: Dict[str, Any] = {}
    max_results: int = 20


class DatasetCandidate(BaseModel):
    accession: str
    title: str
    description: Optional[str] = None
    modalities: List[str] = []
    cancer_types: List[str] = []
    sample_size: Optional[int] = None
    access_type: str = "public"
    download_url: Optional[str] = None
    contact_info: Optional[Dict[str, str]] = None
    link: Optional[str] = None
    relevance_score: float = Field(default=0.0, ge=0, le=1)


bio_database_agent = Agent[DatabaseSearchParams, List[DatasetCandidate]](
    "openai:gpt-4o",
    deps_type=DatabaseSearchParams,
    output_type=List[DatasetCandidate],
    instructions=(
        "You are a biological database search specialist for cancer research.\n"
        "Search public databases (NCBI/GEO, PRIDE, Ensembl) for relevant datasets.\n"
        "Evaluate data quality, sample size, and accessibility. Prefer processed data for speed.\n"
        "Normalize results to JSON list with fields: accession, title, description, modalities[], "
        "cancer_types[], sample_size, access_type, download_url, contact_info{name,email}, link.\n"
    ),
)


def _extract_json_list(text: str) -> List[Dict[str, Any]]:
    """
    Attempt to parse a JSON array from arbitrary text (Browser-Use agent output may be freeform).
    """
    try:
        # Direct JSON
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
            return data["results"]
    except Exception:
        pass

    # Fallback: grab the first [...] block
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return []
    return []


async def _run_browser_use_task(task: str) -> List[Dict[str, Any]]:
    """
    Execute a Browser-Use task, returning parsed JSON list per output contract.
    """
    if BrowserAgent is None or Browser is None or ChatOpenAI is None:
        logger.warning("browser_use not available; returning empty results")
        return []

    # Speed-optimized profile; keep headless=False for development visibility
    profile = BrowserProfile(
        minimum_wait_page_load_time=0.1,
        wait_between_actions=0.2,
        headless=False,
        keep_alive=False,
    )
    browser = Browser(browser_profile=profile)

    # Use a fast model for browsing assistant
    llm = ChatOpenAI(model="gpt-4.1-mini")

    agent = BrowserAgent(
        task=task,
        browser=browser,
        llm=llm,
        flash_mode=True,
        extend_system_message=(
            "Return results strictly as a compact JSON array. "
            "Avoid prose. Keys: accession, title, description, modalities, cancer_types, "
            "sample_size, access_type, download_url, contact_info, link."
        ),
    )

    try:
        result = await agent.run()
        if isinstance(result, str):
            parsed = _extract_json_list(result)
        else:
            # Some versions return dict-like with `final_result` or `result`
            text = ""
            if isinstance(result, dict):
                text = result.get("final_result") or result.get("result") or ""
            parsed = _extract_json_list(text)
        return parsed
    except Exception as e:
        logger.error(f"Browser-Use task failed: {e}")
        return []
    finally:
        try:
            await browser.kill()
        except Exception:
            pass


@bio_database_agent.tool(retries=2)
async def search_ncbi_geo(ctx: RunContext[DatabaseSearchParams]) -> List[Dict[str, Any]]:
    """
    Search NCBI GEO using the dedicated GEOScraper (Browser-Use under the hood).
    Returns a list of dicts normalized for DatasetCandidate.
    """
    scraper = GEOScraper(headless=not bool(getattr(settings, "DEBUG", False)))
    raw = await scraper.search_datasets(query=ctx.deps.query, max_results=ctx.deps.max_results)

    # Normalize into DatasetCandidate-like dicts expected by downstream code
    results: List[Dict[str, Any]] = []
    for r in raw:
        contact_name = r.get("contact_name")
        contact_email = r.get("contact_email")
        contact_info = {"name": contact_name, "email": contact_email} if (contact_name or contact_email) else None
        results.append(
            {
                "accession": r.get("accession", ""),
                "title": r.get("title", ""),
                "description": r.get("description"),
                "modalities": r.get("modalities", []),
                "cancer_types": r.get("cancer_types", []),
                "sample_size": r.get("sample_size"),
                "access_type": r.get("access_type", "public"),
                "download_url": r.get("download_url"),
                "contact_info": contact_info,
                "link": r.get("link"),
                "relevance_score": 0.0,
            }
        )

    await log_provenance(
        actor="bio_database_agent",
        action="searched_geo",
        details={"query": ctx.deps.query, "results_count": len(results)},
    )
    return results


@bio_database_agent.tool
async def evaluate_dataset_relevance(ctx: RunContext[DatabaseSearchParams], dataset: Dict[str, Any]) -> float:
    """
    Score dataset relevance to research question with a simple heuristic.
    """
    score = 0.0
    title = (dataset.get("title") or "").lower()
    desc = (dataset.get("description") or "").lower()
    q = ctx.deps.query.lower()

    # Cancer keyword matches
    cancer_terms = ["cancer", "carcinoma", "tumor", "oncology", "adenocarcinoma", "tnbc", "breast", "lung", "tp53", "p53"]
    if any(t in title or t in desc for t in cancer_terms):
        score += 0.35

    # Modality matches mentioned in query
    modalities = [m.lower() for m in dataset.get("modalities", [])]
    modality_terms = ["rna-seq", "scrna-seq", "proteomics", "genomics", "exome", "wgs", "wxs"]
    if any(m in q for m in modality_terms) and any(mt in modalities for mt in modality_terms):
        score += 0.35

    # Sample size bonus
    try:
        n = int(dataset.get("sample_size") or 0)
        if n > 100:
            score += 0.2
        elif n > 50:
            score += 0.1
    except Exception:
        pass

    # Access type bonus
    if (dataset.get("access_type") or "").lower() == "public":
        score += 0.1

    return min(score, 1.0)
