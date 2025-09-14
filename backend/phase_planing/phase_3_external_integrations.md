# Phase 3: External Integrations

## Overview
Implement the external tool integrations using Browser-Use for web scraping and AgentMail for email automation, following the specific patterns from `browser-use-doc.md` and `agentmail-doc.md`.

## Goals
- Implement Browser-Use agents for NCBI/GEO and LinkedIn scraping
- Set up AgentMail client for email automation
- Create webhook receivers for email reply handling
- Establish robust error handling and retry mechanisms
- Ensure proper provenance logging for all external interactions

## Browser-Use Implementation

### 1. NCBI/GEO Scraper
**Direct Python implementation using browser_use library as per `browser-use-doc.md`**

```python
# app/core/scrapers/geo_scraper.py
import asyncio
from typing import List, Dict, Any, Optional
from browser_use import Agent, Browser, ChatOpenAI, BrowserProfile
from pydantic import BaseModel
import json
import re

class GEODataset(BaseModel):
    """Structured output for GEO dataset"""
    accession: str
    title: str
    organism: str
    experiment_type: List[str]  # modalities
    samples: int
    series_type: str
    pubmed_id: Optional[str]
    download_link: str
    contact_name: Optional[str]
    contact_email: Optional[str]

class GEOScraper:
    """
    NCBI GEO scraper using Browser-Use
    Reference: browser-use-doc.md - Direct Python usage pattern
    """
    
    def __init__(self, headless: bool = False):
        # Speed optimization from browser-use-doc.md
        self.browser_profile = BrowserProfile(
            minimum_wait_page_load_time=0.5,  # Slightly higher for stability
            wait_between_actions=0.3,
            headless=headless,
        )
        
        # Use dedicated profile directory for GEO
        self.browser = Browser(
            user_data_dir='./temp-profile-geo',
            headless=headless,
        )
        
        # Speed optimization instructions from browser-use-doc.md
        self.speed_prompt = """
        Speed optimization instructions:
        - Be extremely concise and direct in your responses
        - Get to the goal as quickly as possible
        - Extract only the required data fields
        - Use multi-action sequences whenever possible to reduce steps
        """
    
    async def search_datasets(
        self, 
        query: str, 
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search GEO for datasets matching the query
        
        Implementation follows browser-use-doc.md patterns:
        - Create agent with specific task
        - Use flash_mode for speed
        - Chain tasks if needed for pagination
        """
        
        # Keep browser alive for potential follow-up tasks
        await self.browser.start()
        
        try:
            # Task string following browser-use-doc.md pattern
            search_task = f"""
            1. Navigate to https://www.ncbi.nlm.nih.gov/gds
            2. Search for: {query}
            3. Filter results by: Dataset, Homo sapiens if cancer-related
            4. For the first {max_results} results, extract:
               - Accession number (GSE/GDS ID)
               - Title
               - Organism
               - Experiment type/Platform
               - Number of samples
               - Publication info if available
            5. Return as structured JSON list
            """
            
            # Create agent with ChatOpenAI as shown in browser-use-doc.md
            agent = Agent(
                task=search_task,
                browser_session=self.browser,
                llm=ChatOpenAI(model='gpt-4o-mini'),  # Using faster model
                flash_mode=True,  # Maximum speed as per browser-use-doc.md
                browser_profile=self.browser_profile,
                extend_system_message=self.speed_prompt,
            )
            
            # Run the search
            result = await agent.run(max_steps=15)
            
            # Parse the result
            datasets = self._parse_search_results(result)
            
            # For datasets needing more info, chain tasks (browser-use-doc.md pattern)
            enriched_datasets = []
            for dataset in datasets[:max_results]:
                if self._needs_enrichment(dataset):
                    enriched = await self._enrich_dataset(dataset, agent)
                    enriched_datasets.append(enriched)
                else:
                    enriched_datasets.append(dataset)
            
            # Log provenance
            await self._log_provenance(
                action="searched_geo",
                details={
                    "query": query,
                    "results_found": len(enriched_datasets)
                }
            )
            
            return enriched_datasets
            
        except Exception as e:
            print(f"GEO search error: {e}")
            return []
        finally:
            # Keep alive for potential chained tasks
            if not self.browser_profile.keep_alive:
                await self.browser.kill()
    
    async def _enrich_dataset(
        self, 
        dataset: Dict[str, Any], 
        agent: Agent
    ) -> Dict[str, Any]:
        """
        Enrich dataset with detailed information
        Using task chaining from browser-use-doc.md
        """
        
        # Add new task to existing agent session
        detail_task = f"""
        Navigate to the GEO page for accession {dataset.get('accession')}
        Extract:
        - Contact person name and email
        - Download links for processed data
        - PubMed ID if available
        - Detailed sample information
        Return as JSON
        """
        
        agent.add_new_task(detail_task)
        detail_result = await agent.run(max_steps=5)
        
        # Merge enriched data
        enrichment = self._parse_detail_result(detail_result)
        dataset.update(enrichment)
        
        return dataset
    
    def _parse_search_results(self, result: Any) -> List[Dict[str, Any]]:
        """Parse agent output to structured datasets"""
        # Extract JSON from agent response
        try:
            # Look for JSON in the response
            json_match = re.search(r'\[.*\]', str(result), re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        # Fallback parsing logic
        return []
    
    def _needs_enrichment(self, dataset: Dict[str, Any]) -> bool:
        """Check if dataset needs additional detail fetching"""
        return not dataset.get('contact_email') or not dataset.get('download_link')
    
    def _parse_detail_result(self, result: Any) -> Dict[str, Any]:
        """Parse detailed dataset information"""
        # Implementation specific to GEO detail pages
        return {}
    
    async def _log_provenance(self, action: str, details: Dict[str, Any]):
        """Log action for audit trail"""
        from app.core.utils.provenance import log_provenance
        await log_provenance(
            actor="geo_scraper",
            action=action,
            details=details
        )
```

