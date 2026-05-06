"""LeadHunterOS v2 - Entry point.

Usage:
  python run_agent.py                        # Run once immediately
  python run_agent.py --schedule             # Run on schedule (every N minutes)
  python run_agent.py --objective "Find VP Sales at SaaS companies that just raised Series A"
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
    "Enrich each lead, score against ICP, and save qualified leads (score >= {threshold}) to the database. "
    "Draft personalized outreach for the top 3 leads."
).format(threshold=config.ICP_SCORE_THRESHOLD)


def run_once(objective: str) -> None:
    """Run one agent cycle."""
    console.print(Panel(
        f"[bold green]LeadHunterOS v2 - Hermes Agent Edition[/bold green]\n"
        f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"LLM: [cyan]{config.OLLAMA_MODEL}[/cyan] (local Ollama) + Claude fallback\n"
        f"ICP threshold: [yellow]{config.ICP_SCORE_THRESHOLD}[/yellow]",
        title="LeadHunterOS v2",
    ))

    # Warn about missing config
    warnings = config.validate_config()
    for w in warnings:
        logger.warning(w)

    agent = HermesAgent()
    result = agent.run(objective)

    console.print(Panel(
        f"[bold]Agent completed[/bold]\n"
        f"Leads found: [green]{agent.leads_found}[/green]\n"
        f"Iterations: {agent.iterations}\n\n"
        f"[dim]{result}[/dim]",
        title="Results",
    ))


def main() -> None:
    parser = argparse.ArgumentParser(description="LeadHunterOS v2 - Hermes Agent")
    parser.add_argument(
        "--objective",
        type=str,
        default=DEFAULT_OBJECTIVE,
        help="Custom objective for the agent",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help=f"Run on a schedule every {config.AGENT_LOOP_INTERVAL_MINUTES} minutes",
    )
    args = parser.parse_args()

    if args.schedule:
        logger.info(
            f"Starting scheduler - running every {config.AGENT_LOOP_INTERVAL_MINUTES} minutes"
        )
        scheduler = BlockingScheduler()
        scheduler.add_job(
            run_once,
            "interval",
            minutes=config.AGENT_LOOP_INTERVAL_MINUTES,
            args=[args.objective],
            next_run_time=datetime.now(timezone.utc),  # Run immediately on start
        )
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")
    else:
        run_once(args.objective)


if __name__ == "__main__":
    main()
