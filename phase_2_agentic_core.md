# Phase 2: Agentic Core Development

## Overview
Implement the multi-agent system using Pydantic AI framework to orchestrate the biodata discovery and outreach workflow, leveraging the patterns and best practices from `pydantic_doc.md`.

## Goals
- Create specialized agents for each workflow component
- Implement agent orchestration and communication
- Build tool functions for agents to interact with external systems
- Establish agent state management and error handling
- Create reusable agent patterns for the hackathon

## Agent Architecture

### Core Agents

#### 1. Planner Agent
**Purpose**: Decompose user research questions and orchestrate the workflow

```python
# app/core/agents/planner_agent.py
from pydantic_ai import Agent, RunContext
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from app.models.schemas import SearchRequest
from app.core.database import get_db_session

class WorkflowStep(BaseModel):
    step_number: int
    action: str  # 'search_public'|'find_colleagues'|'send_outreach'|'summarize'
    description: str
    parameters: Dict[str, Any]
    dependencies: List[int] = []

class WorkflowPlan(BaseModel):
    research_question: str
    confirmed_requirements: Dict[str, Any]
    steps: List[WorkflowStep]
    estimated_duration_minutes: int
    requires_approval: bool = False

planner_agent = Agent[SearchRequest, WorkflowPlan](
    'openai:gpt-4o',
    deps_type=SearchRequest,
    output_type=WorkflowPlan,
    instructions="""
    You are a biomedical research planning assistant specializing in cancer research.
    Your role is to:
    1. Understand the research question deeply (focusing on cancer research)
    2. Identify required data modalities (genomics, transcriptomics, proteomics, imaging, microbiome)
    3. Plan which databases to search (NCBI/GEO, PRIDE, Ensembl)
    4. Determine if internal colleague outreach is needed
    5. Create a structured workflow plan with clear steps
    
    Focus on cancer research priorities: P53, lung adenocarcinoma, TNBC, biomarkers.
    Ensure data requirements match research goals.
    """
)

@planner_agent.tool
async def analyze_research_context(ctx: RunContext[SearchRequest], query: str) -> Dict[str, Any]:
    """Extract key research concepts and identify data requirements"""
    # Parse cancer-specific terms
    cancer_keywords = ['P53', 'TP53', 'lung adenocarcinoma', 'TNBC', 'breast cancer', 
                      'NSCLC', 'carcinoma', 'oncogene', 'tumor suppressor']
    
    modality_keywords = {
        'genomics': ['mutation', 'variant', 'SNP', 'genome', 'DNA'],
        'transcriptomics': ['RNA-seq', 'expression', 'transcript', 'scRNA-seq'],
        'proteomics': ['protein', 'mass spec', 'proteome', 'PTM'],
        'imaging': ['histology', 'microscopy', 'MRI', 'CT scan'],
        'microbiome': ['microbiota', 'bacterial', '16S']
    }
    
    found_cancer_terms = [term for term in cancer_keywords if term.lower() in query.lower()]
    found_modalities = {mod: any(kw in query.lower() for kw in keywords) 
                       for mod, keywords in modality_keywords.items()}
    
    return {
        'cancer_focus': found_cancer_terms,
        'suggested_modalities': [k for k, v in found_modalities.items() if v],
        'requires_multi_modal': sum(found_modalities.values()) > 1
    }

@planner_agent.tool
async def check_internal_resources(ctx: RunContext[SearchRequest]) -> bool:
    """Check if internal colleague search should be included"""
    # In a real implementation, check company size, departments, etc.
    return ctx.deps.include_internal
```

#### 2. Bio-Database Agent
**Purpose**: Search public biobanks using Browser-Use integration