### 2. LinkedIn Colleague Finder
**Direct Python implementation using browser_use library**

```python
# app/core/scrapers/linkedin_scraper.py
import asyncio
from typing import List, Dict, Any, Optional
from browser_use import Agent, Browser, ChatOpenAI, BrowserProfile
from pydantic import BaseModel, EmailStr
import re

class LinkedInContact(BaseModel):
    """Structured LinkedIn employee data"""
    name: str
    job_title: str
    department: Optional[str]
    company: str
    linkedin_url: str
    email_suggestions: List[str] = []
    keywords_matched: List[str] = []
    relevance_score: float = 0.0

class LinkedInScraper:
    """
    LinkedIn employee finder using Browser-Use
    Reference: browser-use-doc.md - Multiple browser pattern
    """
    
    def __init__(self, headless: bool = False):
        # Create dedicated browser for LinkedIn
        self.browser = Browser(
            user_data_dir='./temp-profile-linkedin',
            headless=headless,
        )
        
        # Speed profile from browser-use-doc.md
        self.browser_profile = BrowserProfile(
            minimum_wait_page_load_time=1.0,  # LinkedIn needs more time
            wait_between_actions=0.5,
            headless=headless,
        )
    
    async def find_company_employees(
        self,
        company: str,
        departments: List[str],
        keywords: List[str],
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find employees at company matching department/keywords
        
        Following browser-use-doc.md patterns for complex multi-step tasks
        """
        
        await self.browser.start()
        
        try:
            # Build search query
            dept_filter = " OR ".join([f'"{dept}"' for dept in departments])
            keyword_filter = " OR ".join(keywords)
            
            # Multi-step task as per browser-use-doc.md
            search_task = f"""
            LinkedIn employee search task:
            1. Navigate to linkedin.com/search/results/people/
            2. Search filters:
               - Current company: "{company}"
               - Keywords: {keyword_filter}
               - Title/Department keywords: {dept_filter}
            3. For first {max_results} results, extract:
               - Full name
               - Current job title
               - Department (if visible)
               - Profile URL
               - Any visible keywords: {', '.join(keywords)}
            4. DO NOT attempt to view full profiles (requires login)
            5. Return structured JSON with all found employees
            
            Important: Work with public search results only
            """
            
            # Create agent
            agent = Agent(
                task=search_task,
                browser_session=self.browser,
                llm=ChatOpenAI(model='gpt-4o-mini'),
                flash_mode=True,
                browser_profile=self.browser_profile,
            )
            
            # Execute search
            result = await agent.run(max_steps=20)
            
            # Parse results
            employees = self._parse_employee_results(result)
            
            # Enrich with email patterns
            enriched = [self._generate_email_suggestions(emp, company) 
                       for emp in employees]
            
            # Calculate relevance scores
            scored = [self._calculate_relevance(emp, keywords, departments)
                     for emp in enriched]
            
            # Log provenance
            await self._log_provenance(
                action="searched_linkedin",
                details={
                    "company": company,
                    "departments": departments,
                    "results_found": len(scored)
                }
            )
            
            return scored
            
        except Exception as e:
            print(f"LinkedIn search error: {e}")
            return []
        finally:
            await self.browser.kill()
    
    def _parse_employee_results(self, result: Any) -> List[Dict[str, Any]]:
        """Parse LinkedIn search results"""
        # Extract structured data from agent response
        try:
            # Look for JSON in response
            import json
            json_match = re.search(r'\[.*\]', str(result), re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        return []
    
    def _generate_email_suggestions(
        self, 
        employee: Dict[str, Any], 
        company: str
    ) -> Dict[str, Any]:
        """Generate potential email addresses"""
        name = employee.get('name', '').lower()
        name_parts = name.split()
        
        if len(name_parts) >= 2:
            first = name_parts[0]
            last = name_parts[-1]
            company_domain = company.lower().replace(' ', '').replace(',', '')
            
            # Common corporate email patterns
            patterns = [
                f"{first}.{last}@{company_domain}.com",
                f"{first[0]}{last}@{company_domain}.com",
                f"{first}@{company_domain}.com",
                f"{last}@{company_domain}.com",
                f"{first}_{last}@{company_domain}.com",
            ]
            
            employee['email_suggestions'] = patterns
        
        return employee
    
    def _calculate_relevance(
        self,
        employee: Dict[str, Any],
        keywords: List[str],
        departments: List[str]
    ) -> Dict[str, Any]:
        """Calculate relevance score based on keyword matches"""
        score = 0.0
        matched_keywords = []
        
        # Check job title
        job_title = employee.get('job_title', '').lower()
        for keyword in keywords:
            if keyword.lower() in job_title:
                score += 0.2
                matched_keywords.append(keyword)
        
        # Check department match
        emp_dept = employee.get('department', '').lower()
        for dept in departments:
            if dept.lower() in emp_dept or dept.lower() in job_title:
                score += 0.3
        
        # Bonus for specific titles
        priority_titles = ['data', 'bioinformatics', 'genomics', 'research', 'scientist']
        for title in priority_titles:
            if title in job_title:
                score += 0.1
        
        employee['relevance_score'] = min(score, 1.0)
        employee['keywords_matched'] = matched_keywords
        
        return employee
    
    async def _log_provenance(self, action: str, details: Dict[str, Any]):
        """Log action for audit trail"""
        from app.core.utils.provenance import log_provenance
        await log_provenance(
            actor="linkedin_scraper",
            action=action,
            details=details
        )
```

