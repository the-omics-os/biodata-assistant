# Phase 5: Workflow Orchestration & Testing

## Overview
Implement the complete end-to-end workflow that ties all components together, establish comprehensive testing strategies, and prepare for hackathon deployment with focus on demonstrating the cancer research data acquisition solution.

## Goals
- Orchestrate the complete user journey from query to results
- Implement provenance logging throughout the system
- Establish safety checks for PHI/sensitive data
- Create comprehensive testing strategy
- Prepare demo scenarios for hackathon presentation

## End-to-End Workflow Implementation

### 1. Master Workflow Orchestrator
```python
# app/core/workflow/master_orchestrator.py
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio
from app.core.agents import (
    planner_agent, bio_database_agent,
    colleagues_agent, email_agent, summarizer_agent
)
from app.models.schemas import SearchRequest, WorkflowState
from app.core.database import get_db_session
from app.models.database import Task, Provenance, Dataset, OutreachRequest
from app.core.utils.provenance import ProvenanceLogger

class WorkflowState:
    """Track workflow execution state"""
    def __init__(self, task_id: str, user_email: str):
        self.task_id = task_id
        self.user_email = user_email
        self.start_time = datetime.utcnow()
        self.current_step = "initializing"
        self.steps_completed = []
        self.datasets_found = []
        self.contacts_found = []
        self.outreach_sent = []
        self.errors = []
        self.warnings = []
        
class MasterOrchestrator:
    """
    Complete workflow orchestration following user journey from INSTRUCTIONS.md
    Implements the exact flow:
    1. Research question understanding
    2. Internal colleague discovery
    3. Public database search
    4. Outreach management
    5. Result consolidation
    """
    
    def __init__(self):
        self.provenance = ProvenanceLogger()
        self.safety_checker = SafetyChecker()
        
    async def execute_complete_workflow(
        self,
        search_request: SearchRequest,
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute the complete researcher workflow
        Reference: INSTRUCTIONS.md user_flow
        """
        
        # Initialize workflow state
        task = await self._create_task(search_request, user_context)
        state = WorkflowState(task.id, user_context['email'])
        
        try:
            # Step 1: Understand research question & create plan
            await self.provenance.log(
                actor=user_context['email'],
                action="workflow_started",
                resource_type="task",
                resource_id=task.id,
                details={"query": search_request.query}
            )
            
            plan = await self._step1_understand_and_plan(search_request, state)
            
            # Step 2: Parallel search operations
            search_results = await self._step2_parallel_searches(
                search_request, 
                plan, 
                user_context, 
                state
            )
            
            # Step 3: Evaluate and prioritize results
            prioritized_results = await self._step3_evaluate_results(
                search_results, 
                search_request, 
                state
            )
            
            # Step 4: Prepare and send outreach
            outreach_results = await self._step4_handle_outreach(
                prioritized_results,
                user_context,
                state
            )
            
            # Step 5: Generate summary and prepare export
            final_summary = await self._step5_summarize_and_export(
                state,
                search_request
            )
            
            # Update task as completed
            await self._complete_task(task, final_summary)
            
            return {
                "success": True,
                "task_id": task.id,
                "execution_time_seconds": (datetime.utcnow() - state.start_time).total_seconds(),
                "summary": final_summary,
                "provenance_trail": await self.provenance.get_trail(task.id)
            }
            
        except Exception as e:
            await self._handle_workflow_error(task, state, e)
            raise
    
    async def _step1_understand_and_plan(
        self, 
        request: SearchRequest, 
        state: WorkflowState
    ) -> Dict[str, Any]:
        """
        Step 1: Deep understanding of research question
        - Extract cancer-specific concepts
        - Identify data modalities needed
        - Generate execution plan
        """
        
        state.current_step = "understanding_query"
        
        # Use planner agent to analyze query
        plan_result = await planner_agent.run(request)
        plan = plan_result.output
        
        # Validate cancer research focus
        if not self._validate_cancer_research(plan):
            state.warnings.append("Query may not be cancer-focused")
        
        # Log the plan for user confirmation
        await self.provenance.log(
            actor="planner_agent",
            action="plan_created",
            resource_type="task",
            resource_id=state.task_id,
            details={
                "steps": len(plan.steps),
                "estimated_duration": plan.estimated_duration_minutes,
                "requires_approval": plan.requires_approval
            }
        )
        
        state.steps_completed.append("plan_created")
        return plan.dict()
    
    async def _step2_parallel_searches(
        self,
        request: SearchRequest,
        plan: Dict[str, Any],
        user_context: Dict[str, Any],
        state: WorkflowState
    ) -> Dict[str, Any]:
        """
        Step 2: Execute parallel searches
        - Search public databases (GEO, PRIDE, Ensembl)
        - Find internal colleagues via LinkedIn
        - Check internal databases
        """
        
        state.current_step = "executing_searches"
        tasks = []
        
        # Public database searches
        if "GEO" in (request.sources or ["GEO"]):
            tasks.append(self._search_geo(request.query, state))
        
        # Internal colleague search (if company provided)
        if request.include_internal and user_context.get('company'):
            tasks.append(self._find_colleagues(
                user_context['company'],
                plan.get('keywords', []),
                state
            ))
        
        # Execute all searches in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        search_results = {
            "datasets": [],
            "contacts": [],
            "errors": []
        }
        
        for result in results:
            if isinstance(result, Exception):
                search_results["errors"].append(str(result))
                state.errors.append(str(result))
            elif isinstance(result, dict):
                if "datasets" in result:
                    search_results["datasets"].extend(result["datasets"])
                if "contacts" in result:
                    search_results["contacts"].extend(result["contacts"])
        
        state.datasets_found = search_results["datasets"]
        state.contacts_found = search_results["contacts"]
        state.steps_completed.append("searches_completed")
        
        return search_results
    
    async def _step3_evaluate_results(
        self,
        search_results: Dict[str, Any],
        request: SearchRequest,
        state: WorkflowState
    ) -> Dict[str, Any]:
        """
        Step 3: Evaluate and prioritize results
        - Score relevance to research question
        - Check data accessibility
        - Identify outreach requirements
        """
        
        state.current_step = "evaluating_results"
        
        prioritized = {
            "immediate_access": [],  # Public datasets
            "requires_outreach": [],  # Need email request
            "restricted": [],  # May need special approval
            "contacts_for_outreach": []
        }
        
        # Categorize datasets
        for dataset in search_results.get("datasets", []):
            # PHI/sensitive data check
            if self.safety_checker.contains_phi_indicators(dataset):
                dataset["requires_approval"] = True
                dataset["approval_reason"] = "May contain PHI"
            
            if dataset.get("access_type") == "public":
                prioritized["immediate_access"].append(dataset)
            elif dataset.get("access_type") == "request":
                prioritized["requires_outreach"].append(dataset)
            else:
                prioritized["restricted"].append(dataset)
        
        # Match contacts to datasets
        for contact in search_results.get("contacts", []):
            # Find datasets this contact might own
            relevant_datasets = self._match_contact_to_datasets(
                contact,
                prioritized["requires_outreach"]
            )
            if relevant_datasets:
                contact["relevant_datasets"] = relevant_datasets
                prioritized["contacts_for_outreach"].append(contact)
        
        state.steps_completed.append("evaluation_completed")
        return prioritized
    
    async def _step4_handle_outreach(
        self,
        prioritized_results: Dict[str, Any],
        user_context: Dict[str, Any],
        state: WorkflowState
    ) -> List[Dict[str, Any]]:
        """
        Step 4: Prepare and send outreach emails
        - Generate professional emails
        - Check approval requirements
        - Send via AgentMail
        - Track outreach status
        """
        
        state.current_step = "sending_outreach"
        outreach_results = []
        
        for dataset in prioritized_results.get("requires_outreach", []):
            if not dataset.get("contact_info"):
                continue
            
            # Prepare email
            email_params = {
                "dataset_id": dataset["accession"],
                "dataset_title": dataset["title"],
                "requester_name": user_context["name"],
                "requester_email": user_context["email"],
                "requester_title": user_context.get("title", "Researcher"),
                "contact_name": dataset["contact_info"].get("name", "Data Custodian"),
                "contact_email": dataset["contact_info"]["email"],
                "project_description": state.research_question
            }
            
            # Check if approval needed
            if dataset.get("requires_approval"):
                # Queue for approval
                outreach = await self._queue_for_approval(
                    email_params,
                    dataset["approval_reason"],
                    state
                )
            else:
                # Send immediately
                outreach = await self._send_outreach_email(
                    email_params,
                    state
                )
            
            outreach_results.append(outreach)
            state.outreach_sent.append(outreach)
        
        state.steps_completed.append("outreach_completed")
        return outreach_results
    
    async def _step5_summarize_and_export(
        self,
        state: WorkflowState,
        request: SearchRequest
    ) -> Dict[str, Any]:
        """
        Step 5: Generate summary and export data
        - Consolidate all findings
        - Generate executive summary
        - Prepare export formats
        - Provide next steps
        """
        
        state.current_step = "generating_summary"
        
        # Use summarizer agent
        summary_input = {
            "research_question": request.query,
            "datasets_found": state.datasets_found,
            "contacts_identified": state.contacts_found,
            "outreach_sent": state.outreach_sent,
            "total_duration_minutes": int((datetime.utcnow() - state.start_time).total_seconds() / 60)
        }
        
        summary_result = await summarizer_agent.run(summary_input)
        summary = summary_result.output
        
        # Generate export data
        export_data = await self._prepare_export_data(state)
        
        # Log completion
        await self.provenance.log(
            actor="summarizer_agent",
            action="workflow_completed",
            resource_type="task",
            resource_id=state.task_id,
            details={
                "total_datasets": len(state.datasets_found),
                "outreach_sent": len(state.outreach_sent),
                "execution_time": summary_input["total_duration_minutes"]
            }
        )
        
        state.steps_completed.append("summary_completed")
        
        return {
            "executive_summary": summary.executive_summary,
            "datasets_overview": summary.datasets_overview,
            "outreach_status": summary.outreach_status,
            "next_steps": summary.next_steps,
            "export_data": export_data,
            "confidence_score": summary.confidence_score
        }
    
    # Helper methods
    async def _search_geo(self, query: str, state: WorkflowState) -> Dict[str, Any]:
        """Search GEO using bio_database_agent"""
        from app.core.scrapers.geo_scraper import GEOScraper
        
        scraper = GEOScraper(headless=True)
        datasets = await scraper.search_datasets(query, max_results=20)
        
        # Store in database
        for dataset in datasets:
            await self._store_dataset(dataset, state)
        
        return {"datasets": datasets}
    
    async def _find_colleagues(
        self, 
        company: str, 
        keywords: List[str],
        state: WorkflowState
    ) -> Dict[str, Any]:
        """Find colleagues using colleagues_agent"""
        from app.core.scrapers.linkedin_scraper import LinkedInScraper
        
        scraper = LinkedInScraper(headless=True)
        contacts = await scraper.find_company_employees(
            company=company,
            departments=["Bioinformatics", "Genomics", "Oncology"],
            keywords=keywords + ["cancer", "data"],
            max_results=10
        )
        
        return {"contacts": contacts}
    
    def _validate_cancer_research(self, plan: Dict[str, Any]) -> bool:
        """Validate that query is cancer-research focused"""
        cancer_indicators = [
            "cancer", "carcinoma", "tumor", "oncology",
            "P53", "TP53", "TNBC", "adenocarcinoma"
        ]
        query_lower = plan.get("research_question", "").lower()
        return any(indicator.lower() in query_lower for indicator in cancer_indicators)
    
    def _match_contact_to_datasets(
        self,
        contact: Dict[str, Any],
        datasets: List[Dict[str, Any]]
    ) -> List[str]:
        """Match contacts to relevant datasets based on expertise"""
        matched = []
        contact_keywords = contact.get("keywords_matched", [])
        
        for dataset in datasets:
            dataset_keywords = dataset.get("modalities", []) + dataset.get("cancer_types", [])
            if any(kw in dataset_keywords for kw in contact_keywords):
                matched.append(dataset["accession"])
        
        return matched
```