```python
# app/core/agents/biodatabase_agent.py
from pydantic_ai import Agent, RunContext, ModelRetry
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import httpx
from app.config import settings

class DatabaseSearchParams(BaseModel):
    query: str
    database: str  # 'GEO'|'PRIDE'|'ENSEMBL'
    filters: Dict[str, Any] = {}
    max_results: int = 20

class DatasetCandidate(BaseModel):
    accession: str
    title: str
    description: Optional[str]
    modalities: List[str]
    cancer_types: List[str] = []
    sample_size: Optional[int]
    access_type: str
    download_url: Optional[str]
    contact_info: Optional[Dict[str, str]]
    relevance_score: float = Field(ge=0, le=1)

bio_database_agent = Agent[DatabaseSearchParams, List[DatasetCandidate]](
    'openai:gpt-4o',
    deps_type=DatabaseSearchParams,
    output_type=List[DatasetCandidate],
    instructions="""
    You are a biological database search specialist.
    Search public databases for cancer research datasets.
    Focus on finding relevant datasets with clear cancer associations.
    Evaluate data quality, sample size, and accessibility.
    Prioritize datasets with processed data over raw data for hackathon speed.
    """
)

@bio_database_agent.tool(retries=2)
async def search_ncbi_geo(ctx: RunContext[DatabaseSearchParams]) -> List[Dict[str, Any]]:
    """Search NCBI GEO database via Browser-Use service"""
    async with httpx.AsyncClient() as client:
        try:
            # Call Browser-Use microservice
            response = await client.post(
                f"{settings.BROWSER_SERVICE_URL}/scrape/geo",
                json={
                    "query": ctx.deps.query,
                    "max_results": ctx.deps.max_results,
                    "filters": ctx.deps.filters
                },
                timeout=30.0
            )
            
            if response.status_code == 429:
                raise ModelRetry("Rate limited, retrying...")
            
            response.raise_for_status()
            results = response.json()
            
            # Log provenance
            await log_provenance(
                actor="bio_database_agent",
                action="searched_geo",
                details={"query": ctx.deps.query, "results_count": len(results)}
            )
            
            return results
            
        except httpx.TimeoutException:
            raise ModelRetry("Search timeout, retrying with smaller batch")
        except Exception as e:
            print(f"GEO search error: {e}")
            return []

@bio_database_agent.tool
async def evaluate_dataset_relevance(
    ctx: RunContext[DatabaseSearchParams], 
    dataset: Dict[str, Any]
) -> float:
    """Score dataset relevance to research question"""
    score = 0.0
    
    # Check cancer type match
    if any(cancer in dataset.get('title', '').lower() 
           for cancer in ['cancer', 'carcinoma', 'tumor', 'oncology']):
        score += 0.3
    
    # Check modality match
    query_lower = ctx.deps.query.lower()
    if any(mod in dataset.get('modalities', []) 
           for mod in ['rna-seq', 'proteomics'] if mod in query_lower):
        score += 0.3
    
    # Sample size bonus
    sample_size = dataset.get('sample_size', 0)
    if sample_size > 100:
        score += 0.2
    elif sample_size > 50:
        score += 0.1
    
    # Public access bonus
    if dataset.get('access_type') == 'public':
        score += 0.2
    
    return min(score, 1.0)
```

#### 3. Colleagues Agent
**Purpose**: Find internal data owners via LinkedIn

```python
# app/core/agents/colleagues_agent.py
from pydantic_ai import Agent, RunContext
from typing import List, Dict, Optional
from pydantic import BaseModel, EmailStr
import httpx
from app.config import settings

class ColleagueSearchParams(BaseModel):
    company: str
    departments: List[str] = ["Bioinformatics", "Genomics", "Oncology", "Data Science"]
    keywords: List[str] = []

class InternalContact(BaseModel):
    name: str
    email: Optional[EmailStr]
    job_title: str
    department: str
    linkedin_url: Optional[str]
    relevance_score: float
    reason_for_contact: str

colleagues_agent = Agent[ColleagueSearchParams, List[InternalContact]](
    'openai:gpt-4o',
    deps_type=ColleagueSearchParams,
    output_type=List[InternalContact],
    instructions="""
    You are an internal collaboration facilitator.
    Find relevant colleagues who might have access to cancer research data.
    Focus on wet-lab departments, bioinformatics teams, and data custodians.
    Prioritize people with titles like: Research Scientist, Bioinformatician, 
    Data Manager, Lab Manager, Principal Investigator.
    """
)

@colleagues_agent.tool
async def search_linkedin_employees(
    ctx: RunContext[ColleagueSearchParams]
) -> List[Dict[str, Any]]:
    """Search company employees on LinkedIn via Browser-Use"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.BROWSER_SERVICE_URL}/scrape/linkedin",
            json={
                "company": ctx.deps.company,
                "departments": ctx.deps.departments,
                "keywords": ctx.deps.keywords + ["cancer", "genomics", "data"],
                "max_results": 10
            },
            timeout=30.0
        )
        
        if response.status_code == 200:
            employees = response.json()
            
            # Log provenance
            await log_provenance(
                actor="colleagues_agent",
                action="searched_linkedin",
                details={
                    "company": ctx.deps.company,
                    "found_count": len(employees)
                }
            )
            
            return employees
        return []

@colleagues_agent.tool
async def enrich_contact_info(
    ctx: RunContext[ColleagueSearchParams],
    employee: Dict[str, Any]
) -> Dict[str, Any]:
    """Enrich employee data with contact information"""
    # Generate professional email based on company patterns
    name_parts = employee['name'].lower().split()
    if len(name_parts) >= 2:
        # Common patterns: firstname.lastname@company.com
        email_patterns = [
            f"{name_parts[0]}.{name_parts[-1]}",
            f"{name_parts[0][0]}{name_parts[-1]}",
            f"{name_parts[0]}"
        ]
        
        # In production, verify email patterns against company directory
        employee['email_suggestions'] = [
            f"{pattern}@{ctx.deps.company.lower().replace(' ', '')}.com"
            for pattern in email_patterns
        ]
    
    return employee
```