## AgentMail Integration

### 1. AgentMail Client Setup
**Following patterns from `agentmail-doc.md`**

```python
# app/core/integrations/agentmail_client.py
from agentmail import AsyncAgentMail, AgentMail
from agentmail.core.api_error import ApiError
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, EmailStr
from app.config import settings
import asyncio

class EmailMessage(BaseModel):
    """Email message structure"""
    to: EmailStr
    from_email: EmailStr
    subject: str
    body: str
    metadata: Dict[str, Any] = {}
    attachments: List[Dict[str, Any]] = []

class AgentMailClient:
    """
    AgentMail client wrapper
    Reference: agentmail-doc.md - AsyncAgentMail usage
    """
    
    def __init__(self):
        # Initialize async client as per agentmail-doc.md
        self.client = AsyncAgentMail(
            api_key=settings.AGENTMAIL_API_KEY,
            # Optional: custom timeout as per agentmail-doc.md
            timeout=30.0
        )
        
        # Sync client for non-async contexts
        self.sync_client = AgentMail(
            api_key=settings.AGENTMAIL_API_KEY
        )
    
    async def send_email(
        self, 
        message: EmailMessage,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Send email with retry logic
        Following retry pattern from agentmail-doc.md
        """
        
        try:
            # Use with_raw_response for detailed access (agentmail-doc.md)
            response = await self.client.messages.with_raw_response.create(
                to=message.to,
                from_email=message.from_email,
                subject=message.subject,
                body=message.body,
                metadata=message.metadata,
                request_options={
                    "max_retries": max_retries,
                    "timeout_in_seconds": 20
                }
            )
            
            # Access headers and data as per agentmail-doc.md
            headers = response.headers
            data = response.data
            
            # Log provenance
            await self._log_provenance(
                action="email_sent",
                details={
                    "to": message.to,
                    "subject": message.subject,
                    "message_id": data.id if hasattr(data, 'id') else None,
                    "status": "sent"
                }
            )
            
            return {
                "success": True,
                "message_id": data.id if hasattr(data, 'id') else None,
                "thread_id": data.thread_id if hasattr(data, 'thread_id') else None,
                "headers": dict(headers) if headers else {}
            }
            
        except ApiError as e:
            # Error handling as per agentmail-doc.md
            print(f"AgentMail API error: {e.status_code}")
            print(f"Error body: {e.body}")
            
            # Log failed attempt
            await self._log_provenance(
                action="email_failed",
                details={
                    "to": message.to,
                    "error": str(e.body),
                    "status_code": e.status_code
                }
            )
            
            return {
                "success": False,
                "error": str(e.body),
                "status_code": e.status_code
            }
    
    async def create_inbox(self) -> Dict[str, Any]:
        """
        Create a new inbox for receiving replies
        Reference: agentmail-doc.md basic usage
        """
        
        try:
            inbox = await self.client.inboxes.create()
            
            return {
                "success": True,
                "inbox_id": inbox.id if hasattr(inbox, 'id') else None,
                "email": inbox.email if hasattr(inbox, 'email') else None
            }
            
        except ApiError as e:
            return {
                "success": False,
                "error": str(e.body)
            }
    
    async def list_messages(
        self, 
        inbox_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List messages in an inbox"""
        
        try:
            # Add filtering if inbox_id provided
            params = {"inbox_id": inbox_id} if inbox_id else {}
            messages = await self.client.messages.list(**params)
            
            return [
                {
                    "id": msg.id,
                    "from": msg.from_email,
                    "subject": msg.subject,
                    "received_at": msg.received_at,
                    "thread_id": msg.thread_id
                }
                for msg in messages
            ]
            
        except ApiError as e:
            print(f"Error listing messages: {e.body}")
            return []
    
    async def _log_provenance(self, action: str, details: Dict[str, Any]):
        """Log email actions for audit trail"""
        from app.core.utils.provenance import log_provenance
        await log_provenance(
            actor="agentmail_client",
            action=action,
            resource_type="email",
            details=details
        )
```

