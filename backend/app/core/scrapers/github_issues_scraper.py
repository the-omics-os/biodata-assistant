from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# Browser-Use imports with fallbacks
from browser_use import Agent as BrowserAgent
from browser_use import Browser, BrowserProfile
from browser_use.llm import ChatOpenAI


class BasicIssue(BaseModel):
    """Basic GitHub issue data from issues list page"""
    issue_number: str
    issue_title: str
    issue_url: str
    user_login: str


class BasicIssues(BaseModel):
    """Structured output for basic GitHub issues list"""
    issues: List[BasicIssue]


class DetailedIssue(BaseModel):
    """Detailed GitHub issue data from individual issue pages"""
    issue_body: str = ""
    issue_labels: List[str] = []
    issue_created_at: Optional[str] = None
    author_profile_url: str = ""
    author_email: Optional[str] = None
    author_website: Optional[str] = None


class DetailedIssues(BaseModel):
    """Structured output for detailed GitHub issues"""
    detailed_issues: List[DetailedIssue]


class ProfileContact(BaseModel):
    """Contact information from a GitHub profile"""
    user_login: str
    email: Optional[str] = None
    website: Optional[str] = None


class ProfileContacts(BaseModel):
    """Structured output for GitHub profile contact extraction"""
    profiles: List[ProfileContact]


