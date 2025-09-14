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

import json
import csv
from datetime import datetime

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
from app.core.agents.planner_agent import create_workflow_plan
from app.core.utils.provenance import log_provenance
from app.core.database import init_db
from app.utils.email_templates import generate_email_template

console = Console()


def flatten_contact_info(d: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten nested contact_info into contact_name/contact_email on root."""
    ci = d.get("contact_info") or {}
    if isinstance(ci, dict):
        d.setdefault("contact_name", ci.get("name"))
        d.setdefault("contact_email", ci.get("email"))
    return d


def ensure_exports_dir() -> str:
    path = os.path.join("backend", "exports")
    os.makedirs(path, exist_ok=True)
    return path


def save_json_artifact(name: str, data: Any) -> str:
    path = ensure_exports_dir()
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"{name}_{ts}.json"
    fpath = os.path.join(path, fname)
    with open(fpath, "w") as f:
        json.dump(data, f, indent=2)
    return fpath


def save_csv(name: str, rows: List[Dict[str, Any]], fields: List[str]) -> str:
    path = ensure_exports_dir()
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"{name}_{ts}.csv"
    fpath = os.path.join(path, fname)
    with open(fpath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})
    return fpath


def filter_and_sort_datasets(datasets: List[Dict[str, Any]], reqs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Apply user-provided filters (modalities, cancer_types, organism, min_samples)
    and sort by sample_size descending for easier triage.
    """
    if not datasets:
        return datasets

    modalities = set([m.lower() for m in (reqs.get("modalities") or [])])
    cancer_tokens = [c.lower() for c in (reqs.get("cancer_types") or [])]
    organism = (reqs.get("organism") or "").lower().strip()
    min_samples = reqs.get("min_samples")

    def matches(d: Dict[str, Any]) -> bool:
        # Modality overlap (if specified)
        if modalities:
            ds_mods = {str(m).lower() for m in (d.get("modalities") or [])}
            if not (ds_mods & modalities):
                return False
        # Cancer tokens in title or structured cancer_types
        if cancer_tokens:
            title = (d.get("title") or "").lower()
            ds_cancers = [str(c).lower() for c in (d.get("cancer_types") or [])]
            if not any(tok in title for tok in cancer_tokens) and not any(tok in " ".join(ds_cancers) for tok in cancer_tokens):
                return False
        # Organism exact match (if provided)
        if organism:
            org = (d.get("organism") or "").lower()
            if organism != org:
                return False
        # Minimum sample size
        if isinstance(min_samples, int):
            try:
                n = int(d.get("sample_size") or 0)
                if n < min_samples:
                    return False
            except Exception:
                return False
        return True

    filtered = [flatten_contact_info(d.copy()) for d in datasets if matches(d)]
    # Sort by sample_size desc (None -> 0)
    def sort_key(d: Dict[str, Any]) -> Tuple[int, str]:
        try:
            n = int(d.get("sample_size") or 0)
        except Exception:
            n = 0
        return (n, str(d.get("accession") or d.get("title") or ""))

    filtered.sort(key=sort_key, reverse=True)
    return filtered


def prompt_research_requirements() -> Dict[str, Any]:
    """Prompt for optional filters to better scope the search."""
    console.print("\n[bold]Refine requirements (optional):[/bold]")
    modalities = Prompt.ask("Modalities (comma, e.g., rna-seq,scrna-seq,proteomics)", default="").strip()
    cancer_types = Prompt.ask("Cancer types (comma, e.g., lung adenocarcinoma,tnbc,breast)", default="").strip()
    organism = Prompt.ask("Organism", default="Homo sapiens").strip()
    min_samples = Prompt.ask("Minimum sample size (integer, optional)", default="").strip()
    req = {
        "modalities": [m.strip() for m in modalities.split(",") if m.strip()],
        "cancer_types": [c.strip() for c in cancer_types.split(",") if c.strip()],
        "organism": organism,
        "min_samples": int(min_samples) if min_samples.isdigit() else None,
    }
    return req


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


async def run_planner(req: SearchRequest) -> Dict[str, Any]:
    plan = await create_workflow_plan(req)
    if hasattr(plan, "model_dump"):
        return plan.model_dump()
    return dict(plan)


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
    from app.core.agents.biodatabase_agent import search_geo_direct
    out = await search_geo_direct(query=query, max_results=max_results)
    results: List[Dict[str, Any]] = []
    for item in out or []:
        d = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        d["database"] = "GEO"
        d = flatten_contact_info(d)
        if d.get("modalities") and not isinstance(d.get("modalities"), list):
            d["modalities"] = [str(d["modalities"])]
        results.append(d)
    return results


async def run_linkedin(company: str, departments: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
    from app.core.agents.colleagues_agent import search_linkedin_direct
    out = await search_linkedin_direct(company=company, departments=departments, keywords=keywords, max_results=10)
    contacts: List[Dict[str, Any]] = []
    for item in out or []:
        contacts.append(item.model_dump() if hasattr(item, "model_dump") else dict(item))
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
        contact = d.get("contact_email") or ((d.get("contact_info") or {}).get("email") if isinstance(d.get("contact_info"), dict) else None) or "-"
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
        if str(d.get("access_type", "")).lower() in {"request", "restricted"} and (
            d.get("contact_email") or ((d.get("contact_info") or {}).get("email") if isinstance(d.get("contact_info"), dict) else None)
        )
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
    project_context: str,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for d in datasets:
        contact_email = d.get("contact_email") or ((d.get("contact_info") or {}).get("email") if isinstance(d.get("contact_info"), dict) else None)
        if not contact_email:
            results.append({"success": False, "status": "skipped_no_contact", "error": "Missing contact email"})
            continue
        params = EmailOutreachParams(
            dataset_id=str(d.get("accession") or ""),
            dataset_title=str(d.get("title") or ""),
            requester_name=requester_name,
            requester_email=requester_email,
            requester_title=requester_title,
            contact_name=str(d.get("contact_name") or ((d.get("contact_info") or {}).get("name") if isinstance(d.get("contact_info"), dict) else "Data Custodian")),
            contact_email=str(contact_email or ""),
            project_description=f"{project_context}\n\nDataset: {str(d.get('title') or '')} ({str(d.get('accession') or '')})",
        )
        try:
            from app.core.agents.email_agent import send_outreach_direct
            res = await send_outreach_direct(params)
            results.append(res)
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

    # Ensure database tables exist before any provenance logging
    try:
        await init_db()
    except Exception:
        pass

    # Interactive inputs
    default_suggestions = [
        "I'm looking for a dataset from human plasma proteomics & transcriptomics in breast or lung cancer. I'm curious about the behavior of P53 mutations.",
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

    # Refine research requirements
    reqs = prompt_research_requirements()
    refined_tokens: List[str] = []
    if reqs.get("organism"):
        refined_tokens.append(reqs["organism"])
    if reqs.get("modalities"):
        refined_tokens.extend(reqs["modalities"])
    if reqs.get("cancer_types"):
        refined_tokens.extend(reqs["cancer_types"])
    refined_query = (query + " " + " ".join(refined_tokens)).strip()

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
    departments: List[str] = []
    li_keywords: List[str] = []
    if include_internal:
        company = Prompt.ask("Company to search on LinkedIn (public search)", default=os.getenv("COMPANY_NAME", "Omics-OS"))
        departments_str = Prompt.ask("Departments to include (comma-separated)", default="Bioinformatics,Genomics,Oncology,Data Science")
        departments = [d.strip() for d in departments_str.split(",") if d.strip()]
        keywords_str = Prompt.ask("Role keywords (comma-separated)", default="cancer,genomics,data")
        li_keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

    # Build search request
    search_req = SearchRequest(
        query=(refined_query if 'refined_query' in locals() and refined_query else query),
        modalities=(reqs.get("modalities") if 'reqs' in locals() else None),
        cancer_types=(reqs.get("cancer_types") if 'reqs' in locals() else None),
        include_internal=include_internal,
        max_results=max_results,
    )
    await log_provenance(
        actor=requester_email or "user",
        action="tui_started",
        details={"query": search_req.query, "max_results": max_results, "include_internal": include_internal, "show_browser": show_browser},
    )

    # Execution
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        tk = progress.add_task("[cyan]Planning...", total=None)
        try:
            plan = await run_planner(search_req)
            progress.update(tk, description="[green]✓ Plan created", completed=True)
        except Exception as e:
            progress.update(tk, description=f"[red]Plan failed: {e}", completed=True)
            plan = {}

        tk = progress.add_task("[cyan]Searching GEO (live browser)...", total=None)
        try:
            datasets = await run_geo(search_req.query, max_results)
            progress.update(tk, description=f"[green]✓ GEO results: {len(datasets)}", completed=True)
            # Save dataset artifacts
            try:
                ds_rows = [
                    {
                        "accession": d.get("accession"),
                        "title": d.get("title"),
                        "modalities": ", ".join(d.get("modalities") or []),
                        "sample_size": d.get("sample_size"),
                        "access_type": d.get("access_type"),
                        "contact_email": d.get("contact_email") or ((d.get("contact_info") or {}).get("email") if isinstance(d.get("contact_info"), dict) else None),
                        "link": d.get("link"),
                    }
                    for d in datasets
                ]
                ds_json_path = save_json_artifact("datasets_geo", datasets)
                ds_csv_path = save_csv("datasets_geo", ds_rows, ["accession","title","modalities","sample_size","access_type","contact_email","link"])
                console.print(f"[dim]Saved datasets to {ds_json_path} and {ds_csv_path}[/dim]")
                # Apply filters if provided
                try:
                    filtered = filter_and_sort_datasets(datasets, reqs)
                    if len(filtered) != len(datasets):
                        console.print(f"[dim]Applied filters -> {len(filtered)}/{len(datasets)} datasets match[/dim]")
                    datasets = filtered
                    # Save filtered artifacts
                    f_json = save_json_artifact("datasets_geo_filtered", datasets)
                    f_csv_rows = [
                        {
                            "accession": d.get("accession"),
                            "title": d.get("title"),
                            "modalities": ", ".join(d.get("modalities") or []),
                            "sample_size": d.get("sample_size"),
                            "access_type": d.get("access_type"),
                            "contact_email": d.get("contact_email") or ((d.get("contact_info") or {}).get("email") if isinstance(d.get("contact_info"), dict) else None),
                            "link": d.get("link"),
                        }
                        for d in datasets
                    ]
                    f_csv = save_csv("datasets_geo_filtered", f_csv_rows, ["accession","title","modalities","sample_size","access_type","contact_email","link"])
                    console.print(f"[dim]Saved filtered datasets to {f_json} and {f_csv}[/dim]")
                except Exception:
                    pass
            except Exception:
                pass
        except Exception as e:
            progress.update(tk, description=f"[red]GEO search failed: {e}", completed=True)
            datasets = []

        contacts: List[Dict[str, Any]] = []
        if include_internal:
            tk = progress.add_task("[cyan]Searching LinkedIn (live browser)...", total=None)
            try:
                contacts = await run_linkedin(company, departments=departments, keywords=li_keywords or ["cancer", "genomics", "data"])
                progress.update(tk, description=f"[green]✓ Contacts found: {len(contacts)}", completed=True)
                try:
                    ct_rows = [
                        {
                            "name": c.get("name"),
                            "job_title": c.get("job_title"),
                            "department": c.get("department"),
                            "email": c.get("email") or (", ".join(c.get("email_suggestions", []) or [])),
                            "linkedin_url": c.get("linkedin_url"),
                            "relevance_score": c.get("relevance_score"),
                        }
                        for c in contacts
                    ]
                    ct_json_path = save_json_artifact("contacts_linkedin", contacts)
                    ct_csv_path = save_csv("contacts_linkedin", ct_rows, ["name","job_title","department","email","linkedin_url","relevance_score"])
                    console.print(f"[dim]Saved contacts to {ct_json_path} and {ct_csv_path}[/dim]")
                except Exception:
                    pass
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
        # Optional email preview
        if Confirm.ask("Preview outreach emails before sending?", default=True):
            for d in chosen:
                contact_name = str(d.get("contact_name") or ((d.get("contact_info") or {}).get("name") if isinstance(d.get("contact_info"), dict) else "Data Custodian"))
                tpl = generate_email_template(
                    template_type="data_request",
                    dataset_title=str(d.get("title") or ""),
                    requester_name=requester_name,
                    requester_title=requester_title,
                    contact_name=contact_name,
                    project_description=(refined_query if 'refined_query' in locals() and refined_query else query),
                )
                body_preview = (tpl.get("body","")[:600] + ("..." if len(tpl.get("body",""))>600 else ""))
                console.print(Panel.fit(f"Subject: {tpl.get('subject','')}\n\n{body_preview}", title=f"Preview: {d.get('accession') or d.get('title')}"))

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
                        chosen,
                        requester_name=requester_name,
                        requester_email=requester_email,
                        requester_title=requester_title,
                        project_context=(refined_query if 'refined_query' in locals() and refined_query else query),
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
                    try:
                        orows = [
                            {
                                "dataset": (d.get("accession") or d.get("title")),
                                "status": (res.get("status") or ("sent" if res.get("success") else "failed")),
                                "message_id": res.get("message_id"),
                                "error": res.get("error") or res.get("error_message"),
                            }
                            for d, res in zip(chosen, outreach_results)
                        ]
                        ojson = save_json_artifact("outreach_results", outreach_results)
                        ocsv = save_csv("outreach_results", orows, ["dataset","status","message_id","error"])
                        console.print(f"[dim]Saved outreach results to {ojson} and {ocsv}[/dim]")
                    except Exception:
                        pass

    # Summary
    try:
        summary = await summarize(query, datasets, contacts, outreach_results)
        console.print("\n[bold cyan]🧾 Summary[/bold cyan]")
        console.print(summary.get("executive_summary", ""))
        if summary.get("next_steps"):
            console.print("\n[bold]Next steps:[/bold]")
            for s in summary["next_steps"]:
                console.print(f"- {s}")
        try:
            sjson = save_json_artifact("summary", summary)
            console.print(f"[dim]Saved summary to {sjson}[/dim]")
        except Exception:
            pass
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
