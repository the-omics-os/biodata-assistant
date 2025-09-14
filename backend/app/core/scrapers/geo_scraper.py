from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# Optional Browser-Use imports with fallbacks
try:
    from browser_use import Agent as BrowserAgent
    from browser_use import Browser, BrowserProfile, ChatOpenAI
except Exception:  # pragma: no cover - allow import-time resilience
    BrowserAgent = None  # type: ignore[assignment]
    Browser = None  # type: ignore[assignment]
    BrowserProfile = None  # type: ignore[assignment]
    ChatOpenAI = None  # type: ignore[assignment]


class GEODataset(BaseModel):
    """Structured output for GEO dataset"""
    accession: str
    title: str
    organism: Optional[str] = None
    modalities: List[str] = []
    cancer_types: List[str] = []
    sample_size: Optional[int] = None
    access_type: str = "public"
    publication_url: Optional[str] = None
    pubmed_id: Optional[str] = None
    download_url: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    link: Optional[str] = None


class GEOScraper:
    """
    NCBI GEO scraper using Browser-Use
    Reference: browser-use-doc.md - Direct Python usage pattern
    """

    def __init__(self, headless: Optional[bool] = None) -> None:
        # Headless by default in production; visible in debug/development
        if headless is None:
            headless = not bool(getattr(settings, "DEBUG", False))

        self.headless = headless

        # Speed/stability tuned profile
        self.browser_profile = None
        if BrowserProfile is not None:
            try:
                self.browser_profile = BrowserProfile(
                    minimum_wait_page_load_time=0.5,
                    wait_between_actions=0.3,
                    headless=self.headless,
                    keep_alive=True,
                )
            except Exception:
                self.browser_profile = None

        # Dedicated browser profile directory for GEO
        self.browser = None
        if Browser is not None:
            try:
                # Prefer passing browser_profile if supported, else fallback to args
                if self.browser_profile is not None:
                    self.browser = Browser(browser_profile=self.browser_profile)  # type: ignore[arg-type]
                else:
                    self.browser = Browser(
                        user_data_dir="./temp-profile-geo",
                        headless=self.headless,
                    )
            except Exception as e:
                logger.warning(f"Failed to initialize Browser: {e}")
                self.browser = None

        # Speed optimization instructions
        self.speed_prompt = """
Speed optimization instructions:
- Be extremely concise and direct in your responses
- Get to the goal as quickly as possible
- Extract only the required data fields
- Use multi-action sequences whenever possible to reduce steps
- Return strictly a compact JSON array with the requested keys
"""

    async def search_datasets(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search GEO for datasets matching the query.
        Returns a list of dicts (ready to be normalized by agents if needed).
        """
        # If Browser-Use is not available, return mock results for MVP/demo
        if BrowserAgent is None or self.browser is None or ChatOpenAI is None:
            logger.warning("browser_use not available; returning mock GEO results")
            results = self._mock_results(query, max_results)
            await self._log_provenance(
                action="searched_geo_mock",
                details={"query": query, "results_found": len(results)},
            )
            return results

        # Keep browser alive for chained enrichment tasks
        try:
            # Some versions require explicit start
            try:
                await self.browser.start()  # type: ignore[func-returns-value]
            except Exception:
                pass

            # Task: use the GDS portal which routes GEO/GDS series
            search_task = f"""
1. Navigate to https://www.ncbi.nlm.nih.gov/gds
2. In the search box, search for: {query} with cancer-related focus terms (P53, TP53, TNBC, lung adenocarcinoma, breast cancer)
3. Prefer Homo sapiens when applicable
4. For the first {max_results} results, extract:
   - accession (GSE or GDS)
   - title
   - organism
   - modalities (RNA-seq / scRNA-seq / microarray / proteomics)
   - sample_size (approximate integer)
   - access_type (public/request/restricted)
   - link (result page)
5. Return strictly as a JSON array
"""

            # Fast LLM as per docs
            llm = ChatOpenAI(model="gpt-4.1-mini")

            agent = BrowserAgent(
                task=search_task,
                browser=self.browser,
                llm=llm,
                flash_mode=True,
                browser_profile=self.browser_profile,
                extend_system_message=self.speed_prompt,
            )

            result = await agent.run(max_steps=15)  # type: ignore[func-returns-value]

            datasets = self._parse_search_results(result)
            enriched: List[Dict[str, Any]] = []

            for ds in datasets[: max_results]:
                if self._needs_enrichment(ds):
                    try:
                        enriched_ds = await self._enrich_dataset(ds, agent)
                        enriched.append(enriched_ds)
                    except Exception as e:
                        logger.debug(f"Enrichment failed for {ds.get('accession')}: {e}")
                        enriched.append(ds)
                else:
                    enriched.append(ds)

            await self._log_provenance(
                action="searched_geo",
                details={"query": query, "results_found": len(enriched)},
            )

            return enriched

        except Exception as e:
            logger.error(f"GEO search error: {e}")
            await self._log_provenance(
                action="searched_geo_error",
                details={"query": query, "error": str(e)},
            )
            return []
        finally:
            # If not keeping session, ensure shutdown
            try:
                if getattr(self.browser_profile, "keep_alive", False):
                    # don't kill if caller wants to reuse; this scraper manages its own lifecycle though
                    await self.browser.kill()  # type: ignore[func-returns-value]
                else:
                    await self.browser.kill()  # type: ignore[func-returns-value]
            except Exception:
                pass

    async def _enrich_dataset(self, dataset: Dict[str, Any], agent: Any) -> Dict[str, Any]:
        """
        Enrich dataset with detailed contact, download, and publication info.
        Uses agent.add_new_task to chain tasks within the same session.
        """
        acc = dataset.get("accession") or ""
        detail_task = f"""
Navigate to the GEO page for accession {acc}.
Extract:
- contact_name and contact_email (if provided)
- download_url (processed data link if available)
- pubmed_id and publication_url (if available)
Return strictly as JSON with keys: contact_name, contact_email, download_url, pubmed_id, publication_url
"""
        try:
            # Chain a follow-up task on the same agent/browser session
            agent.add_new_task(detail_task)
            detail_result = await agent.run(max_steps=6)  # type: ignore[func-returns-value]

            enrichment = self._parse_detail_result(detail_result)
            dataset.update(enrichment)
        except Exception as e:
            logger.debug(f"Detail task failed for {acc}: {e}")

        return dataset

    def _parse_search_results(self, result: Any) -> List[Dict[str, Any]]:
        """
        Parse agent output into structured datasets (list of dicts).
        We expect a JSON array or a wrapper with 'final_result'/'result'.
        """
        text = self._stringify_result(result)
        data = self._extract_json_list(text)

        # Normalize field names for downstream compatibility
        normalized: List[Dict[str, Any]] = []
        for item in data:
            try:
                normalized.append(
                    {
                        "accession": item.get("accession") or item.get("id") or "",
                        "title": item.get("title") or "",
                        "organism": item.get("organism"),
                        "modalities": item.get("modalities") or item.get("experiment_type") or [],
                        "cancer_types": item.get("cancer_types") or [],
                        "sample_size": item.get("sample_size") or item.get("samples"),
                        "access_type": item.get("access_type") or "public",
                        "download_url": item.get("download_url") or item.get("download_link"),
                        "publication_url": item.get("publication_url"),
                        "pubmed_id": item.get("pubmed_id"),
                        "contact_name": item.get("contact_name"),
                        "contact_email": item.get("contact_email"),
                        "link": item.get("link"),
                    }
                )
            except Exception:
                # Best-effort append original if normalization fails
                normalized.append(item)
        return normalized

    def _needs_enrichment(self, dataset: Dict[str, Any]) -> bool:
        """Check if dataset needs additional details."""
        return not dataset.get("contact_email") or not dataset.get("download_url")

    def _parse_detail_result(self, result: Any) -> Dict[str, Any]:
        """Parse enrichment JSON; fallback to regex where needed."""
        text = self._stringify_result(result)
        obj: Dict[str, Any] = {}
        arr = self._extract_json_list(text)

        if isinstance(arr, list) and arr:
            # If array, take first object
            if isinstance(arr[0], dict):
                obj = arr[0]
        else:
            # Try parse as direct dict
            try:
                maybe = json.loads(text)
                if isinstance(maybe, dict):
                    obj = maybe
            except Exception:
                obj = {}

        # Minimal email extraction as a fallback
        if not obj.get("contact_email"):
            m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
            if m:
                obj["contact_email"] = m.group(0)

        return {
            "contact_name": obj.get("contact_name"),
            "contact_email": obj.get("contact_email"),
            "download_url": obj.get("download_url"),
            "pubmed_id": obj.get("pubmed_id"),
            "publication_url": obj.get("publication_url"),
        }

    def _stringify_result(self, result: Any) -> str:
        """Convert agent.run(...) result into a string for JSON extraction."""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return str(result.get("final_result") or result.get("result") or "")
        try:
            return str(result)
        except Exception:
            return ""

    def _extract_json_list(self, text: str) -> List[Dict[str, Any]]:
        """Attempt to parse a JSON array from arbitrary text."""
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and isinstance(data.get("results"), list):
                return data["results"]
        except Exception:
            pass

        # Fallback: first [...] block
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return []
        return []

    def _mock_results(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Return cancer-focused mock GEO results for MVP/demo when scraping is unavailable."""
        base = [
            {
                "accession": "GSE999001",
                "title": "TP53-driven lung adenocarcinoma RNA-seq",
                "organism": "Homo sapiens",
                "modalities": ["rna-seq"],
                "cancer_types": ["lung adenocarcinoma"],
                "sample_size": 120,
                "access_type": "public",
                "download_url": "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE999nnn/GSE999001/suppl/",
                "publication_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
                "pubmed_id": "12345678",
                "contact_name": "Dr. Jane Doe",
                "contact_email": "jane.doe@university.edu",
                "link": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE999001",
            },
            {
                "accession": "GSE999002",
                "title": "TNBC single-cell transcriptomics (10x Genomics)",
                "organism": "Homo sapiens",
                "modalities": ["scrna-seq"],
                "cancer_types": ["triple negative breast cancer"],
                "sample_size": 45_000,  # cells
                "access_type": "public",
                "download_url": "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE999nnn/GSE999002/suppl/",
                "publication_url": None,
                "pubmed_id": None,
                "contact_name": "Dr. John Smith",
                "contact_email": "john.smith@cancercenter.org",
                "link": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE999002",
            },
            {
                "accession": "GSE999003",
                "title": "P53 pathway proteomics in breast cancer cohorts",
                "organism": "Homo sapiens",
                "modalities": ["proteomics"],
                "cancer_types": ["breast cancer"],
                "sample_size": 80,
                "access_type": "request",
                "download_url": None,
                "publication_url": None,
                "pubmed_id": None,
                "contact_name": None,
                "contact_email": None,
                "link": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE999003",
            },
        ]
        # Simple relevance filter: prefer items containing query tokens
        q = (query or "").lower()
        filtered = [i for i in base if any(tok and tok in (i.get("title", "").lower()) for tok in q.split())] or base
        return filtered[: max_results]

    async def _log_provenance(self, action: str, details: Dict[str, Any]) -> None:
        """Log action for audit trail"""
        try:
            from app.core.utils.provenance import log_provenance
            await log_provenance(actor="geo_scraper", action=action, details=details)
        except Exception as e:
            logger.debug(f"Provenance logging failed: {e}")