### 2. Webhook Receiver
**Webhook handling for email replies**

```python
# app/api/v1/webhooks.py
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional, Dict, Any
import hmac
import hashlib
from app.models.database import OutreachRequest
from app.core.database import get_db_session
from app.config import settings

router = APIRouter()

@router.post("/agentmail/webhook")
async def handle_agentmail_webhook(
    request: Request,
    x_agentmail_signature: Optional[str] = Header(None)
):
    """
    Handle AgentMail webhook events
    Reference: agentmail-doc.md webhook pattern
    """
    
    # Get raw body for signature verification
    body = await request.body()
    
    # Verify webhook signature (if configured)
    if settings.AGENTMAIL_WEBHOOK_SECRET:
        if not verify_webhook_signature(
            body, 
            x_agentmail_signature, 
            settings.AGENTMAIL_WEBHOOK_SECRET
        ):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse webhook payload
    payload = await request.json()
    
    # Handle different event types
    event_type = payload.get("event_type")
    
    if event_type == "message.received":
        await handle_message_received(payload)
    elif event_type == "message.delivered":
        await handle_message_delivered(payload)
    elif event_type == "message.bounced":
        await handle_message_bounced(payload)
    
    return {"status": "ok"}

async def handle_message_received(payload: Dict[str, Any]):
    """
    Handle incoming email reply
    Map to outreach request via metadata
    """
    
    message = payload.get("message", {})
    metadata = message.get("metadata", {})
    
    # Extract outreach identifiers
    dataset_id = metadata.get("dataset_id")
    thread_id = message.get("thread_id")
    
    if not (dataset_id or thread_id):
        print("Cannot map reply to outreach request")
        return
    
    async with get_db_session() as session:
        # Find outreach request
        query = session.query(OutreachRequest)
        
        if thread_id:
            query = query.filter(OutreachRequest.thread_id == thread_id)
        elif dataset_id:
            query = query.filter(OutreachRequest.dataset_id == dataset_id)
        
        outreach = await query.first()
        
        if outreach:
            # Update status
            outreach.status = "replied"
            outreach.replied_at = message.get("received_at")
            
            # Store reply content (check for attachments)
            if message.get("attachments"):
                # Flag for human review if attachments present
                outreach.approval_required = True
            
            await session.commit()
            
            # Log provenance
            await log_provenance(
                actor="webhook_receiver",
                action="reply_received",
                resource_type="outreach",
                resource_id=str(outreach.id),
                details={
                    "from": message.get("from"),
                    "has_attachments": bool(message.get("attachments"))
                }
            )

async def handle_message_delivered(payload: Dict[str, Any]):
    """Update outreach status to delivered"""
    
    message_id = payload.get("message_id")
    
    async with get_db_session() as session:
        outreach = await session.query(OutreachRequest).filter(
            OutreachRequest.message_id == message_id
        ).first()
        
        if outreach:
            outreach.status = "delivered"
            await session.commit()

async def handle_message_bounced(payload: Dict[str, Any]):
    """Handle bounced emails"""
    
    message_id = payload.get("message_id")
    reason = payload.get("reason", "unknown")
    
    async with get_db_session() as session:
        outreach = await session.query(OutreachRequest).filter(
            OutreachRequest.message_id == message_id
        ).first()
        
        if outreach:
            outreach.status = "bounced"
            # Store bounce reason in metadata
            await session.commit()
            
            # Log for investigation
            await log_provenance(
                actor="webhook_receiver",
                action="email_bounced",
                resource_id=str(outreach.id),
                details={"reason": reason}
            )

def verify_webhook_signature(
    body: bytes, 
    signature: str, 
    secret: str
) -> bool:
    """
    Verify webhook signature
    Implementation depends on AgentMail's signature method
    """
    
    if not signature:
        return False
    
    # Example HMAC-SHA256 verification
    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)

async def log_provenance(
    actor: str,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """Log webhook events for audit trail"""
    from app.core.utils.provenance import log_provenance as log_prov
    await log_prov(actor, action, resource_type, resource_id, details)
```

