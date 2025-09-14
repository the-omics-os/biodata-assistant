#!/usr/bin/env python3
"""
🎛️ Omics-OS Lead Generation TUI
Interactive terminal UI for GitHub issue prospecting and personalized outreach:
- GitHub issues scraping via Browser-Use (visible browser)
- AI-powered lead qualification and prospect identification
- Persona-based casual email outreach via AgentMail

Requirements:
- OPENAI_API_KEY set (for Browser-Use LLM and AI qualification)
- AGENTMAIL_API_KEY set (if sending emails)
- .env loaded by backend/app/config.py (pydantic-settings)

Usage (interactive defaults):
  python backend/demo.py

Optional flags:
  python backend/demo.py --repos scanpy,anndata --max-issues 25 --show-browser --send-emails

Notes:
- Shows real browsers (headless=False) when --show-browser is set (default True in TUI).
- All emailing requires explicit confirmation in the TUI even if --send-emails is passed.
- Uses AI to intelligently identify struggling bioinformatics users.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
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

from dotenv import load_dotenv
load_dotenv()

# Backend imports
from app.config import settings
from app.core.agents.github_leads_agent import prospect_github_issues
from app.core.agents.email_agent import send_product_invite_direct, ProductInviteParams
from app.utils.personas import select_persona
from app.core.utils.provenance import log_provenance
from app.core.database import init_db
from app.utils.email_templates import generate_email_template

console = Console()
logger = logging.getLogger(__name__)


def ensure_exports_dir() -> str:
    path = os.path.join("backend", "exports")
    os.makedirs(path, exist_ok=True)
    return path


def save_json_artifact(name: str, data: Any) -> str:
    path = ensure_exports_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{name}_{ts}.json"
    fpath = os.path.join(path, fname)
    with open(fpath, "w") as f:
        json.dump(data, f, indent=2)
    return fpath


def save_csv(name: str, rows: List[Dict[str, Any]], fields: List[str]) -> str:
    path = ensure_exports_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{name}_{ts}.csv"
    fpath = os.path.join(path, fname)
    with open(fpath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})
    return fpath


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Omics-OS Lead Generation TUI")
    parser.add_argument(
        "--repos",
        type=str,
        default="scverse/scanpy",
        # default="scverse/scanpy,scverse/anndata",
        help="GitHub repositories to prospect (comma-separated, format: owner/repo)",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        default=5,
        help="Max issues to fetch per repository (default 5)",
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
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run non-interactively using default values for all prompts",
    )
    return parser.parse_args()


def validate_env(send_emails: bool) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    # Browser-Use LLM key
    if not (settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")):
        issues.append(
            "OPENAI_API_KEY missing. Required for Browser-Use LLM (GitHub scraping)."
        )
    if send_emails and not (settings.AGENTMAIL_API_KEY or os.getenv("AGENTMAIL_API_KEY")):
        issues.append(
            "AGENTMAIL_API_KEY missing. Required to send emails via AgentMail."
        )
    return (len(issues) == 0, issues)


def banner() -> None:
    rprint(
        Panel.fit(
            "[bold cyan]🧬 OMICS-OS LEAD GENERATION — Interactive TUI[/bold cyan]\n"
            "[yellow]AI-Powered GitHub Prospecting for Bioinformatics Users[/yellow]\n\n"
            "• GitHub issues scraping (scanpy/anndata repositories)\n"
            "• AI-powered lead qualification and prospect identification\n"
            "• Persona-based casual outreach via AgentMail\n"
            "• Human-gated email confirmation\n",
            border_style="cyan",
        )
    )


async def run_github_prospecting(repos: List[str], max_issues: int) -> List[Dict[str, Any]]:
    """Run GitHub issues prospecting workflow with AI qualification."""
    try:
        leads = await prospect_github_issues(
            target_repos=repos,
            max_issues_per_repo=max_issues,
            require_email=True,
            persist_to_db=True,
        )
        return leads
    except Exception as e:
        console.print(f"[red]GitHub prospecting failed: {e}[/red]")
        logger.error(f"GitHub prospecting error: {e}")
        return []


def render_leads(leads: List[Dict[str, Any]]) -> None:
    """Render GitHub leads in a table format."""
    if not leads:
        console.print("[yellow]No AI-qualified leads found.[/yellow]")
        return
        
    console.print("\n[bold magenta]🎯 GitHub Leads (AI-Qualified Prospects)[/bold magenta]")
    t = Table(show_header=True, header_style="bold", show_lines=True)
    t.add_column("#", style="cyan", width=4)
    t.add_column("User", style="yellow")
    t.add_column("Issue Title", style="white", overflow="fold")
    t.add_column("Repo", style="blue")
    t.add_column("Priority", style="green")
    t.add_column("Email", style="cyan")
    t.add_column("AI Reason", style="magenta", overflow="fold")

    for idx, lead in enumerate(leads, start=1):
        signals = lead.get("signals", {})
        qualification_reason = signals.get("qualification_reason", "AI approved")
        priority = signals.get("contact_priority", "medium").upper()
        
        t.add_row(
            str(idx),
            str(lead.get("user_login") or ""),
            str(lead.get("issue_title") or "")[:50] + ("..." if len(str(lead.get("issue_title") or "")) > 50 else ""),
            str(lead.get("repo") or "").split("/")[-1],
            priority,
            str(lead.get("email") or "-"),
            qualification_reason[:60] + ("..." if len(qualification_reason) > 60 else ""),
        )
    console.print(t)


def select_leads_for_outreach(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Interactive lead selection for outreach."""
    if not leads:
        return []
    
    # All leads are pre-qualified by AI, so show all as eligible
    eligible_idx = list(range(1, len(leads) + 1))
    
    console.print(
        f"\n[bold]Select leads for omics-os outreach:[/bold]\n"
        f"All {len(leads)} leads are AI-qualified prospects with contact information\n"
        "Enter space-separated indexes (e.g. '1 3 5'), or 'all' to select all, or leave blank to skip."
    )
    choice = Prompt.ask("Your selection", default="").strip()
    if not choice:
        return []
        
    selected: List[int] = []
    if choice.lower() == "all":
        selected = eligible_idx
    else:
        for tok in choice.split():
            try:
                n = int(tok)
                if 1 <= n <= len(leads):
                    selected.append(n)
            except Exception:
                continue
    
    return [leads[i - 1] for i in selected]


