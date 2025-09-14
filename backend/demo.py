#!/usr/bin/env python3
"""
🔬 BIODATA ASSISTANT DEMO
Hackathon Demonstration Script
Shows how we reduce cancer researcher's data discovery from 2-3 days to minutes
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint
import time

# Import our core components
from app.models.schemas import SearchRequest
from app.core.agent_orchestrator import AgentOrchestrator
from app.core.database import init_db

console = Console()

# Demo data for showcase
DEMO_QUERIES = {
    "p53_lung": "Find all P53 mutation datasets in lung adenocarcinoma with RNA-seq data",
    "tnbc_proteomics": "Triple negative breast cancer proteomics and transcriptomics datasets", 
    "clinical_trial": "Clinical trial data with patient treatment outcomes (PHI test)"
}

MOCK_USER = {
    "email": "researcher@cancerlab.com",
    "name": "Dr. Sarah Chen",
    "company": "Cancer Research Institute",
    "title": "Principal Investigator"
}

class BiodataAssistantDemo:
    """Demo runner for hackathon presentation"""
    
    def __init__(self):
        self.orchestrator = AgentOrchestrator()
        
    async def show_intro(self):
        """Display the problem statement"""
        console.clear()
        
        # Title
        rprint(Panel.fit(
            "[bold cyan]🔬 BIODATA ASSISTANT[/bold cyan]\n"
            "[yellow]AI-Powered Cancer Research Data Discovery[/yellow]",
            border_style="cyan"
        ))
        
        # Problem statement
        console.print("\n[bold red]❌ THE PROBLEM:[/bold red]")
        problems = Table(show_header=False, box=None, padding=(0, 2))
        problems.add_column("Issue", style="red")
        problems.add_row("• Manual search across 5+ databases (GEO, PRIDE, Ensembl...)")
        problems.add_row("• Finding contact emails manually via LinkedIn")
        problems.add_row("• Writing individual outreach emails")
        problems.add_row("• Waiting days for responses")
        problems.add_row("• [bold]Time required: 2-3 DAYS[/bold]")
        console.print(problems)
        
        # Solution
        console.print("\n[bold green]✅ OUR SOLUTION:[/bold green]")
        solutions = Table(show_header=False, box=None, padding=(0, 2))
        solutions.add_column("Feature", style="green")
        solutions.add_row("• AI agents search all databases in parallel")
        solutions.add_row("• Automatic colleague discovery via LinkedIn")
        solutions.add_row("• Professional outreach emails via AgentMail")
        solutions.add_row("• PHI safety checks built-in")
        solutions.add_row("• [bold]Time required: < 5 MINUTES[/bold]")
        console.print(solutions)
        
        console.print("\n[cyan]Press Enter to start demo...[/cyan]")
        input()
    
    async def run_search_demo(self, query_key: str = "p53_lung"):
        """Run a search demonstration"""
        query = DEMO_QUERIES[query_key]
        
        console.print(f"\n[bold cyan]🔍 RESEARCH QUERY:[/bold cyan] {query}")
        console.print(f"[dim]User: {MOCK_USER['name']} ({MOCK_USER['email']})[/dim]\n")
        
        # Create search request
        search_request = SearchRequest(
            query=query,
            sources=["GEO"],
            include_internal=True,
            max_results=5
        )
        
        # Show workflow steps with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            # Step 1: Understanding query
            task1 = progress.add_task("[cyan]Understanding research question...", total=None)
            await asyncio.sleep(1)  # Simulate processing
            progress.update(task1, completed=True, description="[green]✓ Research question analyzed")
            
            # Step 2: Searching databases
            task2 = progress.add_task("[cyan]Searching public databases (NCBI/GEO)...", total=None)
            await asyncio.sleep(2)  # Simulate search
            progress.update(task2, completed=True, description="[green]✓ Found 12 datasets")
            
            # Step 3: Finding colleagues
            task3 = progress.add_task("[cyan]Finding internal colleagues via LinkedIn...", total=None)
            await asyncio.sleep(1.5)  # Simulate LinkedIn search
            progress.update(task3, completed=True, description="[green]✓ Found 3 relevant colleagues")
            
            # Step 4: Preparing outreach
            task4 = progress.add_task("[cyan]Preparing outreach emails...", total=None)
            await asyncio.sleep(1)  # Simulate email generation
            progress.update(task4, completed=True, description="[green]✓ 5 emails prepared")
            
            # Step 5: Safety check
            if "clinical" in query.lower() or "patient" in query.lower():
                task5 = progress.add_task("[yellow]PHI detection - requiring approval...", total=None)
                await asyncio.sleep(1)
                progress.update(task5, completed=True, description="[yellow]⚠️  PHI detected - queued for approval")
        
        # Show results
        await self.display_results(query_key)
    
    async def display_results(self, query_key: str):
        """Display mock results in a nice format"""
        
        console.print("\n[bold green]📊 RESULTS:[/bold green]\n")
        
        # Dataset results table
        datasets_table = Table(title="Datasets Found", show_lines=True)
        datasets_table.add_column("Source", style="cyan")
        datasets_table.add_column("Accession", style="yellow")
        datasets_table.add_column("Title", style="white")
        datasets_table.add_column("Samples", style="green")
        datasets_table.add_column("Access", style="magenta")
        
        # Mock datasets based on query
        if query_key == "p53_lung":
            datasets_table.add_row("GEO", "GSE123456", "P53 mutations in lung adenocarcinoma", "247", "Public")
            datasets_table.add_row("GEO", "GSE789012", "Lung cancer RNA-seq with TP53 status", "189", "Request")
            datasets_table.add_row("GEO", "GSE345678", "NSCLC transcriptome profiling", "412", "Public")
            datasets_table.add_row("Internal", "INT_LC_001", "Lung cancer cohort 2023", "156", "Request")
        elif query_key == "tnbc_proteomics":
            datasets_table.add_row("PRIDE", "PXD012345", "TNBC proteomics profiling", "89", "Public")
            datasets_table.add_row("GEO", "GSE567890", "Triple negative breast cancer multi-omics", "234", "Request")
        else:
            datasets_table.add_row("GEO", "GSE999999", "Clinical trial outcomes dataset", "500", "Restricted")
        
        console.print(datasets_table)
        
        # Outreach status
        console.print("\n[bold cyan]📧 OUTREACH STATUS:[/bold cyan]")
        outreach_table = Table(show_header=False, box=None)
        outreach_table.add_column("Status", style="yellow")
        outreach_table.add_row("• 3 emails sent automatically")
        outreach_table.add_row("• 2 pending approval (senior contacts)")
        if query_key == "clinical_trial":
            outreach_table.add_row("• [red]1 blocked - PHI detected, requires review[/red]")
        console.print(outreach_table)
        
        # Time saved
        console.print("\n[bold green]⏱️  TIME COMPARISON:[/bold green]")
        time_table = Table(show_header=True, box=None)
        time_table.add_column("Traditional Approach", style="red")
        time_table.add_column("Biodata Assistant", style="green")
        time_table.add_row("2-3 days", "4.5 minutes")
        console.print(time_table)
        
        # Export option
        console.print("\n[dim]Results exported to: ./results/search_results.csv[/dim]")
    
    async def show_phi_safety_demo(self):
        """Demonstrate PHI safety features"""
        console.print("\n[bold yellow]🔒 PHI SAFETY DEMONSTRATION[/bold yellow]\n")
        
        # Run search with PHI-containing query
        await self.run_search_demo("clinical_trial")
        
        console.print("\n[bold yellow]Safety Features Activated:[/bold yellow]")
        safety_table = Table(show_header=False, box=None)
        safety_table.add_column("Feature", style="yellow")
        safety_table.add_row("✓ PHI keywords detected in dataset")
        safety_table.add_row("✓ Email queued for human approval")
        safety_table.add_row("✓ Audit trail logged for compliance")
        safety_table.add_row("✓ Sensitive data warning displayed")
        console.print(safety_table)
    
    async def show_value_proposition(self):
        """Show the key value props"""
        console.print("\n")
        value_panel = Panel(
            "[bold cyan]KEY VALUE PROPOSITION[/bold cyan]\n\n"
            "🚀 [green]Time Saved:[/green] 48+ hours per research project\n"
            "📊 [green]Coverage:[/green] Search 5+ databases simultaneously\n"
            "🤖 [green]Automation:[/green] Email outreach handled automatically\n"
            "🔒 [green]Compliance:[/green] PHI safety checks built-in\n"
            "📈 [green]Scale:[/green] Handle 100+ datasets per search\n\n"
            "[yellow]ROI: 10x productivity increase for cancer researchers[/yellow]",
            border_style="green"
        )
        console.print(value_panel)

async def main():
    """Run the complete demo"""
    demo = BiodataAssistantDemo()
    
    try:
        # Introduction
        await demo.show_intro()
        
        # Demo 1: Standard search
        console.print("\n[bold cyan]DEMO 1: P53 Lung Cancer Research[/bold cyan]")
        console.print("[dim]Searching for P53 mutation datasets in lung adenocarcinoma...[/dim]")
        await demo.run_search_demo("p53_lung")
        
        console.print("\n[cyan]Press Enter to continue to PHI safety demo...[/cyan]")
        input()
        
        # Demo 2: PHI safety
        console.clear()
        await demo.show_phi_safety_demo()
        
        # Value proposition
        await demo.show_value_proposition()
        
        # Closing
        console.print("\n[bold green]✨ DEMO COMPLETE![/bold green]")
        console.print("[dim]Thank you for watching the Biodata Assistant demonstration[/dim]\n")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error during demo: {e}[/red]")

if __name__ == "__main__":
    # Run the demo
    console.print("[cyan]Starting Biodata Assistant Demo...[/cyan]\n")
    asyncio.run(main())