### 2. Safety & Compliance Checker
```python
# app/core/safety/safety_checker.py
from typing import Dict, Any, List
import re

class SafetyChecker:
    """
    Check for PHI and sensitive data indicators
    Enforce compliance requirements
    """
    
    PHI_INDICATORS = [
        "patient", "clinical", "PHI", "HIPAA",
        "identifiable", "medical record", "diagnosis",
        "treatment", "hospital", "clinic"
    ]
    
    RESTRICTED_CONTACTS = [
        "CEO", "CTO", "CFO", "Director", "VP",
        "Head of", "Chief", "President"
    ]
    
    def contains_phi_indicators(self, dataset: Dict[str, Any]) -> bool:
        """Check if dataset might contain PHI"""
        text_to_check = " ".join([
            dataset.get("title", ""),
            dataset.get("description", ""),
            " ".join(dataset.get("keywords", []))
        ]).lower()
        
        return any(indicator.lower() in text_to_check 
                  for indicator in self.PHI_INDICATORS)
    
    def requires_executive_approval(self, contact: Dict[str, Any]) -> bool:
        """Check if contact is senior level requiring special approval"""
        job_title = contact.get("job_title", "").lower()
        return any(title.lower() in job_title 
                  for title in self.RESTRICTED_CONTACTS)
    
    def validate_email_content(self, email_body: str) -> Dict[str, Any]:
        """Validate email doesn't contain sensitive information"""
        issues = []
        
        # Check for PHI
        if any(phi in email_body.lower() for phi in self.PHI_INDICATORS):
            issues.append("Email may reference PHI data")
        
        # Check for aggressive language
        aggressive_terms = ["urgent", "immediately", "asap", "deadline"]
        if sum(1 for term in aggressive_terms if term in email_body.lower()) > 2:
            issues.append("Email tone may be too aggressive")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues
        }
```

