from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
import os

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# Optional Browser-Use imports with fallbacks
from browser_use import Agent as BrowserAgent
from browser_use import Browser, BrowserProfile
from browser_use.llm import ChatOpenAI



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


class LinkedInActionResult(BaseModel):
    """Result of LinkedIn outreach action"""
    name: str
    job_title: str
    linkedin_url: str
    action: str  # "connect_sent", "message_sent", "skipped", "dry_run", "error"
    note_used: bool = False
    message_used: bool = False
    error: Optional[str] = None
    is_connected: bool = False


class LinkedInScraper:
    """
    LinkedIn employee finder using Browser-Use with login capability
    Reference: browser-use-doc.md - Multiple browser and speed profile pattern
    """

    def __init__(self, headless: Optional[bool] = None) -> None:
        # Headless by default in production; visible in debug/development
        if headless is None:
            headless = not bool(getattr(settings, "DEBUG", False))

        self.headless = headless
        self.logged_in = False
        
        # LinkedIn needs longer waits and persistent session for login
        self.browser_profile = None
        if BrowserProfile is not None:
            try:
                self.browser_profile = BrowserProfile(
                    minimum_wait_page_load_time=1.2,
                    wait_between_actions=0.6,
                    headless=self.headless,
                    keep_alive=True,  # Keep session alive for login persistence
                    timout=600
                )
            except Exception:
                self.browser_profile = None

        self.browser = None
        if Browser is not None:
            try:
                # Always use a fixed user_data_dir to persist session across separate instances
                self.browser = Browser(
                    user_data_dir="./temp-profile-linkedin",
                    headless=self.headless,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Browser: {e}")
                self.browser = None

    async def open_login_page(self, keep_open: bool = True) -> Dict[str, Any]:
        """
        Open LinkedIn login page and keep the browser open for manual authentication.
        Returns {"ok": True, "status": "opened"} on success, otherwise {"ok": False, "status": "unavailable"|"error", "error": "..."}.
        """

        try:
            try:
                await self.browser.start()  # type: ignore[func-returns-value]
            except Exception:
                pass

            llm = ChatOpenAI(
                model="gpt-4.1",
            )
            task = """
1. Navigate to https://www.linkedin.com/login
2. Wait until the login page is fully loaded and username/password fields are visible
3. Do not enter any credentials and do not submit the form
4. When the page is visible, return "successful" and STOP
"""
            agent = BrowserAgent(
                task=task,
                browser=self.browser,
                llm=llm,
                flash_mode=True,
                browser_profile=self.browser_profile,
            )
            result = await agent.run(max_steps=4)  # type: ignore[func-returns-value]
            text = self._stringify_result(result).lower()
            ok = "successful" in text
            # Keep the browser open so the user can log in manually
            if not keep_open:
                try:
                    await self.browser.kill()  # type: ignore[func-returns-value]
                except Exception:
                    pass
            return {"ok": ok, "status": "successful" if ok else "error"}
        except Exception as e:
            logger.error(f"open_login_page error: {e}")
            return {"ok": False, "status": "error", "error": str(e)}

    async def ensure_logged_in(self) -> tuple[bool, str]:
        """
        Public sign-in helper that ensures the LinkedIn session is authenticated.
        Returns tuple: (ok, status) where status is one of:
        "success" | "missing_credentials" | "checkpoint_required" | "invalid_credentials" | "error" | "unavailable"
        """
        if self.logged_in:
            return True, "success"
        if BrowserAgent is None or self.browser is None or ChatOpenAI is None:
            return False, "unavailable"

        try:
            try:
                await self.browser.start()  # type: ignore[func-returns-value]
            except Exception:
                pass
            status = await self._ensure_login()
            ok = status == "success"
            if ok:
                self.logged_in = True
            return ok, status
        except Exception as e:
            logger.error(f"ensure_logged_in error: {e}")
            return False, "error"

    async def get_logged_in_contacts(
        self,
        company: str,
        departments: List[str],
        keywords: List[str],
        max_results: int = 10,
        skip_login_check: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        After successful login, navigate to company employees page and extract contact-like results
        without performing any connect/message actions.
        Returns a list of LinkedInContact-shaped dicts.
        """
        if BrowserAgent is None or self.browser is None or ChatOpenAI is None:
            return []

        try:
            try:
                await self.browser.start()  # type: ignore[func-returns-value]
            except Exception:
                pass

            if not skip_login_check and not self.logged_in:
                ok, _status = await self.ensure_logged_in()
                if not ok:
                    return []

            nav_ok = await self._navigate_to_employees()
            if not nav_ok:
                return []

            filter_info = f"Departments: {', '.join(departments or [])}; Keywords: {', '.join(keywords or [])}"
            task = f"""
Extract up to {max_results} employee entries from the current LinkedIn employees page.
For each visible result row, extract:
- name
- job_title (current)
- department (infer from job title if not visible)
- profile URL
Return strictly as a JSON array.
Notes: {filter_info}
"""

            llm = ChatOpenAI(
                model="gpt-4.1",
            )
            agent = BrowserAgent(
                task=task,
                browser=self.browser,
                llm=llm,
                flash_mode=True,
                browser_profile=self.browser_profile,
            )
            result = await agent.run(max_steps=12)  # type: ignore[func-returns-value]
            employees = self._parse_employee_results(result)

            # Post-filter and score in Python to avoid brittle UI assumptions
            enriched = [self._generate_email_suggestions(e, company) for e in employees]
            scored = [self._calculate_relevance(e, keywords, departments) for e in enriched]
            return scored[:max_results]
        except Exception as e:
            logger.error(f"get_logged_in_contacts error: {e}")
            return []
        finally:
            try:
                await self.browser.kill()  # type: ignore[func-returns-value]
            except Exception:
                pass

    async def find_company_employees(
        self,
        company: str,
        departments: List[str],
        keywords: List[str],
        max_results: int = 10,
        login: bool = True,
        title_keyword: Optional[str] = None,
        send_messages: bool = False,
        message_template: Optional[str] = None,
        send_connection_note: bool = False,
        connection_note_template: Optional[str] = None,
        max_actions: int = 5,
        dry_run: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Find employees at company matching department/keywords.
        
        Args:
            company: Company name for public search (fallback)
            departments: Department filters
            keywords: Keyword filters  
            max_results: Max results to return
            login: Use logged-in workflow (True) or public search (False)
            title_keyword: Specific title to filter by when logged in
            send_messages: Send messages to already-connected profiles
            message_template: Template for messages (max 600 chars)
            send_connection_note: Include note with connection requests
            connection_note_template: Template for connection notes (max 280 chars)
            max_actions: Max connection/message actions per run
            dry_run: Preview actions without sending (safety default)
        
        Returns:
            List of LinkedInActionResult dicts if login=True, else LinkedInContact dicts
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
                    "login_attempted": login,
                    "dry_run": dry_run,
                },
            )
            return results

        # Decide workflow: logged-in vs public search
        if login and settings.LINKEDIN_EMAIL and settings.LINKEDIN_PW and settings.LINKEDIN_COMPANY_URL:
            return await self._logged_in_workflow(
                title_keyword=title_keyword,
                departments=departments,
                keywords=keywords,
                send_messages=send_messages,
                message_template=message_template,
                send_connection_note=send_connection_note,
                connection_note_template=connection_note_template,
                max_actions=max_actions,
                dry_run=dry_run,
            )
        else:
            if login:
                logger.warning("LinkedIn credentials missing, falling back to public search")
            return await self._public_search_workflow(company, departments, keywords, max_results)

    async def _logged_in_workflow(
        self,
        title_keyword: Optional[str],
        departments: List[str],
        keywords: List[str],
        send_messages: bool,
        message_template: Optional[str],
        send_connection_note: bool,
        connection_note_template: Optional[str],
        max_actions: int,
        dry_run: bool,
    ) -> List[Dict[str, Any]]:
        """Execute the full logged-in LinkedIn workflow"""
        try:
            await self.browser.start()  # type: ignore[func-returns-value]
        except Exception:
            pass

        try:
            # Step 1: Login
            login_result = await self._ensure_login()
            if login_result != "success":
                await self._log_provenance(
                    action="login_failed",
                    details={"status": login_result},
                )
                return [{"error": f"Login failed: {login_result}", "action": "login_error"}]

            # Step 2: Navigate to company employees
            nav_result = await self._navigate_to_employees()
            if not nav_result:
                return [{"error": "Failed to navigate to employees page", "action": "navigation_error"}]

            # Step 3: Apply filters
            if title_keyword:
                filter_result = await self._apply_filters(title_keyword)
                if not filter_result:
                    logger.warning("Failed to apply filters, continuing with unfiltered results")

            # Step 4: Process profiles and perform actions
            actions = await self._process_profiles(
                send_messages=send_messages,
                message_template=message_template or "Hi! I'd like to connect and discuss potential collaboration opportunities in cancer research data.",
                send_connection_note=send_connection_note,
                connection_note_template=connection_note_template or "Hi! I'm working on cancer research data discovery and would love to connect.",
                max_actions=max_actions,
                dry_run=dry_run,
            )

            await self._log_provenance(
                action="linkedin_logged_in_workflow_completed",
                details={
                    "title_keyword": title_keyword,
                    "actions_attempted": len(actions),
                    "dry_run": dry_run,
                    "max_actions": max_actions,
                },
            )

            return actions

        except Exception as e:
            logger.error(f"LinkedIn logged-in workflow error: {e}")
            await self._log_provenance(
                action="logged_in_workflow_error",
                details={"error": str(e)},
            )
            return [{"error": str(e), "action": "workflow_error"}]
        finally:
            try:
                await self.browser.kill()  # type: ignore[func-returns-value]
            except Exception:
                pass

    async def _ensure_login(self) -> str:
        """
        Ensure user is logged in to LinkedIn.
        Returns: "success", "checkpoint_required", "invalid_credentials", "error"
        """
        if not settings.LINKEDIN_EMAIL or not settings.LINKEDIN_PW:
            return "missing_credentials"

        llm = ChatOpenAI(
            model="gpt-4.1",
            aws_region="us-east-1"
        )
        
        login_task = f"""
LinkedIn login task:
1. Navigate to https://www.linkedin.com/login
2. Fill in the email field with the provided credentials
3. Fill in the password field with the provided credentials  
4. Click the "Sign in" button
5. Wait for the page to load and check if login was successful
6. If you see a checkpoint/security challenge, return "checkpoint_required"
7. If login is successful (you see the LinkedIn homepage/feed), return "success"
8. If credentials are rejected, return "invalid_credentials"

IMPORTANT: Do not log or expose the actual credentials in any output.
"""

        agent = BrowserAgent(
            task=login_task,
            browser=self.browser,
            llm=llm,
            flash_mode=False,  # Login needs more careful handling
            browser_profile=self.browser_profile,
        )

        try:
            result = await agent.run(max_steps=10)  # type: ignore[func-returns-value]
            result_text = self._stringify_result(result).lower()
            
            if "checkpoint_required" in result_text:
                return "checkpoint_required"
            elif "success" in result_text:
                self.logged_in = True
                return "success"
            elif "invalid_credentials" in result_text:
                return "invalid_credentials"
            else:
                return "error"
                
        except Exception as e:
            logger.error(f"Login error (credentials masked): {e}")
            return "error"

    async def _navigate_to_employees(self) -> bool:
        """Navigate to company employees page"""
        if not settings.LINKEDIN_COMPANY_URL:
            return False

        llm = ChatOpenAI(
            model="gpt-4.1",
            aws_region="us-east-1"
        )
        
        nav_task = f"""
LinkedIn company navigation task:
1. Go to {settings.LINKEDIN_COMPANY_URL}
2. Look for the employees link - it might be labeled as "See all employees" or show a number like "1,234 employees"
3. Click on that employees link
4. Wait for the employees search page to load
5. Verify you can see a list of employee profiles
6. Return "success" if you successfully reach the employees page
"""

        agent = BrowserAgent(
            task=nav_task,
            browser=self.browser,
            llm=llm,
            flash_mode=True,
            browser_profile=self.browser_profile,
        )

        try:
            result = await agent.run(max_steps=8)  # type: ignore[func-returns-value]
            result_text = self._stringify_result(result).lower()
            return "success" in result_text
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            return False

    async def _apply_filters(self, title_keyword: str) -> bool:
        """Apply title keyword filter in LinkedIn employee search"""
        llm = ChatOpenAI(
            model="gpt-4.1",
            aws_region="us-east-1"
        )
        
        filter_task = f"""
LinkedIn filtering task:
1. Look for "All filters" button on the current employees page
2. Click "All filters" to open the filter sidebar
3. In the sidebar, scroll down to find the "Keywords" section
4. In the Keywords section, find the "Title" input field
5. Enter "{title_keyword}" in the Title field
6. Click "Show results" or "Apply" button to apply the filter
7. Wait for the filtered results to load
8. Return "success" if filtering was applied successfully
"""

        agent = BrowserAgent(
            task=filter_task,
            browser=self.browser,
            llm=llm,
            flash_mode=True,
            browser_profile=self.browser_profile,
        )

        try:
            result = await agent.run(max_steps=10)  # type: ignore[func-returns-value]
            result_text = self._stringify_result(result).lower()
            return "success" in result_text
        except Exception as e:
            logger.error(f"Filtering error: {e}")
            return False

    async def _process_profiles(
        self,
        send_messages: bool,
        message_template: str,
        send_connection_note: bool,
        connection_note_template: str,
        max_actions: int,
        dry_run: bool,
    ) -> List[Dict[str, Any]]:
        """Process profiles and perform connect/message actions"""
        llm = ChatOpenAI(
            model="gpt-4.1",
            aws_region="us-east-1"
        )
        
        # Truncate templates to LinkedIn limits
        message_template = message_template[:600]
        connection_note_template = connection_note_template[:280]
        
        process_task = f"""
LinkedIn profile processing task:
1. Look at the employee search results on the current page
2. For up to {max_actions} profiles, do the following for each:
   a. Click on the profile to open it
   b. Check if there's a "Message" button (already connected) or "Connect" button (not connected)
   c. Record the person's name, job title, and profile URL
   d. If dry_run is True (dry_run={dry_run}), only record what would be done - don't click buttons
   e. If not dry_run and "Connect" button exists:
      - Click "Connect"
      - If send_connection_note is True ({send_connection_note}) and a note dialog appears, enter: "{connection_note_template}"
      - Record the action as "connect_sent"
   f. If not dry_run and "Message" button exists and send_messages is True ({send_messages}):
      - Click "Message" 
      - In the message box, enter: "{message_template}"
      - Click Send
      - Record the action as "message_sent"
   g. Go back to the search results to process the next profile

3. Return results as a JSON array with format:
   [{{"name": "John Doe", "job_title": "Data Scientist", "linkedin_url": "https://...", "action": "connect_sent", "is_connected": false}}]

IMPORTANT: Respect the max_actions limit of {max_actions}. Add small delays between actions to avoid rate limiting.
"""

        agent = BrowserAgent(
            task=process_task,
            browser=self.browser,
            llm=llm,
            flash_mode=False,  # Careful processing for actions
            browser_profile=self.browser_profile,
        )

        try:
            result = await agent.run(max_steps=max_actions * 8)  # type: ignore[func-returns-value]
            actions = self._parse_action_results(result)
            
            # Add metadata to results
            for action in actions:
                action["note_used"] = send_connection_note and action.get("action") == "connect_sent"
                action["message_used"] = send_messages and action.get("action") == "message_sent"
                
            return actions
            
        except Exception as e:
            logger.error(f"Profile processing error: {e}")
            return [{"error": str(e), "action": "processing_error"}]

    async def _public_search_workflow(
        self,
        company: str,
        departments: List[str],
        keywords: List[str],
        max_results: int,
    ) -> List[Dict[str, Any]]:
        """Execute public LinkedIn search (original implementation)"""
        try:
            await self.browser.start()  # type: ignore[func-returns-value]
        except Exception:
            pass

        try:
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

            llm = ChatOpenAI(
                model="gpt-4.1",
            )

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
                action="searched_linkedin_public",
                details={
                    "company": company,
                    "departments": departments,
                    "keywords": keywords,
                    "results_found": len(scored),
                },
            )
            
            return scored
            
        except Exception as e:
            logger.error(f"LinkedIn public search error: {e}")
            await self._log_provenance(
                action="searched_linkedin_public_error",
                details={"company": company, "error": str(e)},
            )
            return []
        finally:
            try:
                await self.browser.kill()  # type: ignore[func-returns-value]
            except Exception:
                pass

    def _parse_action_results(self, result: Any) -> List[Dict[str, Any]]:
        """Parse LinkedIn action results from agent output."""
        text = self._stringify_result(result)
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and isinstance(data.get("results"), list):
                return data["results"]
        except Exception:
            pass

        # Fallback: extract JSON array from text
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return []

        return []

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
        """Convert agent result to string for parsing."""
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
        return scored[:max_results]

    async def _log_provenance(self, action: str, details: Dict[str, Any]) -> None:
        """Log action for audit trail"""
        try:
            from app.core.utils.provenance import log_provenance
            await log_provenance(actor="linkedin_scraper", action=action, details=details)
        except Exception as e:
            logger.debug(f"Provenance logging failed: {e}")