class GitHubIssuesScraper:
    """
    GitHub issues scraper using Browser-Use for lead generation
    Focuses on scanpy and anndata repositories for bioinformatics prospects
    """

    def __init__(self, headless: Optional[bool] = None) -> None:
        # Headless by default in production; visible in debug/development
        if headless is None:
            headless = not bool(getattr(settings, "DEBUG", False))

        self.headless = headless

        # Speed/stability tuned profile for GitHub
        self.browser_profile = None
        if BrowserProfile is not None:
            try:
                self.browser_profile = BrowserProfile(
                    minimum_wait_page_load_time=0.1,
                    wait_between_actions=0.1,
                    headless=self.headless,
                    keep_alive=False,
                    timeout=300
                )
            except Exception:
                self.browser_profile = None

        # Dedicated browser profile directory for GitHub
        self.browser = None
        if Browser is not None:
            try:
                # Prefer passing browser_profile if supported, else fallback to args
                if self.browser_profile is not None:
                    self.browser = Browser(browser_profile=self.browser_profile)  # type: ignore[arg-type]
                else:
                    self.browser = Browser(
                        user_data_dir="./temp-profile-github",
                        headless=self.headless,
                    )
            except Exception as e:
                logger.warning(f"Failed to initialize Browser: {e}")
                self.browser = None

    async def fetch_issue_list(self, repo: str, max_issues: int = 25, profile_enrichment: str = "simple") -> List[Dict[str, Any]]:
        """
        Fetch a list of GitHub issues from the specified repository.
        
        Args:
            repo: Repository in format "owner/repo" (e.g., "scverse/scanpy")
            max_issues: Maximum number of issues to fetch (default 25)
            profile_enrichment: Enrichment strategy for contact info: "none" | "simple" | "browser" (default "simple")
            
        Returns:
            List of issue dictionaries with basic info and author details
        """
        # If Browser-Use is not available, return mock results for MVP/demo
        if BrowserAgent is None or self.browser is None or ChatOpenAI is None:
            logger.warning("browser_use not available; returning mock GitHub issues")
            results = self._mock_issues(repo, max_issues)
            await self._log_provenance(
                action="fetched_issues_mock",
                details={
                    "repo": repo,
                    "max_issues": max_issues,
                    "results_found": len(results),
                },
            )
            return results

        # Use Browser with keep_alive for proper session management
        browser = Browser(
            user_data_dir="./temp-profile-github",
            headless=self.headless,
            keep_alive=True,  # Keep browser alive for task chaining
        )
        
        try:
            await browser.start()
            
            url = f"https://github.com/{repo}/issues"
            
            # Step 1: Get issue list from main page
            issues_list_task = f"""
1. Navigate to {url} and wait for the GitHub issues page to fully load
2. Extract the first {max_issues} issue URLs and basic info from the issues list.
For each issue, extract:
- issue_number (the #number like #1234)
- issue_title (the main title text)
- issue_url (full URL to the individual issue)
- user_login (author username who created the issue)

Return as JSON: {{"issues": [list of issues with these 4 fields]}}
Focus on open issues only. Skip pull requests.
"""
            
            llm = ChatOpenAI(model="gpt-4.1")

            # Get basic issue list first with structured output
            list_agent = BrowserAgent(
                task=issues_list_task,
                browser=browser,
                llm=llm,
                flash_mode=True,
                output_model_schema=BasicIssues,
            )

            list_result = await list_agent.run(max_steps=10)  # type: ignore[func-returns-value]
            basic_issues = self._parse_basic_issues(list_result)
            
            logger.info(f"Parsed {len(basic_issues)} basic issues from {repo}")
            
            if not basic_issues:
                logger.warning(f"No issues found on {repo} issues page")
                # Return mock data for testing if no real issues found
                return self._mock_issues(repo, max_issues)

            # Step 2: Open each issue page to get detailed info (NO emails here - they're not visible on issue pages!)
            detailed_task = f"""
Now open the first {min(len(basic_issues), max_issues)} individual issue pages to extract detailed information.
For each issue page, extract:
- issue_body (the full description/content of the issue)
- issue_labels (array of all label names)
- issue_created_at (creation date)
- author_profile_url (author's GitHub profile URL - click on the username to get the profile link)

Click on each issue URL from the list, then extract the detailed info.
Return as JSON: {{"detailed_issues": [array of issues with these fields]}}
Note: Emails are NOT visible on issue pages - only extract what's actually there.
"""

            # Add detailed extraction task to same agent
            list_agent.add_new_task(detailed_task)
            
            # Run detailed extraction
            detail_result = await list_agent.run(max_steps=20)  # type: ignore[func-returns-value]
            detailed_issues = self._parse_detailed_issues(detail_result, basic_issues)
            
            logger.info(f"Parsed detailed info for {len(detailed_issues)} issues")
            
            # Step 3: Visit GitHub profiles to extract contact info (emails/websites)
            # This is the ONLY place where emails are actually visible on GitHub
            enriched_issues: List[Dict[str, Any]] = []
            
            if profile_enrichment == "none":
                # Skip all enrichment
                enriched_issues = detailed_issues[:max_issues]
            elif profile_enrichment == "simple":
                # Try HTTP-only scraping (limited success rate)
                for issue in detailed_issues[:max_issues]:
                    try:
                        enriched = await self._enrich_issue_basic(issue)
                        enriched_issues.append(enriched)
                    except Exception as e:
                        logger.debug(f"Simple enrichment failed for issue {issue.get('issue_number')}: {e}")
                        enriched_issues.append(issue)
            else:  # profile_enrichment == "browser"
                # Full browser-based profile extraction
                logger.info(f"Starting Step 3: Visiting {len(detailed_issues[:max_issues])} GitHub profiles to extract contact info")
                
                # Batch profile URLs for efficient extraction
                profiles_to_visit = []
                for issue in detailed_issues[:max_issues]:
                    profile_url = issue.get("profile_url")
                    if profile_url and profile_url not in [p["url"] for p in profiles_to_visit]:
                        profiles_to_visit.append({
                            "url": profile_url,
                            "user_login": issue.get("user_login")
                        })
                
                logger.info(f"Unique profiles to visit: {len(profiles_to_visit)}")
                
                # Create a new browser agent for profile extraction
                profile_task = f"""
Visit the following GitHub profile URLs and extract contact information for each user:
{chr(10).join([f"- {p['url']} (user: {p['user_login']})" for p in profiles_to_visit[:10]])}

For each profile, extract:
- user_login (the username)
- email (if publicly visible in the profile)
- website (if listed in the profile)

Look in:
- The profile sidebar for email and website links
- The bio section
- The README.md if one is pinned

Return as JSON: {{"profiles": [{{"user_login": "username", "email": "email@example.com or null", "website": "https://site.com or null"}}]}}
"""
                
                if profiles_to_visit:
                    profile_agent = BrowserAgent(
                        task=profile_task,
                        browser=browser,
                        llm=llm,
                        flash_mode=True,
                        output_model_schema=ProfileContacts,
                    )
                    
                    try:
                        profile_result = await profile_agent.run(max_steps=len(profiles_to_visit) * 3)  # type: ignore
                        profile_data = self._parse_profile_enrichment(profile_result)
                        
                        # Merge profile data back into issues
                        for issue in detailed_issues[:max_issues]:
                            user_login = issue.get("user_login")
                            if user_login and user_login in profile_data:
                                issue["email"] = profile_data[user_login].get("email")
                                issue["website"] = profile_data[user_login].get("website")
                            else:
                                issue.setdefault("email", None)
                                issue.setdefault("website", None)
                            enriched_issues.append(issue)
                            
                        logger.info(f"Successfully enriched {len([i for i in enriched_issues if i.get('email')])} issues with emails")
                        
                    except Exception as e:
                        logger.error(f"Profile enrichment failed: {e}")
                        # Fallback to issues without email/website
                        for issue in detailed_issues[:max_issues]:
                            issue.setdefault("email", None)
                            issue.setdefault("website", None)
                            enriched_issues.append(issue)
                else:
                    enriched_issues = detailed_issues[:max_issues]

            await self._log_provenance(
                action="fetched_issues",
                details={
                    "repo": repo,
                    "max_issues": max_issues,
                    "results_found": len(enriched_issues),
                },
            )

            return enriched_issues

        except Exception as e:
            logger.error(f"GitHub issues scraping error for {repo}: {e}")
            await self._log_provenance(
                action="fetch_issues_error",
                details={"repo": repo, "error": str(e)},
            )
            return []
        finally:
            # Cleanup browser session
            try:
                await browser.kill()  # type: ignore[func-returns-value]
            except Exception:
                pass

    async def enrich_author_contacts(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich an issue with author contact information by visiting their GitHub profile.
        
        Args:
            issue: Issue dict with profile_url
            
        Returns:
            Enhanced issue dict with email and website fields
        """
        profile_url = issue.get("profile_url")
        if not profile_url:
            issue["email"] = None
            issue["website"] = None
            return issue

        try:
            profile_meta = await self._open_profile_and_extract(profile_url)
            issue.update(profile_meta)
        except Exception as e:
            logger.debug(f"Failed to extract profile info from {profile_url}: {e}")
            issue["email"] = None
            issue["website"] = None

        return issue

    async def _open_issue_list(self, repo: str) -> bool:
        """Navigate to the GitHub issues page for the specified repository."""
        if not self.browser:
            return False

        url = f"https://github.com/{repo}/issues"
        
        try:
            llm = ChatOpenAI(model="gpt-4.1")
            
            nav_task = f"""
Navigate to {url} and verify the issues page loads successfully.
Wait for the page to fully load and show the list of issues.
Return "success" when you can see GitHub issues listed on the page.
"""

            agent = BrowserAgent(
                task=nav_task,
                browser=self.browser,
                llm=llm,
                flash_mode=True,
                browser_profile=self.browser_profile,
            )

            result = await agent.run(max_steps=5)  # type: ignore[func-returns-value]
            result_text = self._stringify_result(result).lower()
            return "success" in result_text

        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            return False

    def _parse_issue_cards(self, result: Any) -> List[Dict[str, Any]]:
        """Parse Browser-Use agent result into issue dictionaries."""
        issues = []
        
        # Try to get structured output first
        try:
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
                for item in items:
                    if isinstance(item, BaseModel):
                        item = item.model_dump()
                    if isinstance(item, dict):
                        issues.append(item)
                        
                return issues
        except Exception:
            pass

        # Fallback to text parsing
        text = self._stringify_result(result)
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data["items"]
        except Exception:
            pass

        # Last resort: regex extraction
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass

        return []

    async def _open_profile_and_extract(self, profile_url: str) -> Dict[str, Optional[str]]:
        """Extract email and website from a GitHub profile page."""
        if not self.browser:
            return {"email": None, "website": None}

        try:
            llm = ChatOpenAI(model="gpt-4.1")
            
            extract_task = f"""
Navigate to {profile_url} and extract the user's contact information:
- email address (if publicly visible)
- website/blog URL (if listed)

Return as JSON: {{"email": "user@example.com or null", "website": "https://example.com or null"}}
Look in the profile sidebar, bio section, and README for contact info.
"""

            agent = BrowserAgent(
                task=extract_task,
                browser=self.browser,
                llm=llm,
                flash_mode=True,
                browser_profile=self.browser_profile,
            )

            result = await agent.run(max_steps=6)  # type: ignore[func-returns-value]
            
            # Parse result
            text = self._stringify_result(result)
            try:
                data = json.loads(text)
                email = data.get("email")
                website = data.get("website")
                
                # Additional email extraction from website if needed
                if not email and website:
                    email = await self._extract_email_from_website(website)
                    
                return {"email": email, "website": website}
            except Exception:
                pass

            # Fallback regex extraction
            email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
            url_match = re.search(r"https?://[^\s<>\"]+", text)
            
            return {
                "email": email_match.group(0) if email_match else None,
                "website": url_match.group(0) if url_match else None,
            }

        except Exception as e:
            logger.debug(f"Profile extraction failed for {profile_url}: {e}")
            return {"email": None, "website": None}

    async def _extract_email_from_website(self, url: str, max_bytes: int = 200_000) -> Optional[str]:
        """Attempt to extract an email address from a personal website."""
        if not url or not url.startswith(("http://", "https://")):
            return None

        try:
            # Simple regex-based email extraction from website content
            # In production, you might want to use a proper HTML parser
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        content = await response.text()
                        # Truncate to avoid processing huge pages
                        content = content[:max_bytes]
                        
                        # Look for email addresses
                        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
                        matches = re.findall(email_pattern, content)
                        
                        # Return first reasonable email (avoid common false positives)
                        for email in matches:
                            if not any(skip in email.lower() for skip in ["noreply", "example", "test", "spam"]):
                                return email
                                
        except Exception as e:
            logger.debug(f"Website email extraction failed for {url}: {e}")

        return None

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

    def _mock_issues(self, repo: str, max_issues: int) -> List[Dict[str, Any]]:
        """Return mock GitHub issues for testing when Browser-Use is unavailable."""
        mock_data = [
            {
                "issue_number": 1234,
                "issue_title": "Error installing scanpy on M1 Mac",
                "issue_labels": ["question", "installation"],
                "issue_created_at": "2024-09-01",
                "user_login": "biouser123",
                "profile_url": "https://github.com/biouser123",
                "issue_url": f"https://github.com/{repo}/issues/1234",
                "email": None,
                "website": None,
            },
            {
                "issue_number": 1235,
                "issue_title": "AnnData object manipulation help needed",
                "issue_labels": ["help wanted", "usage"],
                "issue_created_at": "2024-09-02",
                "user_login": "newbie_scientist",
                "profile_url": "https://github.com/newbie_scientist",
                "issue_url": f"https://github.com/{repo}/issues/1235",
                "email": "scientist@university.edu",
                "website": "https://scientist-blog.example.com",
            },
            {
                "issue_number": 1236,
                "issue_title": "Beginner question: How to load my data?",
                "issue_labels": ["question", "beginner"],
                "issue_created_at": "2024-09-03",
                "user_login": "confused_researcher",
                "profile_url": "https://github.com/confused_researcher",
                "issue_url": f"https://github.com/{repo}/issues/1236",
                "email": None,
                "website": None,
            },
        ]
        
        return mock_data[:max_issues]

    async def _enrich_issue_basic(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """
        Basic enrichment of issue without additional browser sessions.
        Avoids WebSocket connection issues by not creating new browser agents.
        """
        # Add basic email/website fields if not present
        issue.setdefault("email", None)
        issue.setdefault("website", None)
        
        # Try simple website email extraction if we have a website but no email
        profile_url = issue.get("profile_url")
        if profile_url and not issue.get("email"):
            try:
                # Extract email from website without browser automation to avoid connection issues
                # This is a simplified approach that avoids multiple browser sessions
                website = await self._extract_email_simple(profile_url)
                if website:
                    issue["website"] = website
                    # Try to extract email from the website
                    email = await self._extract_email_from_website(website)
                    if email:
                        issue["email"] = email
            except Exception as e:
                logger.debug(f"Simple enrichment failed for {profile_url}: {e}")
        
        return issue

    async def _extract_email_simple(self, profile_url: str) -> Optional[str]:
        """
        Simple website extraction from GitHub profile without Browser-Use to avoid connection issues.
        Looks for website links in GitHub profile via API or simple scraping.
        """
        try:
            # Simple regex-based approach to avoid browser session conflicts
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get(profile_url, timeout=10) as response:
                    if response.status == 200:
                        content = await response.text()
                        
                        # Look for website links in GitHub profile HTML
                        website_patterns = [
                            r'href="(https?://[^"]+)"[^>]*>\s*<svg[^>]*octicon-link',  # Website link with link icon
                            r'<a[^>]*href="(https?://[^"]+)"[^>]*class="[^"]*Link[^"]*"',  # General website links
                            r'"blog":"([^"]+)"',  # JSON data in page
                        ]
                        
                        for pattern in website_patterns:
                            matches = re.findall(pattern, content)
                            for match in matches:
                                if match and not any(skip in match.lower() for skip in ["github.com", "linkedin.com", "twitter.com"]):
                                    return match
        except Exception as e:
            logger.debug(f"Simple website extraction failed for {profile_url}: {e}")
        
        return None

    def _parse_basic_issues(self, result: Any) -> List[Dict[str, Any]]:
        """Parse basic issue list from the Browser-Use agent result."""
        basic_issues = []
        
        try:
            # Try to get final result using browser-use's API
            if hasattr(result, "final_result") and callable(result.final_result):
                final_result_data = result.final_result()
                if final_result_data:
                    try:
                        # Parse JSON from final result
                        if isinstance(final_result_data, str):
                            data = json.loads(final_result_data)
                        else:
                            data = final_result_data
                            
                        if isinstance(data, dict) and "issues" in data:
                            raw_issues = data["issues"]
                            logger.info(f"Found {len(raw_issues)} issues from final_result")
                            return self._normalize_issue_format(raw_issues)
                    except json.JSONDecodeError as je:
                        logger.debug(f"JSON decode error in final_result: {je}")
        except Exception as e:
            logger.debug(f"final_result parsing failed: {e}")
        
        try:
            # Browser-Use structured output - property access (not method call)
            if hasattr(result, "structured_output") and result.structured_output is not None:
                structured = result.structured_output
                logger.info(f"Found structured output: {type(structured)} - {structured}")
                
                # The structured output should be the actual parsed object
                if isinstance(structured, dict):
                    if "issues" in structured:
                        raw_issues = structured["issues"]
                        logger.info(f"Found {len(raw_issues)} issues from structured_output")
                        return self._normalize_issue_format(raw_issues)
                elif isinstance(structured, BaseModel):
                    data_obj = structured.model_dump()
                    if "issues" in data_obj:
                        raw_issues = data_obj["issues"]
                        logger.info(f"Found {len(raw_issues)} issues from structured BaseModel")
                        return self._normalize_issue_format(raw_issues)
        except Exception as e:
            logger.debug(f"Structured output parsing failed: {e}")
        
        try:
            # Browser-Use history parsing - extract from all_results
            if hasattr(result, 'all_results') and result.all_results:
                # Check both final action and all actions for extracted_content
                for action_result in reversed(result.all_results):  # Check from most recent
                    if hasattr(action_result, 'extracted_content'):
                        extracted_text = str(action_result.extracted_content)
                        logger.debug(f"Parsing from extracted_content: {extracted_text[:200]}...")
                        
                        # Look for JSON in the extracted content
                        json_match = re.search(r'\{[^{}]*"issues"[^{}]*:\s*\[[^\]]*\][^{}]*\}', extracted_text, re.DOTALL)
                        if json_match:
                            try:
                                data = json.loads(json_match.group(0))
                                if "issues" in data:
                                    raw_issues = data["issues"]
                                    logger.info(f"Found {len(raw_issues)} issues from extracted_content JSON")
                                    return self._normalize_issue_format(raw_issues)
                            except json.JSONDecodeError as je:
                                logger.debug(f"JSON decode error: {je}")
                
                # Fallback to long_term_memory
                final_action = result.all_results[-1]
                if hasattr(final_action, 'long_term_memory'):
                    memory_text = str(final_action.long_term_memory)
                    logger.debug(f"Parsing from long_term_memory: {memory_text[:200]}...")
                    
                    # Look for JSON in the memory text
                    json_match = re.search(r'\{[^{}]*"issues"[^{}]*:\s*\[[^\]]*\][^{}]*\}', memory_text, re.DOTALL)
                    if json_match:
                        try:
                            data = json.loads(json_match.group(0))
                            if "issues" in data:
                                raw_issues = data["issues"]
                                logger.info(f"Found {len(raw_issues)} issues from memory JSON")
                                return self._normalize_issue_format(raw_issues)
                        except json.JSONDecodeError as je:
                            logger.debug(f"JSON decode error: {je}")
                            
                    # Fallback: simple regex for issue data
                    issue_pattern = r'issue_number:\s*([^,\n]+)[^}]*issue_title:\s*([^,\n]+)[^}]*issue_url:\s*([^,\n]+)[^}]*user_login:\s*([^,\n}]+)'
                    matches = re.findall(issue_pattern, memory_text, re.DOTALL)
                    if matches:
                        raw_issues = []
                        for match in matches:
                            raw_issues.append({
                                "issue_number": match[0].strip().strip('"'),
                                "issue_title": match[1].strip().strip('"'),
                                "issue_url": match[2].strip().strip('"'),
                                "user_login": match[3].strip().strip('"'),
                            })
                        logger.info(f"Found {len(raw_issues)} issues from regex parsing")
                        return self._normalize_issue_format(raw_issues)
        except Exception as e:
            logger.debug(f"History parsing failed: {e}")

        logger.warning("Failed to parse any issues from Browser-Use result")
        return basic_issues

    def _normalize_issue_format(self, raw_issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize issue format and add missing fields."""
        normalized = []
        
        for issue in raw_issues:
            if not isinstance(issue, dict):
                continue
                
            # Clean up issue_number (remove # prefix if present)
            issue_number = str(issue.get("issue_number", ""))
            if issue_number.startswith("#"):
                issue_number = issue_number[1:]
            
            # Generate profile_url if not present
            user_login = issue.get("user_login", "")
            profile_url = issue.get("profile_url") or f"https://github.com/{user_login}" if user_login else ""
            
            normalized_issue = {
                "issue_number": int(issue_number) if issue_number.isdigit() else 0,
                "issue_title": issue.get("issue_title", ""),
                "issue_url": issue.get("issue_url", ""),
                "user_login": user_login,
                "profile_url": profile_url,
                "issue_body": issue.get("issue_body", ""),
                "issue_labels": issue.get("issue_labels", []),
                "issue_created_at": issue.get("issue_created_at"),
                "email": issue.get("email"),
                "website": issue.get("website"),
            }
            
            normalized.append(normalized_issue)
            
        return normalized

    def _parse_detailed_issues(self, result: Any, basic_issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse detailed issue information and merge with basic issue data."""
        text = self._stringify_result(result)
        detailed_issues = []
        
        try:
            # Try JSON parsing first
            data = json.loads(text)
            if isinstance(data, dict) and "detailed_issues" in data:
                detailed_data = data["detailed_issues"]
            elif isinstance(data, list):
                detailed_data = data
            else:
                detailed_data = []
                
            # Merge detailed data with basic issues
            for i, basic_issue in enumerate(basic_issues):
                merged_issue = basic_issue.copy()
                
                # Try to find matching detailed data
                if i < len(detailed_data) and isinstance(detailed_data[i], dict):
                    detail = detailed_data[i]
                    merged_issue.update({
                        "issue_body": detail.get("issue_body", ""),
                        "issue_labels": detail.get("issue_labels", []),
                        "issue_created_at": detail.get("issue_created_at"),
                        "profile_url": detail.get("author_profile_url") or basic_issue.get("profile_url", f"https://github.com/{basic_issue.get('user_login', '')}"),
                        "email": detail.get("author_email"),
                        "website": detail.get("author_website"),
                    })
                else:
                    # Fill in missing fields with defaults
                    merged_issue.update({
                        "issue_body": "",
                        "issue_labels": [],
                        "issue_created_at": None,
                        "profile_url": merged_issue.get("profile_url") or f"https://github.com/{merged_issue.get('user_login', '')}",
                        "email": None,
                        "website": None,
                    })
                
                detailed_issues.append(merged_issue)
                
        except Exception as e:
            logger.debug(f"Failed to parse detailed issues: {e}")
            # Fallback: use basic issues with empty detailed fields
            for basic_issue in basic_issues:
                merged_issue = basic_issue.copy()
                merged_issue.update({
                    "issue_body": "",
                    "issue_labels": [],
                    "issue_created_at": None,
                    "profile_url": merged_issue.get("profile_url") or f"https://github.com/{merged_issue.get('user_login', '')}",
                    "email": None,
                    "website": None,
                })
                detailed_issues.append(merged_issue)

        return detailed_issues

    def _parse_profile_enrichment(self, result: Any) -> Dict[str, Dict[str, Optional[str]]]:
        """
        Parse profile enrichment results from browser agent using structured output.
        
        Returns:
            Dict mapping user_login to their contact info (email, website)
        """
        profile_data = {}
        
        try:
            # Try to get structured result using browser-use's final_result() method
            if hasattr(result, "final_result") and callable(result.final_result):
                final_result_data = result.final_result()
                if final_result_data:
                    try:
                        # Parse structured output using ProfileContacts model
                        parsed_contacts = ProfileContacts.model_validate_json(final_result_data)
                        for profile in parsed_contacts.profiles:
                            profile_data[profile.user_login] = {
                                "email": profile.email,
                                "website": profile.website
                            }
                        logger.info(f"Parsed {len(profile_data)} profiles from structured output")
                        return profile_data
                    except Exception as e:
                        logger.debug(f"Structured parsing failed, trying JSON: {e}")
                        
                        # Fallback to manual JSON parsing
                        if isinstance(final_result_data, str):
                            data = json.loads(final_result_data)
                        else:
                            data = final_result_data
                            
                        if isinstance(data, dict) and "profiles" in data:
                            profiles = data["profiles"]
                            if isinstance(profiles, list):
                                for profile in profiles:
                                    if isinstance(profile, dict) and "user_login" in profile:
                                        user_login = profile["user_login"]
                                        profile_data[user_login] = {
                                            "email": profile.get("email"),
                                            "website": profile.get("website")
                                        }
        except Exception as e:
            logger.debug(f"final_result parsing failed: {e}")
        
        try:
            # Fallback to text-based parsing if structured output fails
            text = self._stringify_result(result)
            
            # Try parsing as JSON
            data = json.loads(text) if isinstance(text, str) else text
            
            # Handle {"profiles": [...]} format
            if isinstance(data, dict) and "profiles" in data:
                profiles = data["profiles"]
                if isinstance(profiles, list):
                    for profile in profiles:
                        if isinstance(profile, dict) and "user_login" in profile:
                            user_login = profile["user_login"]
                            profile_data[user_login] = {
                                "email": profile.get("email"),
                                "website": profile.get("website")
                            }
            # Handle direct list format
            elif isinstance(data, list):
                for profile in data:
                    if isinstance(profile, dict) and "user_login" in profile:
                        user_login = profile["user_login"]
                        profile_data[user_login] = {
                            "email": profile.get("email"),
                            "website": profile.get("website")
                        }
                        
        except json.JSONDecodeError:
            # Final fallback to regex extraction if JSON parsing fails
            logger.debug("JSON parsing failed, using regex fallback")
            text = self._stringify_result(result)
            
            # Look for patterns like: user_login: "username", email: "email@example.com"
            profile_pattern = r'user_login["\s:]+([^",\n]+)[^}]*email["\s:]+([^",\n]+)[^}]*website["\s:]+([^",\n}]+)'
            matches = re.findall(profile_pattern, text, re.DOTALL)
            
            for match in matches:
                user_login = match[0].strip().strip('"')
                email = match[1].strip().strip('"') if match[1].strip().strip('"') != "null" else None
                website = match[2].strip().strip('"') if match[2].strip().strip('"') != "null" else None
                
                profile_data[user_login] = {
                    "email": email,
                    "website": website
                }
        except Exception as e:
            logger.debug(f"Profile enrichment parsing failed: {e}")
        
        logger.info(f"Successfully parsed contact info for {len(profile_data)} profiles")
        return profile_data

    async def _log_provenance(self, action: str, details: Dict[str, Any]) -> None:
        """Log action for audit trail"""
        try:
            from app.core.utils.provenance import log_provenance
            await log_provenance(actor="github_issues_scraper", action=action, details=details)
        except Exception as e:
            logger.debug(f"Provenance logging failed: {e}")