### 3. Provenance Logger
```python
# app/core/utils/provenance.py
from datetime import datetime
from typing import Dict, Any, Optional, List
from app.models.database import Provenance
from app.core.database import get_db_session
import json

class ProvenanceLogger:
    """
    Comprehensive provenance logging for audit trail
    Tracks every action in the system
    """
    
    def __init__(self):
        self.session_id = datetime.utcnow().isoformat()
    
    async def log(
        self,
        actor: str,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an action with full context"""
        
        async with get_db_session() as session:
            provenance = Provenance(
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=json.dumps(details) if details else "{}",
                session_id=self.session_id,
                created_at=datetime.utcnow()
            )
            session.add(provenance)
            await session.commit()
    
    async def get_trail(
        self, 
        resource_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get provenance trail for a resource"""
        
        async with get_db_session() as session:
            records = await session.query(Provenance).filter(
                Provenance.resource_id == resource_id
            ).order_by(
                Provenance.created_at.desc()
            ).limit(limit).all()
            
            return [
                {
                    "actor": r.actor,
                    "action": r.action,
                    "timestamp": r.created_at.isoformat(),
                    "details": json.loads(r.details) if r.details else {}
                }
                for r in records
            ]
```

## Testing Strategy

### 1. Unit Tests
```python
# tests/unit/test_agents.py
import pytest
from unittest.mock import Mock, patch
from app.core.agents.planner_agent import planner_agent
from app.models.schemas import SearchRequest

class TestPlannerAgent:
    @pytest.mark.asyncio
    async def test_cancer_research_planning(self):
        """Test planner correctly identifies cancer research"""
        request = SearchRequest(
            query="P53 mutations in lung adenocarcinoma RNA-seq",
            modalities=["transcriptomics"],
            cancer_types=["lung adenocarcinoma"]
        )
        
        result = await planner_agent.run(request)
        
        assert result.output.research_question == request.query
        assert "search_public" in [s.action for s in result.output.steps]
        assert any("P53" in str(s) for s in result.output.steps)
    
    @pytest.mark.asyncio
    async def test_multi_modal_detection(self):
        """Test detection of multi-modal data requirements"""
        request = SearchRequest(
            query="Integrate genomics and proteomics for TNBC biomarkers"
        )
        
        result = await planner_agent.run(request)
        
        assert len(result.output.steps) > 1
        assert "genomics" in result.output.confirmed_requirements.get("modalities", [])
        assert "proteomics" in result.output.confirmed_requirements.get("modalities", [])

# tests/unit/test_scrapers.py
class TestGEOScraper:
    @pytest.mark.asyncio
    @patch('browser_use.Agent')
    async def test_geo_search(self, mock_agent):
        """Test GEO scraper extracts correct fields"""
        from app.core.scrapers.geo_scraper import GEOScraper
        
        # Mock browser agent response
        mock_agent.return_value.run.return_value = Mock(
            output='[{"accession": "GSE123", "title": "Test"}]'
        )
        
        scraper = GEOScraper(headless=True)
        results = await scraper.search_datasets("test query")
        
        assert len(results) > 0
        assert results[0]["accession"] == "GSE123"
```

