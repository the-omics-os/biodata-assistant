from __future__ import annotations

from typing import List, Dict, Any
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.bedrock import BedrockConverseModel
from datetime import datetime
from app.core.utils.provenance import log_provenance


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

model = BedrockConverseModel( "us.anthropic.claude-sonnet-4-20250514-v1:0")
summarizer_agent = Agent[SummaryInput, ResearchSummary](
    model,
    deps_type=SummaryInput,
    output_type=ResearchSummary,
    instructions=(
        "You are a research intelligence analyst. Synthesize search results into actionable insights for cancer researchers.\n"
        "Highlight:\n"
        "- Most relevant datasets for the research question\n"
        "- Success rate of outreach attempts\n"
        "- Data availability timeline\n"
        "- Recommended prioritization\n"
        "- Potential roadblocks or alternatives\n"
        "Maintain a focus on oncology topics (P53/TP53, lung adenocarcinoma, TNBC, breast cancer) and modalities.\n"
    ),
)


@summarizer_agent.tool
async def analyze_dataset_quality(ctx: RunContext[SummaryInput]) -> Dict[str, Any]:
    """Analyze overall quality and fit of discovered datasets."""
    datasets = ctx.deps.datasets_found or []

    quality_metrics = {
        "total_found": len(datasets),
        "publicly_available": sum(1 for d in datasets if (d.get("access_type") or "").lower() == "public"),
        "requires_outreach": sum(1 for d in datasets if (d.get("access_type") or "").lower() == "request"),
        "average_sample_size": (
            sum(int(d.get("sample_size") or 0) for d in datasets) / len(datasets) if datasets else 0
        ),
        "modality_coverage": sorted(
            {m.lower() for d in datasets for m in (d.get("modalities") or [])}
        ),
    }

    await log_provenance(
        actor="summarizer_agent",
        action="analyze_dataset_quality",
        details=quality_metrics,
    )
    return quality_metrics


@summarizer_agent.tool
async def generate_export_data(ctx: RunContext[SummaryInput]) -> Dict[str, Any]:
    """Prepare data for CSV/Excel export."""
    export_data = {
        "metadata": {
            "research_question": ctx.deps.research_question,
            "search_date": datetime.utcnow().isoformat(),
            "total_results": len(ctx.deps.datasets_found or []),
        },
        "datasets": [
            {
                "accession": d.get("accession"),
                "title": d.get("title"),
                "source": d.get("source") or d.get("database"),
                "modalities": ", ".join(d.get("modalities") or []),
                "sample_size": d.get("sample_size"),
                "access_type": d.get("access_type"),
                "contact": (d.get("contact_info") or {}).get("email"),
                "outreach_status": next(
                    (o.get("status") for o in (ctx.deps.outreach_sent or []) if o.get("dataset_id") in (d.get("id"), d.get("accession"))),
                    "not_initiated",
                ),
            }
            for d in (ctx.deps.datasets_found or [])
        ],
    }

    await log_provenance(
        actor="summarizer_agent",
        action="generate_export_data",
        details={"count": len(export_data["datasets"])},
    )
    return export_data
