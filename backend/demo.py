#!/usr/bin/env python3
"""
🎛️ Biodata Assistant TUI
Interactive terminal UI to run the real end-to-end backend workflow:
- Live GEO scraping via Browser-Use (visible browser)
- Optional LinkedIn colleague discovery (visible browser)
- Human-gated email outreach via AgentMail

Requirements:
- OPENAI_API_KEY set (for Browser-Use LLM)
- AGENTMAIL_API_KEY set (if sending emails)
- .env loaded by backend/app/config.py (pydantic-settings)

Usage (interactive defaults):
  python backend/demo.py

Optional flags:
  python backend/demo.py --query "TP53 lung adenocarcinoma RNA-seq" --max-results 3 --include-internal --show-browser --send-emails

Notes:
- Shows real browsers (headless=False) when --show-browser is set (default True in TUI).
- All emailing requires explicit confirmation in the TUI even if --send-emails is passed.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

# Backend imports
from app.config import settings
from app.models.schemas import SearchRequest
from app.core.agents import (
    planner_agent,
    bio_database_agent,
    colleagues_agent,
    email_agent,
    summarizer_agent,
    DatabaseSearchParams,
    ColleagueSearchParams,
    EmailOutreachParams,
)
from app.core.utils.provenance import log_provenance

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Biodata Assistant TUI")
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Research query to run (if omitted, TUI will prompt)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="Max results to fetch per source (default 5; prompt in TUI)",
    )
    parser.add_argument(
        "--include-internal",
        action="store_true",
        help="Also search LinkedIn for internal colleagues",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Show real browsers (headless=False). If omitted, TUI will ask.",
    )
    parser.add_argument(
        "--send-emails",
        action="store_true",
        help="Allow sending emails after confirmation (still requires in-TUI confirmation)",
    )
    return parser.parse_args()


def validate_env(send_emails: bool) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    # Browser-Use LLM key
    if not (settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")):
        issues.append(
            "OPENAI_API_KEY missing. Required for Browser-Use LLM (GEO/LinkedIn scraping)."
        )
    if send_emails and not (settings.AGENTMAIL_API_KEY or os.getenv("AGENTMAIL_API_KEY")):
        issues.append(
            "AGENTMAIL_API_KEY missing. Required to send emails via AgentMail."
        )
    return (len(issues) == 0, issues)


def banner() -> None:
    rprint(
        Panel.fit(
            "[bold cyan]🔬 BIODATA ASSISTANT — Interactive TUI[/bold cyan]\n"
            "[yellow]AI-Powered Cancer Research Data Discovery[/yellow]\n\n"
            "• GEO scraping (visible browser)\n"
            "• Optional LinkedIn colleague discovery\n"
            "• Human-gated email outreach via AgentMail\n",
            border_style="cyan",
        )
    )


async def run_planner(query: str) -> Dict[str, Any]:
    req = SearchRequest(query=query)
    plan_run = await planner_agent.run(req)
    out = plan_run.output
    if hasattr(out, "model_dump"):
        return out.model_dump()
    return dict(out)


def render_plan(plan: Dict[str, Any]) -> None:
    console.print("\n[bold cyan]🧭 Plan[/bold cyan]")
    steps = plan.get("steps") or []
    t = Table(show_header=True, header_style="bold")
    t.add_column("#", style="cyan", width=4)
    t.add_column("Action", style="green")
    t.add_column("Description", style="white")
    for s in steps:
        t.add_row(str(s.get("step_number", "?")), str(s.get("action", "")), str(s.get("description", "")))
    console.print(t)


async def run_geo(query: str, max_results: int) -> List[Dict[str, Any]]:
    params = DatabaseSearchParams(
        query=query,
        database="GEO",
        max_results=max_results,
        filters={},
    )
    run = await bio_database_agent.run(params)
    out = run.output or []
    # Normalize to list of dict (DatasetCandidate is pydantic model)
    results: List[Dict[str, Any]] = []
    for item in out:
        if hasattr(item, "model_dump"):
            results.append(item.model_dump())
        elif isinstance(item, dict):
            results.append(item)
    return results


async def run_linkedin(company: str, keywords: List[str]) -> List[Dict[str, Any]]:
    params = ColleagueSearchParams(company=company, keywords=keywords)
    run = await colleagues_agent.run(params)
    out = run.output or []
    contacts: List[Dict[str, Any]] = []
    for item in out:
        if hasattr(item, "model_dump"):
            contacts.append(item.model_dump())
        elif isinstance(item, dict):
            contacts.append(item)
    return contacts


def render_datasets(datasets: List[Dict[str, Any]]) -> None:
    console.print("\n[bold green]📊 Datasets[/bold green]")
    t = Table(show_header=True, header_style="bold", show_lines=True)
    t.add_column("#", style="cyan", width=4)
    t.add_column("Accession", style="yellow")
    t.add_column("Title", style="white", overflow="fold")
    t.add_column("Modalities", style="magenta")
    t.add_column("Samples", style="green")
    t.add_column("Access", style="red")
    t.add_column("Contact", style="cyan")

    for idx, d in enumerate(datasets, start=1):
        mods = ", ".join([str(m) for m in (d.get("modalities") or [])])
        contact = d.get("contact_email") or "-"
        t.add_row(
            str(idx),
            str(d.get("accession") or ""),
            str(d.get("title") or ""),
            mods,
            str(d.get("sample_size") or "-"),
            str(d.get("access_type") or "public"),
            contact,
        )
    console.print(t)


def render_contacts(contacts: List[Dict[str, Any]]) -> None:
    if not contacts:
        return
    console.print("\n[bold cyan]🧑‍🔬 Potential Colleagues[/bold cyan]")
    t = Table(show_header=True, header_style="bold", show_lines=True)
    t.add_column("#", style="cyan", width=4)
    t.add_column("Name", style="yellow")
    t.add_column("Title", style="white")
    t.add_column("Department", style="magenta")
    t.add_column("Company", style="green")
    t.add_column("Email", style="cyan")
    t.add_column("LinkedIn", style="blue", overflow="fold")

    for idx, c in enumerate(contacts, start=1):
        t.add_row(
            str(idx),
            str(c.get("name") or ""),
            str(c.get("job_title") or ""),
            str(c.get("department") or ""),
            str(c.get("company") or ""),
            str(c.get("email") or (", ".join(c.get("email_suggestions", []) or []) or "-")),
            str(c.get("linkedin_url") or ""),
        )
    console.print(t)


def select_datasets_for_outreach(datasets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Preselect request/restricted datasets with a contact email
    eligible_idx = [
        i for i, d in enumerate(datasets, start=1)
        if str(d.get("access_type", "")).lower() in {"request", "restricted"} and d.get("contact_email")
    ]

    if not eligible_idx:
        console.print("[yellow]No datasets requiring outreach with available contact emails were found.[/yellow]")
        return []

    console.print(
        "\n[bold]Select datasets to send outreach:[/bold]\n"
        f"Eligible indexes (request/restricted with contact): {eligible_idx}\n"
        "Enter space-separated indexes (e.g. '1 3 5'), or 'all' to select all eligible, or leave blank to skip."
    )
    choice = Prompt.ask("Your selection", default="all").strip()
    if not choice:
        return []
    selected: List[int] = []
    if choice.lower() == "all":
        selected = eligible_idx
    else:
        for tok in choice.split():
            try:
                n = int(tok)
                if 1 <= n <= len(datasets):
                    selected.append(n)
            except Exception:
                continue
        # Keep only eligible
        selected = [n for n in selected if n in eligible_idx]

    return [datasets[i - 1] for i in selected]


async def send_outreach_for_datasets(
    datasets: List[Dict[str, Any]],
    requester_name: str,
    requester_email: str,
    requester_title: str,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for d in datasets:
        params = EmailOutreachParams(
            dataset_id=str(d.get("accession") or ""),
            dataset_title=str(d.get("title") or ""),
            requester_name=requester_name,
            requester_email=requester_email,
            requester_title=requester_title,
            contact_name=str(d.get("contact_name") or "Data Custodian"),
            contact_email=str(d.get("contact_email")),
            project_description=str(d.get("title") or ""),
        )
        try:
            run = await email_agent.run(params)
            out = run.output
            if hasattr(out, "model_dump"):
                results.append(out.model_dump())
            elif isinstance(out, dict):
                results.append(out)
            else:
                results.append({"success": True, "status": "sent"})
        except Exception as e:
            results.append({"success": False, "status": "failed", "error": str(e)})
    return results


async def summarize(query: str, datasets: List[Dict[str, Any]], contacts: List[Dict[str, Any]], outreach: List[Dict[str, Any]]) -> Dict[str, Any]:
    from app.core.agents import SummaryInput  # defer import to avoid circulars in some setups
    inp = SummaryInput(
        research_question=query,
        datasets_found=datasets,
        contacts_identified=contacts,
        outreach_sent=outreach,
        total_duration_minutes=5,
    )
    run = await summarizer_agent.run(inp)
    out = run.output
    if hasattr(out, "model_dump"):
        return out.model_dump()
    return dict(out)


async def main() -> None:
    args = parse_args()
    banner()

    # Interactive inputs
    default_suggestions = [
        "Find all P53 mutation datasets in lung adenocarcinoma with RNA-seq data",
        "Triple negative breast cancer proteomics and transcriptomics datasets",
        "P53 pathway proteomics in breast cancer cohorts",
    ]

    if args.query:
        query = args.query
    else:
        console.print("[bold]Enter your research question[/bold]")
        console.print("Suggestions:")
        for i, s in enumerate(default_suggestions, start=1):
            console.print(f"  {i}. {s}")
        free = Prompt.ask("\nType your query (or choose 1/2/3)", default="1").strip()
        if free in {"1", "2", "3"}:
            query = default_suggestions[int(free) - 1]
        else:
            query = free

    if args.max_results is not None:
        max_results = max(1, int(args.max_results))
    else:
        max_results = max(1, IntPrompt.ask("Max results to fetch from GEO", default=5))

    # Show browsers (headless=False) toggle
    if args.show_browser:
        show_browser = True
    else:
        show_browser = Confirm.ask("Show live browsers for scraping? (recommended for dev)", default=True)

    # Control LinkedIn colleague search
    if args.include_internal:
        include_internal = True
    else:
        include_internal = Confirm.ask("Also search for internal colleagues via LinkedIn?", default=False)

    # Set DEBUG to make scrapers use headless=False when show_browser=True
    try:
        settings.DEBUG = bool(show_browser)
    except Exception:
        pass

    # Validate environment
    allow_send_flag = bool(args.send_emails)
    ok_env, issues = validate_env(send_emails=allow_send_flag)
    if not ok_env:
        console.print(Panel.fit("\n".join(issues), title="Environment Validation", border_style="red"))
        if not Confirm.ask("Continue anyway (scraping may fail or emailing disabled)?", default=False):
            sys.exit(1)

    # Requester identity
    console.print("\n[bold]Requester identity (used in outreach emails):[/bold]")
    requester_name = Prompt.ask("Your name", default=os.getenv("REQUESTER_NAME", "Researcher"))
    requester_email = Prompt.ask("Your email", default=os.getenv("REQUESTER_EMAIL", "researcher@example.com"))
    requester_title = Prompt.ask("Your title", default=os.getenv("REQUESTER_TITLE", "Researcher"))

    # Company for LinkedIn search (when enabled)
    company = ""
    if include_internal:
        company = Prompt.ask("Company to search on LinkedIn (public search)", default=os.getenv("COMPANY_NAME", "YourCompany"))

    await log_provenance(
        actor=requester_email or "user",
        action="tui_started",
        details={"query": query, "max_results": max_results, "include_internal": include_internal, "show_browser": show_browser},
    )

    # Execution
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        tk = progress.add_task("[cyan]Planning...", total=None)
        try:
            plan = await run_planner(query)
            progress.update(tk, description="[green]✓ Plan created", completed=True)
        except Exception as e:
            progress.update(tk, description=f"[red]Plan failed: {e}", completed=True)
            plan = {}

        tk = progress.add_task("[cyan]Searching GEO (live browser)...", total=None)
        try:
            datasets = await run_geo(query, max_results)
            progress.update(tk, description=f"[green]✓ GEO results: {len(datasets)}", completed=True)
        except Exception as e:
            progress.update(tk, description=f"[red]GEO search failed: {e}", completed=True)
            datasets = []

        contacts: List[Dict[str, Any]] = []
        if include_internal:
            tk = progress.add_task("[cyan]Searching LinkedIn (live browser)...", total=None)
            try:
                contacts = await run_linkedin(company, keywords=["cancer", "genomics", "data"])
                progress.update(tk, description=f"[green]✓ Contacts found: {len(contacts)}", completed=True)
            except Exception as e:
                progress.update(tk, description=f"[red]LinkedIn search failed: {e}", completed=True)

    if plan:
        render_plan(plan)
    render_datasets(datasets)
    render_contacts(contacts)

    # Outreach selection
    chosen = select_datasets_for_outreach(datasets)
    outreach_results: List[Dict[str, Any]] = []

    if chosen:
        console.print("\n[bold cyan]📧 Outreach Preparation[/bold cyan]")
        console.print("Emails will be composed and sent via AgentMail with provenance logging.")
        # PHI / sensitive approval gate (simple heuristic)
        contains_phi = any(
            any(k in (d.get("title", "").lower()) for k in ["clinical", "patient", "phi"])
            for d in chosen
        )
        if contains_phi:
            console.print("[yellow]PHI indicators detected in selected datasets.[/yellow]")
            if not Confirm.ask("Require manual approval to proceed?", default=True):
                console.print("[red]Outreach aborted due to PHI policy.[/red]")
                chosen = []

    if chosen:
        # Allow sending?
        if not allow_send_flag and not Confirm.ask("Send emails now via AgentMail?", default=False):
            console.print("[yellow]Skipping email sending.[/yellow]")
        else:
            ok_env, issues = validate_env(send_emails=True)
            if not ok_env:
                console.print(Panel.fit("\n".join(issues), title="Email Disabled", border_style="red"))
            else:
                if not Confirm.ask(f"Confirm sending {len(chosen)} emails now?", default=False):
                    console.print("[yellow]Email sending cancelled by user.[/yellow]")
                else:
                    outreach_results = await send_outreach_for_datasets(
                        chosen, requester_name=requester_name, requester_email=requester_email, requester_title=requester_title
                    )
                    # Render outreach results
                    console.print("\n[bold green]✉️ Outreach Results[/bold green]")
                    ot = Table(show_header=True, header_style="bold")
                    ot.add_column("Dataset", style="yellow")
                    ot.add_column("Status", style="green")
                    ot.add_column("Message ID", style="cyan")
                    ot.add_column("Error", style="red")
                    for d, res in zip(chosen, outreach_results):
                        ot.add_row(
                            str(d.get("accession") or d.get("title")),
                            str(res.get("status") or ("sent" if res.get("success") else "failed")),
                            str(res.get("message_id") or "-"),
                            str(res.get("error") or res.get("error_message") or "-"),
                        )
                    console.print(ot)

    # Summary
    try:
        summary = await summarize(query, datasets, contacts, outreach_results)
        console.print("\n[bold cyan]🧾 Summary[/bold cyan]")
        console.print(summary.get("executive_summary", ""))
    except Exception:
        summary = {}

    console.print("\n[bold green]Done.[/bold green]")
    await log_provenance(
        actor=requester_email or "user",
        action="tui_completed",
        details={"datasets": len(datasets), "contacts": len(contacts), "outreach": len(outreach_results)},
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