async def send_outreach_for_leads(leads: List[Dict[str, Any]], style: str = "casual") -> List[Dict[str, Any]]:
    """Send persona-based outreach emails for selected leads."""
    results: List[Dict[str, Any]] = []
    
    for lead in leads:
        try:
            # Select appropriate persona for this lead
            persona = select_persona(lead)
            
            # Extract recipient name from GitHub username (fallback)
            recipient_name = lead.get("user_login", "there")
            if recipient_name and recipient_name != "there":
                # Capitalize first letter for friendlier tone
                recipient_name = recipient_name.replace("_", " ").replace("-", " ").title()
            
            # Prepare outreach parameters
            params = ProductInviteParams(
                lead_id=str(lead.get("issue_url", "")),
                repo=lead.get("repo", ""),
                issue_title=lead.get("issue_title", ""),
                recipient_name=recipient_name,
                recipient_email=lead.get("email", ""),
                persona_name=persona.name,
                persona_title=persona.title,
                persona_from_email=persona.from_email,
                message_style=style,
            )
            
            # Send the email
            result = await send_product_invite_direct(params)
            result["lead_user"] = lead.get("user_login")
            result["lead_repo"] = lead.get("repo")
            result["persona_used"] = persona.name
            results.append(result)
            
        except Exception as e:
            logger.error(f"Failed to send outreach to {lead.get('user_login')}: {e}")
            results.append({
                "success": False,
                "status": "failed",
                "error_message": str(e),
                "lead_user": lead.get("user_login"),
                "lead_repo": lead.get("repo"),
            })
    
    return results


