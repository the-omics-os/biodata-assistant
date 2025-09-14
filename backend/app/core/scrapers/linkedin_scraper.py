from __future__ import annotations

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


class LinkedInContact(BaseModel):
    """Structured LinkedIn employee data"""
    name: str
    job_title: str
    department: Optional[str] = None
    company: str
    linkedin_url: Optional[str] = None
    email_suggestions: List[str] = []
    keywords_matched: List[str] = []
    relevance_score: float = 0.0


class LinkedInScraper:
    """
    LinkedIn employee finder using Browser-Use
    Reference: browser-use-doc.md - Multiple browser and speed profile pattern
    """

    def __init__(self, headless: Optional[bool] = None) -> None:
        # Headless by default in production; visible in debug/development
        if headless is None:
            headless = not bool(getattr(settings, "DEBUG", False))

        self.headless = headless

        # LinkedIn usually needs a bit longer waits
        self.browser_profile = None
        if BrowserProfile is not None:
            try:
                self.browser_profile = BrowserProfile(
                    minimum_wait_page_load_time=1.0,
                    wait_between_actions=0.5,
                    headless=self.headless,
                    keep_alive=False,
                )
            except Exception:
                self.browser_profile = None

        self.browser = None
        if Browser is not None:
            try:
                if self.browser_profile is not None:
                    self.browser = Browser(browser_profile=self.browser_profile)  # type: ignore[arg-type]
                else:
                    self.browser = Browser(
                        user_data_dir="./temp-profile-linkedin",
                        headless=self.headless,
                    )
            except Exception as e:
                logger.warning(f"Failed to initialize Browser: {e}")
                self.browser = None

    async def find_company_employees(
        self,
        company: str,
        departments: List[str],
        keywords: List[str],
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find employees at company matching department/keywords using public LinkedIn search.
        """
        # If Browser-Use is not available, return mock results for MVP/demo
        if BrowserAgent is None or self.browser is None or ChatOpenAI is None:
            logger.warning("browser_use not available; returning mock LinkedIn results")
            results = self._mock_results(company, departments, keywords, max_results)
            await self._log_provenance(
                action="searched_linkedin_mock",
                details={
                    "company": company,
                    "departments": departments,
                    "keywords": keywords,
                    "results_found": len(results),
                },
            )
            return results

        try:
            try:
                await self.browser.start()  # type: ignore[func-returns-value]
            except Exception:
                pass

            dept_filter = " OR ".join([f'"{d}"' for d in departments]) if departments else ""
            keyword_filter = " OR ".join([f'"{k}"' for k in keywords]) if keywords else ""

            search_task = f"""
LinkedIn employee search task:
1. Navigate to https://www.linkedin.com/search/results/people/
2. Apply filters using public search (no login):
   - Current company: "{company}"
   - Keywords: {keyword_filter}
   - Title/Department keywords: {dept_filter}
3. For the first {max_results} results, extract:
   - name
   - job_title (current)
   - department (if visible or infer from title)
   - profile URL
4. DO NOT attempt to open gated profile pages; only use public search result snippets.
5. Return strictly as a JSON array.
"""

            llm = ChatOpenAI(model="gpt-4.1-mini")

            agent = BrowserAgent(
                task=search_task,
                browser=self.browser,
                llm=llm,
                flash_mode=True,
                browser_profile=self.browser_profile,
            )

            result = await agent.run(max_steps=20)  # type: ignore[func-returns-value]

            employees = self._parse_employee_results(result)

            enriched = [self._generate_email_suggestions(e, company) for e in employees]
            scored = [self._calculate_relevance(e, keywords, departments) for e in enriched]

            await self._log_provenance(
                action="searched_linkedin",
                details={
                    "company": company,
                    "departments": departments,
                    "keywords": keywords,
                    "results_found": len(scored),
                },
            )
            return scored
        except Exception as e:
            logger.error(f"LinkedIn search error: {e}")
            await self._log_provenance(
                action="searched_linkedin_error",
                details={"company": company, "error": str(e)},
            )
            return []
        finally:
            try:
                await self.browser.kill()  # type: ignore[func-returns-value]
            except Exception:
                pass

    def _parse_employee_results(self, result: Any) -> List[Dict[str, Any]]:
        """Parse LinkedIn search results from agent output."""
        text = self._stringify_result(result)
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

    def _stringify_result(self, result: Any) -> str:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return str(result.get("final_result") or result.get("result") or "")
        try:
            return str(result)
        except Exception:
            return ""

    def _generate_email_suggestions(self, employee: Dict[str, Any], company: str) -> Dict[str, Any]:
        """Generate potential corporate email patterns."""
        name = (employee.get("name") or "").lower()
        parts = [p for p in re.split(r"[^\w]+", name) if p]
        domain = re.sub(r"[^a-z0-9]", "", (company or "").lower()) + ".com" if company else None

        suggestions: List[str] = []
        if domain and len(parts) >= 2:
            first, last = parts[0], parts[-1]
            suggestions = [
                f"{first}.{last}@{domain}",
                f"{first[0]}{last}@{domain}",
                f"{first}@{domain}",
                f"{last}@{domain}",
                f"{first}_{last}@{domain}",
            ]

        employee["email_suggestions"] = suggestions
        return employee

    def _calculate_relevance(
        self,
        employee: Dict[str, Any],
        keywords: List[str],
        departments: List[str],
    ) -> Dict[str, Any]:
        """Calculate relevance score from job title/department and keywords."""
        score = 0.0
        matched: List[str] = []

        job_title = (employee.get("job_title") or "").lower()
        emp_dept = (employee.get("department") or "").lower()

        for kw in keywords or []:
            if kw.lower() in job_title:
                score += 0.2
                matched.append(kw)

        for dept in departments or []:
            if dept.lower() in emp_dept or dept.lower() in job_title:
                score += 0.3

        priority_titles = ["data", "bioinformatic", "genomic", "oncolog", "scientist", "research"]
        if any(t in job_title for t in priority_titles):
            score += 0.2

        employee["keywords_matched"] = matched
        employee["relevance_score"] = min(1.0, score)
        return employee

    def _mock_results(
        self,
        company: str,
        departments: List[str],
        keywords: List[str],
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """Return generic mock LinkedIn results for MVP/demo when scraping is unavailable."""
        base = [
            {
                "name": "Alice Johnson",
                "job_title": "Senior Data Scientist",
                "department": "Data",
                "company": company,
                "linkedin_url": None,
            },
            {
                "name": "Bob Lee",
                "job_title": "Research Scientist",
                "department": "Research",
                "company": company,
                "linkedin_url": None,
            },
            {
                "name": "Carol Perez",
                "job_title": "Lab Manager",
                "department": "Laboratory",
                "company": company,
                "linkedin_url": None,
            },
        ]
        # Lightweight scoring pass (based solely on provided keywords/departments)
        enriched = [self._generate_email_suggestions(e, company) for e in base]
        scored = [self._calculate_relevance(e, keywords, departments) for e in enriched]
        return scored[: max_results]

    async def _log_provenance(self, action: str, details: Dict[str, Any]) -> None:
        """Log action for audit trail"""
        try:
            from app.core.utils.provenance import log_provenance
            await log_provenance(actor="linkedin_scraper", action=action, details=details)
        except Exception as e:
            logger.debug(f"Provenance logging failed: {e}")