### 2. Integration Tests
```python
# tests/integration/test_workflow.py
import pytest
from app.core.workflow.master_orchestrator import MasterOrchestrator
from app.models.schemas import SearchRequest

class TestWorkflowIntegration:
    @pytest.mark.asyncio
    async def test_complete_workflow(self, test_db, test_user):
        """Test complete workflow from query to summary"""
        orchestrator = MasterOrchestrator()
        
        request = SearchRequest(
            query="Find P53 mutation datasets in lung cancer",
            sources=["GEO"],
            include_internal=False,
            max_results=5
        )
        
        result = await orchestrator.execute_complete_workflow(
            request,
            test_user
        )
        
        assert result["success"]
        assert "summary" in result
        assert len(result["summary"]["datasets_overview"]) > 0
    
    @pytest.mark.asyncio
    async def test_phi_detection_blocks_email(self, test_db):
        """Test that PHI detection prevents automatic email"""
        orchestrator = MasterOrchestrator()
        
        # Create dataset with PHI indicators
        dataset = {
            "title": "Patient clinical data with treatment outcomes",
            "access_type": "request",
            "contact_info": {"email": "test@example.com"}
        }
        
        result = await orchestrator._step4_handle_outreach(
            {"requires_outreach": [dataset]},
            {"email": "researcher@company.com"},
            Mock()
        )
        
        assert result[0]["status"] == "pending_approval"
        assert result[0]["requires_approval"]
```

