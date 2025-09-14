#!/usr/bin/env python3
"""
📧 AgentMail Email Testing Script

Simple utility to test email sending functionality using AgentMail.
Uses configuration from .env file and prompts for recipient and message content.

Usage:
  python backend/test_email.py

Requirements:
- AGENTMAIL_API_KEY set in .env
- Valid recipient email address
"""

import asyncio
import logging
import sys
from typing import Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import print as rprint

from dotenv import load_dotenv
load_dotenv()

# Backend imports
from app.config import settings
from app.core.integrations.agentmail_client import AgentMailClient, EmailMessage

console = Console()
logger = logging.getLogger(__name__)


def banner() -> None:
    """Display banner for the email testing utility."""
    rprint(
        Panel.fit(
            "[bold cyan]📧 AGENTMAIL EMAIL TESTING UTILITY[/bold cyan]\n"
            "[yellow]Simple script to test email sending functionality[/yellow]\n\n"
            "• Uses AgentMail API for email delivery\n"
            "• Loads configuration from .env file\n"
            "• Interactive prompts for recipient and content\n",
            border_style="cyan",
        )
    )


def validate_environment() -> tuple[bool, list[str]]:
    """Validate that required environment variables are set."""
    issues = []
    
    if not settings.AGENTMAIL_API_KEY:
        issues.append("AGENTMAIL_API_KEY missing in .env file")
    
    return len(issues) == 0, issues


async def send_test_email(recipient: str, subject: str, body: str, from_email: str) -> Dict[str, Any]:
    """Send a test email using AgentMailClient."""
    client = AgentMailClient()
    
    # Check if client is enabled
    if not client.enabled:
        return {
            "success": False,
            "status": "failed",
            "error": "AgentMail client not enabled (check API key)",
        }
    
    # Create email message
    message = EmailMessage(
        to=recipient,
        from_email=from_email,
        subject=subject,
        body=body,
        metadata={
            "test": "true",
            "sender": "email_test_script",
        },
    )
    
    console.print(f"\n[cyan]Sending email via AgentMail...[/cyan]")
    console.print(f"From: {from_email}")
    console.print(f"To: {recipient}")
    console.print(f"Subject: {subject}")
    console.print()
    
    # Send the email
    result = await client.send_email(message)
    return result


def get_user_input() -> tuple[str, str, str, str]:
    """Get email details from user input."""
    console.print("\n[bold green]📝 Email Details[/bold green]")
    
    # Get recipient email
    recipient = Prompt.ask(
        "Recipient email address",
        default="",
    ).strip()
    
    if not recipient:
        console.print("[red]Recipient email is required![/red]")
        sys.exit(1)
    
    # Get sender email (use a default test email)
    from_email = Prompt.ask(
        "From email address",
        default="test@omics-os.com",
    ).strip()
    
    # Get subject
    subject = Prompt.ask(
        "Email subject",
        default="Test Email from AgentMail",
    ).strip()
    
    # Get email body
    console.print("\n[yellow]Enter your email message (press Enter twice to finish):[/yellow]")
    lines = []
    empty_lines = 0
    
    while True:
        try:
            line = input()
            if line.strip() == "":
                empty_lines += 1
                if empty_lines >= 2:
                    break
            else:
                empty_lines = 0
            lines.append(line)
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled by user.[/yellow]")
            sys.exit(0)
    
    # Remove trailing empty lines
    while lines and lines[-1].strip() == "":
        lines.pop()
    
    body = "\n".join(lines)
    
    if not body.strip():
        body = "This is a test email sent via AgentMail API."
    
    return recipient, from_email, subject, body


def display_result(result: Dict[str, Any]) -> None:
    """Display the result of the email sending attempt."""
    if result.get("success"):
        console.print("\n[bold green]✅ Email sent successfully![/bold green]")
        console.print(f"Message ID: {result.get('message_id', 'N/A')}")
        console.print(f"Thread ID: {result.get('thread_id', 'N/A')}")
        console.print(f"Status: {result.get('status', 'sent')}")
        
        if result.get("headers"):
            console.print("\n[dim]Response headers received ✓[/dim]")
        
    else:
        console.print("\n[bold red]❌ Email sending failed![/bold red]")
        console.print(f"Status: {result.get('status', 'unknown')}")
        console.print(f"Error: {result.get('error', 'Unknown error')}")
        
        if result.get('status_code'):
            console.print(f"Status Code: {result.get('status_code')}")


async def main() -> None:
    """Main function to run the email test."""
    banner()
    
    # Validate environment
    env_ok, issues = validate_environment()
    if not env_ok:
        console.print(
            Panel.fit(
                "\n".join(issues),
                title="Environment Issues",
                border_style="red",
            )
        )
        console.print("\n[yellow]Please check your .env file and ensure AGENTMAIL_API_KEY is set.[/yellow]")
        sys.exit(1)
    
    console.print("[green]✓ Environment validation passed[/green]")
    
    # Get user input
    try:
        recipient, from_email, subject, body = get_user_input()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user.[/yellow]")
        sys.exit(0)
    
    # Display preview
    console.print("\n[bold magenta]📋 Email Preview[/bold magenta]")
    preview_panel = Panel.fit(
        f"From: {from_email}\n"
        f"To: {recipient}\n"
        f"Subject: {subject}\n\n"
        f"{body[:200]}{'...' if len(body) > 200 else ''}",
        title="Email Content",
        border_style="magenta",
    )
    console.print(preview_panel)
    
    # Confirm sending
    if not Confirm.ask("\nSend this email?", default=True):
        console.print("[yellow]Email sending cancelled.[/yellow]")
        sys.exit(0)
    
    # Send the email
    try:
        result = await send_test_email(recipient, subject, body, from_email)
        display_result(result)
        
    except Exception as e:
        console.print(f"\n[bold red]❌ Unexpected error occurred:[/bold red]")
        console.print(f"[red]{str(e)}[/red]")
        logger.error(f"Email test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        sys.exit(1)