## Email Templates

### Professional Outreach Templates
```python
# app/utils/email_templates.py
from typing import Dict, Any
from datetime import datetime

def generate_email_template(
    template_type: str,
    **kwargs
) -> Dict[str, str]:
    """
    Generate professional email templates
    Following requirements from INSTRUCTIONS.md
    """
    
    templates = {
        "data_request": data_request_template,
        "follow_up": follow_up_template,
        "thank_you": thank_you_template
    }
    
    generator = templates.get(template_type, data_request_template)
    return generator(**kwargs)

def data_request_template(
    dataset_title: str,
    dataset_id: str,
    requester_name: str,
    requester_title: str,
    requester_company: str,
    contact_name: str,
    project_description: str,
    **kwargs
) -> Dict[str, str]:
    """
    Professional data request email
    Based on INSTRUCTIONS.md template
    """
    
    subject = f"Request for access to {dataset_id} — Cancer Research Collaboration"
    
    body = f"""Dear {contact_name},

I am {requester_name}, a {requester_title} at {requester_company}. I am reaching out regarding the dataset {dataset_id} ({dataset_title}) which I found through our cancer research database search.

**Research Context:**
{project_description}

**Data Usage:**
- Purpose: Cancer biomarker discovery and validation
- Analysis: The data will be used for computational analysis only
- Compliance: We will follow all institutional data sharing policies and ensure de-identified data handling
- Attribution: Proper citation and acknowledgment will be provided in any publications

**Next Steps:**
If access requires specific agreements or procedures, please let me know the process. I am happy to:
- Complete any required data use agreements
- Provide additional project details
- Schedule a brief call to discuss the collaboration

Thank you for your time and for making this valuable data available to the research community.

Best regards,
{requester_name}
{requester_title}
{requester_company}

---
*This outreach was sent via the Biodata Assistant platform on behalf of {requester_name}.*
*Reference ID: {kwargs.get('outreach_id', 'N/A')}*

**Important Note:** If this dataset contains clinical PHI or sensitive patient data, please do not send it directly via email. Please contact your data governance office for proper transfer procedures.
"""
    
    return {
        "subject": subject,
        "body": body
    }

def follow_up_template(
    original_request_date: str,
    dataset_title: str,
    contact_name: str,
    requester_name: str,
    **kwargs
) -> Dict[str, str]:
    """Follow-up email template"""
    
    subject = f"Follow-up: Data Access Request for {dataset_title}"
    
    body = f"""Dear {contact_name},

I hope this message finds you well. I wanted to follow up on my request from {original_request_date} regarding access to {dataset_title}.

I understand you may be busy, and I wanted to check if:
- You need any additional information about our research project
- There are specific procedures I should follow
- Another colleague handles data access requests

I remain very interested in this dataset for our cancer research work and would appreciate any guidance on next steps.

Thank you for your time.

Best regards,
{requester_name}
"""
    
    return {
        "subject": subject,
        "body": body
    }
```