#### 4. Email Agent
**Purpose**: Manage outreach emails via AgentMail

```python
# app/core/agents/email_agent.py
from pydantic_ai import Agent, RunContext, ModelRetry
from typing import Dict, Optional
from pydantic import BaseModel, EmailStr
from agentmail import AsyncAgentMail
from app.config import settings
from app.utils.email_templates import generate_email_template

class EmailOutreachParams(BaseModel):
    dataset_id: str
    dataset_title: str
    requester_name: str
    requester_email: EmailStr
    requester_title: str
    contact_name: str
    contact_email: EmailStr
    project_description: str
    urgency: str = "normal"  # 'low'|'normal'|'high'

class EmailResult(BaseModel):
    success: bool
    message_id: Optional[str]
    thread_id: Optional[str]
    status: str
    requires_approval: bool
    error_message: Optional[str]

email_agent = Agent[EmailOutreachParams, EmailResult](
    'openai:gpt-4o',
    deps_type=EmailOutreachParams,
    output_type=EmailResult,
    instructions="""
    You are a professional scientific communication specialist.
    Compose clear, respectful outreach emails for data access requests.
    Emphasize:
    - Research purpose and cancer research impact
    - Data handling compliance and ethics
    - Professional courtesy and collaboration
    - Clear next steps
    
    Flag for approval if:
    - Dataset contains PHI/sensitive data
    - Contact is C-level or senior management
    - Multiple datasets requested simultaneously
    """
)

@email_agent.tool
async def compose_email(ctx: RunContext[EmailOutreachParams]) -> Dict[str, str]:
    """Generate professional email content"""
    template = generate_email_template(
        template_type="data_request",
        dataset_title=ctx.deps.dataset_title,
        requester_name=ctx.deps.requester_name,
        requester_title=ctx.deps.requester_title,
        contact_name=ctx.deps.contact_name,
        project_description=ctx.deps.project_description
    )
    
    # Customize based on urgency
    if ctx.deps.urgency == "high":
        template["subject"] = f"[URGENT] {template['subject']}"
    
    return template

@email_agent.tool(retries=2)
async def send_via_agentmail(
    ctx: RunContext[EmailOutreachParams],
    email_content: Dict[str, str]
) -> Dict[str, Any]:
    """Send email through AgentMail API"""
    client = AsyncAgentMail(api_key=settings.AGENTMAIL_API_KEY)
    
    try:
        # Check if approval required
        requires_approval = await check_approval_requirements(ctx.deps)
        
        if requires_approval:
            # Queue for approval
            return {
                "success": False,
                "status": "pending_approval",
                "requires_approval": True
            }
        
        # Send email
        response = await client.messages.create(
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
        
        # Log provenance
        await log_provenance(
            actor=ctx.deps.requester_email,
            action="sent_outreach",
            resource_type="outreach",
            details={
                "recipient": ctx.deps.contact_email,
                "dataset": ctx.deps.dataset_title,
                "message_id": response.id
            }
        )
        
        return {
            "success": True,
            "message_id": response.id,
            "thread_id": response.thread_id,
            "status": "sent"
        }
        
    except Exception as e:
        if "rate_limit" in str(e).lower():
            raise ModelRetry("Rate limited, will retry")
        return {
            "success": False,
            "status": "failed",
            "error_message": str(e)
        }

async def check_approval_requirements(params: EmailOutreachParams) -> bool:
    """Check if email requires human approval"""
    # PHI/sensitive data check
    sensitive_keywords = ['PHI', 'clinical', 'patient', 'identifiable']
    if any(kw in params.dataset_title.lower() for kw in sensitive_keywords):
        return True
    
    # Senior contact check
    senior_titles = ['CEO', 'CTO', 'Director', 'VP', 'Head of']
    if any(title in params.contact_name for title in senior_titles):
        return True
    
    return False
```

