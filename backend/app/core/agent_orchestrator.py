from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Tuple

from app.core.agents import (
    planner_agent,
    bio_database_agent,
    colleagues_agent,
    email_agent,
    summarizer_agent,
    DatabaseSearchParams,
    ColleagueSearchParams,
    EmailOutreachParams,
    DatasetCandidate,
    InternalContact,
    SummaryInput,
)
from app.models.schemas import SearchRequest
from app.core.utils.provenance import log_provenance

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Coordinates the multi-agent workflow:
    1) Plan
    2) Search public databases (parallel)
    3) Search internal colleagues (optional)
    4) Send outreach (if access_type requires request and contact exists)
    5) Summarize
    """

    def __init__(self) -> None:
        self.agents = {
            "planner": planner_agent,
            "bio_database": bio_database_agent,
            "colleagues": colleagues_agent,
            "email": email_agent,
            "summarizer": summarizer_agent,
        }

    async def execute_workflow(self, search_request: SearchRequest, user_email: str) -> Dict[str, Any]:
        """
        Execute complete workflow from research question to results.
        """
        await log_provenance(
            actor=user_email or "system",
            action="workflow_started",
            resource_type="task",
            details={"query": search_request.query},
        )

        # Step 1: Planning
        plan_run = await planner_agent.run(search_request)
        plan = plan_run.output

        # Step 2: Parallel execution of searches
        search_tasks: List[asyncio.Future] = []

        # Public database searches
        sources = search_request.sources or []
        if not sources:
            sources = []  # default empty; bio-database tools will default to GEO when invoked
            # We can choose to always include GEO for MVP
            sources = ["GEO"]

        for source in sources:
            search_params = DatabaseSearchParams(
                query=search_request.query,
                database=str(source),
                max_results=search_request.max_results,
                filters={
                    "modalities": search_request.modalities or [],
                    "cancer_types": search_request.cancer_types or [],
                },
            )
            search_tasks.append(asyncio.create_task(bio_database_agent.run(search_params)))

        # Internal colleague search (if enabled)
        if search_request.include_internal:
            colleague_params = ColleagueSearchParams(
                company="YourCompany",
                keywords=plan.confirmed_requirements.get("keywords", []),
            )
            search_tasks.append(asyncio.create_task(colleagues_agent.run(colleague_params)))

        # Execute searches in parallel
        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Step 3: Process search results
        datasets: List[DatasetCandidate] = []
        contacts: List[InternalContact] = []

        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Search sub-task error: {r}")
                continue
            try:
                # Pydantic AI returns AgentRunResult with .output
                out = r.output  # type: ignore[attr-defined]
            except Exception:
                out = None

            if not out:
                continue

            # Heuristics to separate dataset vs contacts output
            if isinstance(out, list) and out:
                first = out[0]
                if isinstance(first, DatasetCandidate) or ("accession" in dict(first)):
                    datasets.extend(out)  # type: ignore[arg-type]
                elif isinstance(first, InternalContact) or ("linkedin_url" in dict(first)):
                    contacts.extend(out)  # type: ignore[arg-type]

        # Step 4: Outreach for request-only datasets (if contact info exists)
        outreach_results: List[Dict[str, Any]] = []
        for d in datasets:
            access_type = (d.access_type or "").lower()
            if access_type == "request" and d.contact_info and d.contact_info.get("email"):
                email_params = EmailOutreachParams(
                    dataset_id=d.accession,
                    dataset_title=d.title,
                    requester_name=(user_email.split("@")[0] if user_email else "researcher"),
                    requester_email=user_email or "researcher@example.com",
                    requester_title="Researcher",
                    contact_name=d.contact_info.get("name", "Data Custodian"),
                    contact_email=d.contact_info["email"],  # type: ignore[index]
                    project_description=search_request.query,
                )
                try:
                    email_run = await email_agent.run(email_params)
                    outreach_results.append(email_run.output.model_dump())
                except Exception as e:
                    logger.error(f"Email agent failed for {d.accession}: {e}")
                    outreach_results.append(
                        {
                            "success": False,
                            "status": "failed",
                            "error_message": str(e),
                            "dataset_id": d.accession,
                        }
                    )

        # Step 5: Summarize
        summary_input = SummaryInput(
            research_question=search_request.query,
            datasets_found=[dc.model_dump() if hasattr(dc, "model_dump") else dict(dc) for dc in datasets],  # type: ignore[arg-type]
            contacts_identified=[cc.model_dump() if hasattr(cc, "model_dump") else dict(cc) for cc in contacts],  # type: ignore[arg-type]
            outreach_sent=outreach_results,
            total_duration_minutes=5,
        )
        summary_run = await summarizer_agent.run(summary_input)
        summary = summary_run.output

        await log_provenance(
            actor=user_email or "system",
            action="workflow_completed",
            resource_type="task",
            details={
                "datasets_count": len(datasets),
                "contacts_count": len(contacts),
                "outreach_count": len(outreach_results),
            },
        )

        return {
            "plan": plan.model_dump() if hasattr(plan, "model_dump") else dict(plan),  # type: ignore[arg-type]
            "datasets": [dc.model_dump() if hasattr(dc, "model_dump") else dict(dc) for dc in datasets],  # type: ignore[arg-type]
            "contacts": [cc.model_dump() if hasattr(cc, "model_dump") else dict(cc) for cc in contacts],  # type: ignore[arg-type]
            "outreach": outreach_results,
            "summary": summary.model_dump() if hasattr(summary, "model_dump") else dict(summary),  # type: ignore[arg-type]
        }
