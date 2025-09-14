from __future__ import annotations

from typing import Dict, List, Any, Optional
import re
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from app.models.schemas import SearchRequest
from app.core.utils.provenance import log_provenance
from dotenv import load_dotenv
from pydantic_ai.models.bedrock import BedrockConverseModel
load_dotenv()


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

model = BedrockConverseModel( "us.anthropic.claude-sonnet-4-20250514-v1:0")

planner_agent = Agent[SearchRequest, WorkflowPlan](
    'openai:gpt-4.1',
    deps_type=SearchRequest,
    output_type=WorkflowPlan,
    instructions=(
        "You are a biomedical research planning assistant for cancer researchers.\n"
        "Return only valid JSON matching the WorkflowPlan schema. No prose or markdown.\n"
        "Derive steps strictly from user inputs (query, modalities, cancer_types, include_internal, max_results).\n"
        "Do not inject assumptions or hardcoded keywords; do not infer disease terms.\n"
        "The workflow should generally include:\n"
        "1. Search public databases\n"
        "2. Optionally find internal colleagues (only if include_internal=true)\n"
        "3. Evaluate results\n"
        "4. Send outreach emails for non-public datasets\n"
        "5. Generate summary\n"
    ),
)


@planner_agent.tool_plain
async def create_workflow_plan(search_request: SearchRequest) -> WorkflowPlan:
    """Create the main workflow plan strictly from user inputs without hardcoded keywords."""
    include_internal = bool(search_request.include_internal)
    steps: List[WorkflowStep] = []

    # Step 1: Search public databases
    steps.append(
        WorkflowStep(
            step_number=1,
            action="search_public",
            description="Search public databases for datasets matching the query",
            parameters={
                "databases": ["GEO"],
                "query": search_request.query,
                "modalities": search_request.modalities or [],
                "cancer_types": search_request.cancer_types or [],
                "max_results": search_request.max_results or 20,
            },
        )
    )

    # Step 2: Internal colleagues (optional)
    if include_internal:
        steps.append(
            WorkflowStep(
                step_number=2,
                action="find_colleagues",
                description="Search for internal colleagues with relevant expertise",
                parameters={
                    "departments": [],
                    "keywords": [],
                },
                dependencies=[1],
            )
        )

    # Step 3: Evaluate results
    next_step = 2 if not include_internal else 3
    steps.append(
        WorkflowStep(
            step_number=next_step,
            action="evaluate_results",
            description="Analyze and prioritize discovered datasets",
            parameters={"criteria": ["relevance", "sample_size", "access_type"]},
            dependencies=[1] if not include_internal else [1, 2],
        )
    )

    # Step 4: Send outreach
    next_step += 1
    steps.append(
        WorkflowStep(
            step_number=next_step,
            action="send_outreach",
            description="Compose and send data access requests (for non-public datasets with contacts)",
            parameters={"template": "data_request"},
            dependencies=[next_step - 1],
        )
    )

    # Step 5: Generate summary
    next_step += 1
    steps.append(
        WorkflowStep(
            step_number=next_step,
            action="summarize",
            description="Create executive summary and export data",
            parameters={"format": "executive_summary"},
            dependencies=[next_step - 1],
        )
    )

    return WorkflowPlan(
        research_question=search_request.query,
        confirmed_requirements={
            "modalities": search_request.modalities or [],
            "cancer_types": search_request.cancer_types or [],
            "include_internal": include_internal,
            "max_results": search_request.max_results or 20,
        },
        steps=steps,
        estimated_duration_minutes=5 + (2 if include_internal else 0),
        requires_approval=False,
    )


@planner_agent.tool
async def analyze_research_context(ctx: RunContext[SearchRequest], query: str) -> Dict[str, Any]:
    """Parse query into neutral keywords without hardcoded domain assumptions."""
    text = (query or "").lower()
    tokens = re.findall(r"[a-z0-9\-]+", text)
    unique_tokens: List[str] = []
    for t in tokens:
        if len(t) > 2 and t not in unique_tokens:
            unique_tokens.append(t)

    result = {
        "cancer_focus": [],  # avoid hardcoded assumptions
        "suggested_modalities": [],  # defer to user inputs/downstream agents
        "requires_multi_modal": False,
        "keywords": unique_tokens[:15],
    }

    await log_provenance(
        actor="planner_agent",
        action="analyze_research_context",
        details={"query": query, "result": result},
    )
    return result


@planner_agent.tool
async def check_internal_resources(ctx: RunContext[SearchRequest]) -> bool:
    """Check if internal colleague search should be included."""
    decision = bool(ctx.deps.include_internal)
    await log_provenance(
        actor="planner_agent",
        action="check_internal_resources",
        details={"include_internal": decision},
    )
    return decision