#### 5. Summarizer Agent
**Purpose**: Consolidate and present results to the user

```python
# app/core/agents/summarizer_agent.py
from pydantic_ai import Agent, RunContext
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class SummaryInput(BaseModel):
    research_question: str
    datasets_found: List[Dict[str, Any]]
    contacts_identified: List[Dict[str, Any]]
    outreach_sent: List[Dict[str, Any]]
    total_duration_minutes: int

class ResearchSummary(BaseModel):
    executive_summary: str
    datasets_overview: Dict[str, Any]
    outreach_status: Dict[str, Any]
    next_steps: List[str]
    export_ready: bool
    confidence_score: float = Field(ge=0, le=1)

summarizer_agent = Agent[SummaryInput, ResearchSummary](
    'openai:gpt-4o',
    deps_type=SummaryInput,
    output_type=ResearchSummary,
    instructions="""
    You are a research intelligence analyst.
    Synthesize search results into actionable insights for cancer researchers.
    Highlight:
    - Most relevant datasets for the research question
    - Success rate of outreach attempts
    - Data availability timeline
    - Recommended prioritization
    - Potential roadblocks or alternatives
    """
)

@summarizer_agent.tool
async def analyze_dataset_quality(
    ctx: RunContext[SummaryInput]
) -> Dict[str, Any]:
    """Analyze overall quality and fit of discovered datasets"""
    datasets = ctx.deps.datasets_found
    
    quality_metrics = {
        "total_found": len(datasets),
        "publicly_available": sum(1 for d in datasets if d.get("access_type") == "public"),
        "requires_outreach": sum(1 for d in datasets if d.get("access_type") == "request"),
        "average_sample_size": sum(d.get("sample_size", 0) for d in datasets) / len(datasets) if datasets else 0,
        "modality_coverage": list(set(m for d in datasets for m in d.get("modalities", [])))
    }
    
    return quality_metrics

@summarizer_agent.tool
async def generate_export_data(
    ctx: RunContext[SummaryInput]
) -> Dict[str, Any]:
    """Prepare data for Excel/CSV export"""
    export_data = {
        "metadata": {
            "research_question": ctx.deps.research_question,
            "search_date": datetime.now().isoformat(),
            "total_results": len(ctx.deps.datasets_found)
        },
        "datasets": [
            {
                "accession": d.get("accession"),
                "title": d.get("title"),
                "source": d.get("source"),
                "modalities": ", ".join(d.get("modalities", [])),
                "sample_size": d.get("sample_size"),
                "access_type": d.get("access_type"),
                "contact": d.get("contact_info", {}).get("email"),
                "outreach_status": next(
                    (o["status"] for o in ctx.deps.outreach_sent 
                     if o.get("dataset_id") == d.get("id")),
                    "not_initiated"
                )
            }
            for d in ctx.deps.datasets_found
        ]
    }
    
    return export_data
```

## Agent Orchestration

