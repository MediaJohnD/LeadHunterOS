"""LeadHunterOS v2 - Entry point.

Usage:
  python run_agent.py                          # Run once immediately
  python run_agent.py --schedule               # Run on schedule (every N minutes)
  python run_agent.py --objective "Find VP Sales at SaaS companies that just raised Series B"
"""

import argparse
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger
from rich.console import Console
from rich.panel import Panel

import config
from agent.hermes_agent import HermesAgent

console = Console()

DEFAULT_OBJECTIVE = (
    "Hunt for high-quality B2B leads in SaaS and software companies with 10-500 employees. "
    "Search for VP of Sales, Head of Revenue, CRO, and Founder titles. "
    "Check Reddit and news for buying signals. "
    f"Enrich each lead, score against ICP, and save qualified leads (score >= {config.ICP_SCORE_THRESHOLD}). "
    "Draft personalized outreach for the top 3 leads."
)


def run_once(objective: str) -> None:
    """Run one agent cycle."""
    console.print(
        Panel(
            f"[bold green]LeadHunterOS v2 — True Hermes Agent[/bold green]\n"
            f"LLM: [cyan]{config.LEMONADE_MODEL}[/cyan] via Lemonade (local AMD)\n"
            f"Fallbacks: Claude → OpenAI → Perplexity\n"
            f"Lemonade: [cyan]{config.LEMONADE_BASE_URL}[/cyan]\n"
            f"Started: [yellow]{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}[/yellow]\n"
            f"Objective: {objective[:100]}...",
            title="🎯 LeadHunterOS",
            border_style="green",
        )
    )

    agent = HermesAgent()

    try:
        result = agent.run(objective)
        console.print("\n[bold green]✅ Agent completed[/bold green]")
        console.print(f"Session: {result['session_id']}")
        console.print(f"Steps taken: {len(result['steps'])}")
        console.print(f"Backends used: {result['llm_backends_used']}")

        if result.get("final_answer"):
            console.print(
                Panel(
                    result["final_answer"][:2000],
                    title="📋 Final Answer",
                    border_style="cyan",
                )
            )
        else:
            console.print("[yellow]No final answer produced.[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Agent error: {e}")
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="LeadHunterOS v2 - Hermes Lead Agent")
    parser.add_argument(
        "--objective",
        type=str,
        default=DEFAULT_OBJECTIVE,
        help="Task objective for the agent",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default=None,
        help="Target company domain for lead hunting (e.g. salesforce.com)",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run on a recurring schedule",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=config.SCHEDULE_INTERVAL_MINUTES,
        help="Schedule interval in minutes (default: from config)",
    )
    args = parser.parse_args()

    # Build objective
    objective = args.objective
    if args.domain:
        objective = f"Hunt leads at domain: {args.domain}. " + objective

    if args.schedule:
        console.print(f"[green]Scheduling agent every {args.interval} minutes...[/green]")
        scheduler = BlockingScheduler()
        scheduler.add_job(
            run_once,
            "interval",
            minutes=args.interval,
            args=[objective],
            next_run_time=datetime.now(timezone.utc),
        )
        try:
            scheduler.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]Scheduler stopped.[/yellow]")
    else:
        run_once(objective)


if __name__ == "__main__":
    main()