def render_outreach_results(leads: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> None:
    """Render outreach results in a table format."""
    console.print("\n[bold green]📧 Outreach Results[/bold green]")
    ot = Table(show_header=True, header_style="bold")
    ot.add_column("User", style="yellow")
    ot.add_column("Repo", style="blue")
    ot.add_column("Persona", style="magenta")
    ot.add_column("Status", style="green")
    ot.add_column("Message ID", style="cyan")
    ot.add_column("Error", style="red")
    
    for lead, res in zip(leads, results):
        ot.add_row(
            str(lead.get("user_login", "")),
            str(lead.get("repo", "")).split("/")[-1],
            str(res.get("persona_used", "")),
            str(res.get("status") or ("sent" if res.get("success") else "failed")),
            str(res.get("message_id") or "-"),
            str(res.get("error") or res.get("error_message") or "-"),
        )
    console.print(ot)


async def main() -> None:
    args = parse_args()
    banner()

    # Ensure database tables exist before any provenance logging
    try:
        await init_db()
    except Exception as e:
        console.print(f"[yellow]Database initialization warning: {e}[/yellow]")

    # Parse target repositories
    repos = [repo.strip() for repo in args.repos.split(",") if repo.strip()]
    if not repos:
        repos = ["scverse/scanpy"]
        # repos = ["scverse/scanpy", "scverse/anndata"]
    
    # Get max issues per repo
    if args.demo:
        max_issues = args.max_issues
    else:
        max_issues = IntPrompt.ask(
            "Max issues to fetch per repository", 
            default=args.max_issues,
            show_default=True
        )
    
    # Show browsers (headless=False) toggle
    if args.show_browser:
        show_browser = True
    elif args.demo:
        show_browser = True
    else:
        show_browser = Confirm.ask("Show live browsers for scraping? (recommended for dev)", default=True)

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
        if args.demo:
            console.print("[yellow]Continuing in demo mode despite environment issues.[/yellow]")
        else:
            if not Confirm.ask("Continue anyway (GitHub scraping may fail or emailing disabled)?", default=False):
                sys.exit(1)

    await log_provenance(
        actor="user",
        action="github_prospecting_started",
        details={
            "repos": repos,
            "max_issues": max_issues,
            "show_browser": show_browser
        },
    )

    # Main execution: GitHub prospecting workflow with AI qualification
    leads: List[Dict[str, Any]] = []
    
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        tk = progress.add_task("[cyan]Prospecting GitHub issues with AI qualification...", total=None)
        try:
            leads = await run_github_prospecting(repos, max_issues)
            progress.update(tk, description=f"[green]✓ AI-qualified leads found: {len(leads)}", completed=True)
            
            # Display leads immediately
            render_leads(leads)
            
            # Save lead artifacts
            try:
                lead_rows = [
                    {
                        "user_login": lead.get("user_login"),
                        "repo": lead.get("repo"),
                        "issue_title": lead.get("issue_title"),
                        "issue_url": lead.get("issue_url"),
                        "email": lead.get("email"),
                        "novice_score": lead.get("novice_score"),
                        "signals_keywords": ", ".join(lead.get("signals", {}).get("keywords", [])),
                        "account_age_days": lead.get("signals", {}).get("account_age_days"),
                        "followers": lead.get("signals", {}).get("followers"),
                    }
                    for lead in leads
                ]
                leads_json_path = save_json_artifact("github_leads", leads)
                leads_csv_path = save_csv("github_leads", lead_rows, [
                    "user_login", "repo", "issue_title", "issue_url", "email", 
                    "novice_score", "signals_keywords", "account_age_days", "followers"
                ])
                console.print(f"[dim]Saved leads to {leads_json_path} and {leads_csv_path}[/dim]")
            except Exception as e:
                logger.debug(f"Failed to save lead artifacts: {e}")
                
        except Exception as e:
            progress.update(tk, description=f"[red]GitHub prospecting failed: {e}", completed=True)
            logger.error(f"GitHub prospecting error: {e}")

    # Lead selection for outreach
    selected_leads: List[Dict[str, Any]] = []
    if args.demo:
        # In demo mode, select first 2 leads if any
        selected_leads = leads[:2]
    else:
        selected_leads = select_leads_for_outreach(leads)

    outreach_results: List[Dict[str, Any]] = []

    if selected_leads:
        console.print("\n[bold cyan]📧 Omics-OS Outreach Preparation[/bold cyan]")
        console.print("Persona-based emails will be composed and sent via AgentMail with provenance logging.")
        
        # Preview emails before sending
        if not args.demo and Confirm.ask("Preview outreach emails before sending?", default=True):
            for lead in selected_leads:
                persona = select_persona(lead)
                recipient_name = lead.get("user_login", "there").replace("_", " ").replace("-", " ").title()
                
                tpl = generate_email_template(
                    template_type="product_invite",
                    persona_name=persona.name,
                    persona_title=persona.title,
                    repo=lead.get("repo", ""),
                    issue_title=lead.get("issue_title", ""),
                    recipient_name=recipient_name,
                )
                body_preview = (tpl.get("body","")[:400] + ("..." if len(tpl.get("body",""))>400 else ""))
                console.print(Panel.fit(
                    f"Subject: {tpl.get('subject','')}\n\nFrom: {persona.name} <{persona.from_email}>\n\n{body_preview}", 
                    title=f"Preview: {lead.get('user_login')} - {persona.name}"
                ))

        # Allow sending?
        if not allow_send_flag and not Confirm.ask("Send omics-os emails now via AgentMail?", default=False):
            console.print("[yellow]Skipping email sending.[/yellow]")
        else:
            ok_env, issues = validate_env(send_emails=True)
            if not ok_env:
                console.print(Panel.fit("\n".join(issues), title="Email Disabled", border_style="red"))
            else:
                if not Confirm.ask(f"Confirm sending {len(selected_leads)} persona-based emails now?", default=False):
                    console.print("[yellow]Email sending cancelled by user.[/yellow]")
                else:
                    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
                        email_tk = progress.add_task("[cyan]Sending persona-based outreach emails...", total=None)
                        outreach_results = await send_outreach_for_leads(selected_leads, style="casual")
                        progress.update(email_tk, description=f"[green]✓ Emails sent: {len(outreach_results)}", completed=True)
                    
                    # Render outreach results
                    render_outreach_results(selected_leads, outreach_results)
                    
                    # Save outreach artifacts
                    try:
                        orows = [
                            {
                                "user": res.get("lead_user"),
                                "repo": res.get("lead_repo"),
                                "persona": res.get("persona_used"),
                                "status": res.get("status") or ("sent" if res.get("success") else "failed"),
                                "message_id": res.get("message_id"),
                                "error": res.get("error") or res.get("error_message"),
                            }
                            for res in outreach_results
                        ]
                        ojson = save_json_artifact("outreach_results", outreach_results)
                        ocsv = save_csv("outreach_results", orows, ["user","repo","persona","status","message_id","error"])
                        console.print(f"[dim]Saved outreach results to {ojson} and {ocsv}[/dim]")
                    except Exception as e:
                        logger.debug(f"Failed to save outreach artifacts: {e}")

    # Final summary
    console.print(f"\n[bold green]🎯 Prospecting Complete![/bold green]")
    console.print(f"• Total leads found: {len(leads)}")
    console.print(f"• Leads selected for outreach: {len(selected_leads)}")
    console.print(f"• Emails sent: {len([r for r in outreach_results if r.get('success')])}")
    
    if outreach_results:
        success_count = len([r for r in outreach_results if r.get("success")])
        console.print(f"• Success rate: {success_count}/{len(outreach_results)} ({success_count/len(outreach_results)*100:.1f}%)")

    await log_provenance(
        actor="user",
        action="github_prospecting_completed",
        details={
            "leads_found": len(leads),
            "leads_selected": len(selected_leads),
            "emails_sent": len([r for r in outreach_results if r.get("success")]),
        },
    )

    console.print("\n[bold green]Done.[/bold green]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