### Main Orchestrator
```python
# app/core/agent_orchestrator.py
from typing import Dict, Any, List, Optional
from app.core.agents import (
    planner_agent, bio_database_agent, 
    colleagues_agent, email_agent, summarizer_agent
)
from app.models.schemas import SearchRequest
import asyncio

class AgentOrchestrator:
    def __init__(self):
        self.agents = {
            "planner": planner_agent,
            "bio_database": bio_database_agent,
            "colleagues": colleagues_agent,
            "email": email_agent,
            "summarizer": summarizer_agent
        }
        
    async def execute_workflow(
        self, 
        search_request: SearchRequest,
        user_email: str
    ) -> Dict[str, Any]:
        """Execute complete workflow from research question to results"""
        
        # Step 1: Planning
        plan = await planner_agent.run(search_request)
        
        # Step 2: Parallel execution of searches
        search_tasks = []
        
        # Public database searches
        for source in search_request.sources or ["GEO"]:
            search_params = DatabaseSearchParams(
                query=search_request.query,
                database=source,
                max_results=search_request.max_results
            )
            search_tasks.append(
                bio_database_agent.run(search_params)
            )
        
        # Internal colleague search (if enabled)
        if search_request.include_internal:
            colleague_params = ColleagueSearchParams(
                company="YourCompany",  # Get from user context
                keywords=plan.output.confirmed_requirements.get("keywords", [])
            )
            search_tasks.append(
                colleagues_agent.run(colleague_params)
            )
        
        # Execute searches in parallel
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Step 3: Process results and prepare outreach
        datasets = []
        contacts = []
        
        for result in results:
            if not isinstance(result, Exception):
                if hasattr(result.output, 'accession'):  # Dataset results
                    datasets.extend(result.output)
                elif hasattr(result.output, 'email'):  # Contact results
                    contacts.extend(result.output)
        
        # Step 4: Send outreach emails for datasets requiring access
        outreach_results = []
        for dataset in datasets:
            if dataset.access_type == "request" and dataset.contact_info:
                email_params = EmailOutreachParams(
                    dataset_id=dataset.accession,
                    dataset_title=dataset.title,
                    requester_name=user_email.split('@')[0],
                    requester_email=user_email,
                    requester_title="Researcher",
                    contact_name=dataset.contact_info.get("name", "Data Custodian"),
                    contact_email=dataset.contact_info["email"],
                    project_description=search_request.query
                )
                
                email_result = await email_agent.run(email_params)
                outreach_results.append(email_result.output)
        
        # Step 5: Summarize results
        summary_input = SummaryInput(
            research_question=search_request.query,
            datasets_found=[d.dict() for d in datasets],
            contacts_identified=[c.dict() for c in contacts],
            outreach_sent=outreach_results,
            total_duration_minutes=5  # Calculate actual duration
        )
        
        summary = await summarizer_agent.run(summary_input)
        
        return {
            "plan": plan.output.dict(),
            "datasets": datasets,
            "contacts": contacts,
            "outreach": outreach_results,
            "summary": summary.output.dict()
        }
```

## Utility Functions

### Provenance Logging
```python
# app/core/utils/provenance.py
from datetime import datetime
from typing import Dict, Any, Optional
from app.models.database import Provenance
from app.core.database import get_db_session

async def log_provenance(
    actor: str,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """Log action to provenance table for audit trail"""
    async with get_db_session() as session:
        provenance = Provenance(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            created_at=datetime.utcnow()
        )
        session.add(provenance)
        await session.commit()
```

## Integration with Phase 1

### API Endpoint Integration
```python
# app/api/v1/search.py
from fastapi import APIRouter, Depends, BackgroundTasks
from app.core.agent_orchestrator import AgentOrchestrator
from app.models.schemas import SearchRequest, TaskResponse

router = APIRouter()
orchestrator = AgentOrchestrator()

@router.post("/search", response_model=TaskResponse)
async def initiate_search(
    request: SearchRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user)
):
    """Initiate agent-powered dataset search"""
    
    # Create task record
    task = await create_task(
        type="search",
        user_email=current_user,
        input_data=request.dict()
    )
    
    # Run workflow in background
    background_tasks.add_task(
        orchestrator.execute_workflow,
        request,
        current_user
    )
    
    return task
```

## Testing Strategy

### Unit Tests for Each Agent
```python
# tests/test_agents.py
import pytest
from app.core.agents.planner_agent import planner_agent
from app.models.schemas import SearchRequest

@pytest.mark.asyncio
async def test_planner_agent():
    request = SearchRequest(
        query="P53 mutations in lung adenocarcinoma RNA-seq data",
        modalities=["transcriptomics"],
        cancer_types=["lung adenocarcinoma"]
    )
    
    result = await planner_agent.run(request)
    
    assert result.output.research_question == request.query
    assert len(result.output.steps) > 0
    assert any(step.action == "search_public" for step in result.output.steps)
```

