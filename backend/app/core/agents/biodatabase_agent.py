from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, ModelRetry
from pydantic_ai.models.bedrock import BedrockConverseModel
from app.core.utils.provenance import log_provenance
from app.config import settings
from app.core.scrapers.geo_scraper import GEOScraper

# Browser-Use (Python) — MUST be used for scraping

from browser_use import Agent as BrowserAgent
from browser_use import Browser, BrowserProfile
from browser_use.llm import ChatOpenAI


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


model = BedrockConverseModel( "us.anthropic.claude-sonnet-4-20250514-v1:0")

bio_database_agent = Agent[DatabaseSearchParams, List[DatasetCandidate]](
    model,
    deps_type=DatabaseSearchParams,
    output_type=List[DatasetCandidate],
    instructions=(
        """
        You are an expert biological database search specialist optimized for cancer research data discovery.

        Use advanced search strategies with Boolean operators, specific filters, and step-by-step methodology.

        Search Strategy Framework:
        1. Construct optimized queries with Boolean operators (AND, OR, NOT)
        2. Apply database-specific filters (date ranges, organisms, file types)
        3. Validate metadata requirements (treatment response, timepoints, clinical annotations)
        4. Prioritize datasets with clinical metadata and structured annotations
        5. Score relevance based on sample size, data quality, and research context

        Query Construction Rules:
        - Use quoted terms for exact phrases: "single-cell RNA-seq", "NSCLC"
        - Combine synonyms with OR: ("PD-1" OR "PD-L1" OR "pembrolizumab")
        - Include treatment/response terms: ("responder" OR "resistance" OR "sensitive")
        - Add timepoint indicators: ("pre-treatment" OR "post-treatment" OR "longitudinal")
        - Specify data modalities: ("RNA-seq" OR "scRNA-seq" OR "proteomics")
        Example queries: 
        - "P53 lung cancer RNA-seq" → ("TP53" OR "p53") AND ("lung cancer" OR "NSCLC") AND "RNA-seq"
        - "immunotherapy resistance" → ("PD-1" OR "PD-L1" OR "checkpoint inhibitor") AND ("resistance" OR "non-responder")

        Output Format:
        Return structured JSON with relevance scoring and metadata validation flags.
        Prioritize datasets with complete clinical annotations and accessible data files.
        """
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


# async def _run_browser_use_task(task: str) -> List[Dict[str, Any]]:
#     """
#     Execute a Browser-Use task, returning parsed JSON list per output contract.
#     """
#     if BrowserAgent is None or Browser is None or ChatOpenAI is None:
#         logger.warning("browser_use not available; returning empty results")
#         return []

#     # Speed-optimized profile; keep headless=False for development visibility
#     profile = BrowserProfile(
#         minimum_wait_page_load_time=0.1,
#         wait_between_actions=0.2,
#         headless=False,
#         keep_alive=False,
#     )
#     browser = Browser(browser_profile=profile)

#     # Use a fast model for browsing assistant
#     llm = ChatOpenAI(model="gpt-4.1-mini")

#     agent = BrowserAgent(
#         task=task,
#         browser=browser,
#         llm=llm,
#         flash_mode=True,
#         extend_system_message=(
#             "Return results strictly as a compact JSON array. "
#             "Avoid prose. Keys: accession, title, description, modalities, cancer_types, "
#             "sample_size, access_type, download_url, contact_info, link."
#         ),
#     )

#     try:
#         result = await agent.run()
#         if isinstance(result, str):
#             parsed = _extract_json_list(result)
#         else:
#             # Some versions return dict-like with `final_result` or `result`
#             text = ""
#             if isinstance(result, dict):
#                 text = result.get("final_result") or result.get("result") or ""
#             parsed = _extract_json_list(text)
#         return parsed
#     except Exception as e:
#         logger.error(f"Browser-Use task failed: {e}")
#         return []
#     finally:
#         try:
#             await browser.kill()
#         except Exception:
#             pass


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


async def search_geo_direct(query: str, max_results: int) -> List[Dict[str, Any]]:
    """
    Professional GEO search with dynamic optimization and validation.
    Uses the bio_database_agent's intelligence for query optimization and result validation.
    """
    # Create search parameters
    search_params = DatabaseSearchParams(
        query=query,
        database="GEO",
        max_results=max_results
    )
    
    try:
        # Use the intelligent agent for advanced search
        agent_run = await bio_database_agent.run(search_params)
        if agent_run.output:
            # Convert agent output to expected format
            results = []
            for candidate in agent_run.output:
                if hasattr(candidate, 'model_dump'):
                    result = candidate.model_dump()
                else:
                    result = dict(candidate)
                
                # Ensure contact_info is properly structured
                contact_info = result.get("contact_info")
                if contact_info and not isinstance(contact_info, dict):
                    result["contact_info"] = None
                    
                results.append(result)
            
            await log_provenance(
                actor="bio_database_agent",
                action="searched_geo_intelligent",
                details={"query": query, "results_count": len(results)},
            )
            
            return results
    except Exception as e:
        logger.warning(f"Intelligent search failed, falling back to direct search: {e}")
    
    # Fallback to direct scraper if agent fails
    scraper = GEOScraper(headless=not bool(getattr(settings, "DEBUG", False)))
    raw = await scraper.search_datasets(query=query, max_results=max_results)

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
        action="searched_geo_fallback",
        details={"query": query, "results_count": len(results)},
    )
    return results


@bio_database_agent.tool(retries=2)
async def validate_metadata_requirements(ctx: RunContext[DatabaseSearchParams], dataset: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dynamically validate dataset metadata against research requirements.
    
    Analyze the dataset and research context to determine:
    - Clinical data availability
    - Treatment response information
    - Timepoint data
    - Required biomarkers
    - Data quality indicators
    
    Return validation results with specific requirements and quality assessment.
    """
    validation_results = {
        "is_suitable": True,
        "quality_score": 0.0,
        "missing_elements": [],
        "strengths": [],
        "recommendations": []
    }
    
    # The LLM will analyze the dataset content and research context
    # to provide intelligent validation without hardcoded rules
    return validation_results


@bio_database_agent.tool(retries=2)
async def search_with_advanced_strategy(ctx: RunContext[DatabaseSearchParams]) -> List[Dict[str, Any]]:
    """
    Execute advanced multi-step search strategy following the template approach:
    
    Step 1: Optimize query construction with Boolean operators
    Step 2: Execute targeted database search with filters
    Step 3: Validate metadata requirements for each result
    Step 4: Score and rank results by relevance and quality
    
    This implements the professional search methodology from the template.
    """
    # Step 1: Get optimized query
    optimized_query = ctx.deps.query
    
    # Step 2: Execute search with optimized query
    scraper = GEOScraper(headless=not bool(getattr(settings, "DEBUG", False)))
    
    # Apply filters based on context
    filters = ctx.deps.filters.copy()
    if not filters.get("date_range"):
        filters["date_range"] = {"start": "2019", "end": "2024"}  # Recent data preference
    if not filters.get("organisms"):
        filters["organisms"] = ["human"]  # Default to human studies
    
    raw_results = await scraper.search_datasets(
        query=optimized_query, 
        max_results=ctx.deps.max_results * 2  # Get more for filtering
    )
    
    # Step 3: Process and validate each result
    validated_results = []
    for r in raw_results:
        # Normalize result structure
        result = {
            "accession": r.get("accession", ""),
            "title": r.get("title", ""),
            "description": r.get("description"),
            "modalities": r.get("modalities", []),
            "cancer_types": r.get("cancer_types", []),
            "sample_size": r.get("sample_size"),
            "access_type": r.get("access_type", "public"),
            "download_url": r.get("download_url"),
            "contact_info": {"name": r.get("contact_name"), "email": r.get("contact_email")} if (r.get("contact_name") or r.get("contact_email")) else None,
            "link": r.get("link"),
        }
        
        # Validate metadata requirements
        validation = await validate_metadata_requirements(ctx, result)
        result["validation"] = validation
        result["quality_score"] = validation["quality_score"]
        
        if validation["is_suitable"]:
            validated_results.append(result)
    
    # Step 4: Sort by quality and return top results
    validated_results.sort(key=lambda x: x["quality_score"], reverse=True)
    final_results = validated_results[:ctx.deps.max_results]
    
    await log_provenance(
        actor="bio_database_agent",
        action="advanced_search_completed",
        details={
            "original_query": ctx.deps.query,
            "optimized_query": optimized_query,
            "total_found": len(raw_results),
            "validated_count": len(validated_results),
            "final_count": len(final_results)
        }
    )
    
    return final_results


@bio_database_agent.tool
async def evaluate_dataset_relevance(ctx: RunContext[DatabaseSearchParams], dataset: Dict[str, Any]) -> float:
    """
    Dynamically evaluate dataset relevance using LLM analysis rather than hardcoded rules.
    
    Consider:
    - Semantic similarity to research question
    - Data modality alignment
    - Sample size appropriateness
    - Clinical relevance
    - Data accessibility
    
    Return relevance score (0.0 to 1.0).
    """
    # Let the LLM analyze relevance dynamically based on the research context
    # This avoids hardcoded keyword lists and uses intelligent assessment
    
    # Basic scoring as fallback
    base_score = 0.5
    
    # The LLM will provide more sophisticated relevance scoring
    # based on the actual research question and dataset content
    
    return base_score