### 3. End-to-End Tests
```python
# tests/e2e/test_user_journey.py
import pytest
from httpx import AsyncClient
from app.main import app

class TestUserJourney:
    @pytest.mark.asyncio
    async def test_researcher_workflow(self):
        """Test complete researcher journey"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Step 1: Login
            login_response = await client.post("/api/v1/auth/login", json={
                "email": "researcher@biotech.com",
                "password": "test123"
            })
            assert login_response.status_code == 200
            token = login_response.json()["access_token"]
            
            # Step 2: Submit search
            headers = {"Authorization": f"Bearer {token}"}
            search_response = await client.post(
                "/api/v1/search",
                json={
                    "query": "P53 lung adenocarcinoma datasets",
                    "sources": ["GEO"],
                    "include_internal": True
                },
                headers=headers
            )
            assert search_response.status_code == 200
            task_id = search_response.json()["task_id"]
            
            # Step 3: Poll for results
            import asyncio
            for _ in range(30):  # Poll for 30 seconds max
                status_response = await client.get(
                    f"/api/v1/search/{task_id}",
                    headers=headers
                )
                if status_response.json()["status"] == "completed":
                    break
                await asyncio.sleep(1)
            
            # Step 4: Get results
            results_response = await client.get(
                f"/api/v1/search/{task_id}/results",
                headers=headers
            )
            assert results_response.status_code == 200
            results = results_response.json()
            
            assert results["datasets"]
            assert results["summary"]["total_datasets"] > 0
```

## Demo Scenarios