## Dependencies Update for Phase 2
```
# Add to requirements.txt
pydantic-ai==0.0.9
agentmail==0.1.0
```

## Tooling Contracts and Documentation References

This phase mandates specific tool usage for each agent. The following contracts are binding to ensure consistency and to guide future contributors. Always consult the local docs in this repo before implementation:

- Browser automation and scraping: See browser-use-doc.md
- Email sending and webhooks: See agentmail-doc.md
- Agent design patterns and typed tools: See pydantic_doc.md

1) Bio-Database Agent → MUST use Browser-Use (browser-use-doc.md)
- Library: browser_use.Agent with Browser/BrowserProfile
- Task pattern: provide a concise multi-step task string (see SPEED_OPTIMIZATION_PROMPT example in browser-use-doc.md), prefer flash_mode for speed, and keep headless=False during development for visibility.
- Minimal usage (based on docs):
  from browser_use import Agent, Browser, ChatOpenAI
  browser = Browser(user_data_dir='./geo-profile', headless=False)
  agent = Agent(
      task="Open https://www.ncbi.nlm.nih.gov/; search 'lung adenocarcinoma P53'; open GEO results; extract accession, title, modality, sample size, access type, contact email if present; return JSON list",
      browser=browser,
      llm=ChatOpenAI(model='gpt-4.1-mini'),
  )
  await agent.run()
- Session chaining: If you need to open individual dataset pages after search, keep the browser session alive and chain tasks (see “Chain Agent Tasks” in browser-use-doc.md).
- Output contract: Normalize outputs to DatasetCandidate fields: accession, title, modalities[], cancer_types[], sample_size, access_type, download_url, contact_info{name,email}, link, relevance_score.

2) Colleagues Agent → MUST use Browser-Use (browser-use-doc.md)
- Task: “Open linkedin.com; search employees at {company} with keywords {oncology, genomics, data, cancer}; collect name, role, department, profile URL; if possible infer email patterns; return structured JSON”.
- Reuse the same Browser session if doing iterative refinement across pages (keep_alive=True).
- Follow speed optimization guidance from browser-use-doc.md to minimize steps, but respect polite crawling intervals.

3) Email Agent → MUST use AgentMail Python SDK (agentmail-doc.md)
- SDK import: from agentmail import AgentMail or from agentmail import AsyncAgentMail
- Minimal example from docs:
  from agentmail import AgentMail
  client = AgentMail(api_key="YOUR_API_KEY")
  client.inboxes.create()
- Apply similar pattern for sending messages and handling errors; consult the upstream reference linked in agentmail-doc.md:
  https://github.com/agentmail-to/agentmail-python/blob/HEAD/./reference.md
- Error handling: Catch ApiError (from agentmail.core.api_error import ApiError) and record provenance with error body/status_code.
- Websockets: The SDK supports sockets for low-latency updates (optional for hackathon; Phase 3 covers webhooks first).

4) Provenance and Safety (applies to all agents)
- Every tool use must call log_provenance(actor, action, details).
- Enforce human-approval gating before sending any sensitive email (PHI or restricted data hints) — email agent must return status='pending_approval' when applicable.

Implementation note on architecture
- For hackathon speed, prefer direct Python usage of browser_use per browser-use-doc.md inside the Python agents. The previously suggested Node microservice is an optional alternative, but not required for this version. If used later, keep the same JSON output contract.

References to local docs (must-read before coding)
- browser-use-doc.md: Examples for creating agents, multiple browsers, chaining tasks, and speed optimization.
- agentmail-doc.md: Installation, async usage, retries, timeouts, ApiError handling, websockets.
- pydantic_doc.md: Agent creation, tools, typed outputs, retries, streaming, and iteration patterns.

## Next Phase
Phase 3 will implement the external integrations (Browser-Use direct Python usage and AgentMail webhook handling) that these agents depend on, utilizing documentation from `browser-use-doc.md` and `agentmail-doc.md`.