## Integration Points

### 1. Update Agent Tool Functions
```python
# app/core/agents/biodatabase_agent.py - Updated tool
@bio_database_agent.tool(retries=2)
async def search_ncbi_geo_direct(
    ctx: RunContext[DatabaseSearchParams]
) -> List[Dict[str, Any]]:
    """
    Direct Browser-Use integration for GEO search
    Replaces the microservice call with direct Python usage
    """
    from app.core.scrapers.geo_scraper import GEOScraper
    
    scraper = GEOScraper(headless=True)
    results = await scraper.search_datasets(
        query=ctx.deps.query,
        max_results=ctx.deps.max_results
    )
    
    return results

# app/core/agents/colleagues_agent.py - Updated tool
@colleagues_agent.tool
async def search_linkedin_direct(
    ctx: RunContext[ColleagueSearchParams]
) -> List[Dict[str, Any]]:
    """
    Direct Browser-Use integration for LinkedIn search
    """
    from app.core.scrapers.linkedin_scraper import LinkedInScraper
    
    scraper = LinkedInScraper(headless=True)
    results = await scraper.find_company_employees(
        company=ctx.deps.company,
        departments=ctx.deps.departments,
        keywords=ctx.deps.keywords,
        max_results=10
    )
    
    return results

# app/core/agents/email_agent.py - Updated tool
@email_agent.tool(retries=2)
async def send_via_agentmail_direct(
    ctx: RunContext[EmailOutreachParams],
    email_content: Dict[str, str]
) -> Dict[str, Any]:
    """
    Direct AgentMail SDK integration
    """
    from app.core.integrations.agentmail_client import AgentMailClient, EmailMessage
    
    client = AgentMailClient()
    
    message = EmailMessage(
        to=ctx.deps.contact_email,
        from_email=ctx.deps.requester_email,
        subject=email_content["subject"],
        body=email_content["body"],
        metadata={
            "dataset_id": ctx.deps.dataset_id,
            "thread_type": "data_request",
            "requester": ctx.deps.requester_email
        }
    )
    
    result = await client.send_email(message)
    return result
```

## Testing & Validation

### Integration Tests
```python
# tests/test_integrations.py
import pytest
import asyncio
from app.core.scrapers.geo_scraper import GEOScraper
from app.core.scrapers.linkedin_scraper import LinkedInScraper
from app.core.integrations.agentmail_client import AgentMailClient

@pytest.mark.asyncio
async def test_geo_scraper():
    """Test GEO scraper functionality"""
    scraper = GEOScraper(headless=True)
    
    results = await scraper.search_datasets(
        query="lung adeno