### Scenario 1: Quick Win Demo (5 minutes)
```python
# demo/quick_demo.py
"""
Quick demo for hackathon judges
Shows core value proposition in 5 minutes
"""

DEMO_QUERY = "Find all P53 mutation datasets in lung adenocarcinoma with RNA-seq data"

async def run_quick_demo():
    print("🔬 Biodata Assistant - Cancer Research Data Discovery")
    print("=" * 50)
    
    # 1. Show the pain point
    print("\n❌ Traditional approach:")
    print("- Manual search across 5+ databases")
    print("- Finding contact emails manually")
    print("- Writing individual outreach emails")
    print("- Time: 2-3 days")
    
    # 2. Show our solution
    print("\n✅ Our solution:")
    print(f"Query: {DEMO_QUERY}")
    
    # 3. Execute search
    orchestrator = MasterOrchestrator()
    result = await orchestrator.execute_complete_workflow(
        SearchRequest(query=DEMO_QUERY),
        {"email": "demo@biotech.com", "name": "Demo User"}
    )
    
    # 4. Show results
    print(f"\n📊 Results in {result['execution_time_seconds']:.1f} seconds:")
    print(f"- Datasets found: {len(result['summary']['datasets_overview'])}")
    print(f"- Emails sent: {len(result['summary']['outreach_status'])}")
    print(f"- Time saved: 48+ hours")
```

### Scenario 2: PHI Safety Demo
```python
# demo/safety_demo.py
"""
Demonstrate PHI safety features
Shows compliance and human-in-the-loop
"""

SENSITIVE_QUERY = "Clinical trial patient data with treatment outcomes"

async def run_safety_demo():
    print("🔒 PHI Safety Demonstration")
    
    # Show detection
    result = await orchestrator.execute_complete_workflow(
        SearchRequest(query=SENSITIVE_QUERY),
        user_context
    )
    
    print("\n⚠️ PHI Detected - Approval Required")
    print("- Dataset flagged for sensitive content")
    print("- Email queued for human review")
    print("- Compliance maintained")
```

## Performance Optimization

### 1. Parallel Processing
```python
# app/core/optimization/parallel_executor.py
import asyncio
from typing import List, Callable, Any

class ParallelExecutor:
    """Execute multiple async tasks with rate limiting"""
    
    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def execute_batch(
        self,
        tasks: List[Callable],
        *args,
        **kwargs
    ) -> List[Any]:
        """Execute tasks in parallel with concurrency limit"""
        
        async def run_with_semaphore(task):
            async with self.semaphore:
                return await task(*args, **kwargs)
        
        return await asyncio.gather(
            *[run_with_semaphore(task) for task in tasks],
            return_exceptions=True
        )
```

### 2. Caching Strategy
```python
# app/core/cache/result_cache.py
from typing import Dict, Any, Optional
import hashlib
import json
from datetime import datetime, timedelta

class ResultCache:
    """Cache search results to avoid redundant searches"""
    
    def __init__(self, ttl_minutes: int = 30):
        self.cache = {}
        self.ttl = timedelta(minutes=ttl_minutes)
    
    def _get_key(self, query: str, sources: List[str]) -> str:
        """Generate cache key from query parameters"""
        data = json.dumps({"query": query, "sources": sorted(sources)})
        return hashlib.md5(data.encode()).hexdigest()
    
    async def get(self, query: str, sources: List[str]) -> Optional[Dict[str, Any]]:
        """Get cached result if available and not expired"""
        key = self._get_key(query, sources)
        
        if key in self.cache:
            entry = self.cache[key]
            if datetime.utcnow() - entry["timestamp"] < self.ttl:
                return entry["data"]
        
        return None
    
    async def set(self, query: str, sources: List[str], data: Dict[str, Any]):
        """Cache search result"""
        key = self._get_key(query, sources)
        self.cache[key] = {
            "data": data,
            "timestamp": datetime.utcnow()
        }
```

## Deployment Preparation

### Docker Compose Configuration
```yaml
# docker-compose.yml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/biodata
      - REDIS_URL=redis://redis:6379
      - AGENTMAIL_API_KEY=${AGENTMAIL_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - db
      - redis
    volumes:
      - ./backend:/app
      - browser_profiles:/app/browser_profiles
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=biodata
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_API_URL=http://localhost:8000
    depends_on:
      - backend

volumes:
  postgres_data:
  browser_profiles:
```

### Environment Variables
```bash
# .env.example
# API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
AGENTMAIL_API_KEY=sk_...
AGENTMAIL_DOMAIN=yourdomain

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/biodata

# Redis
