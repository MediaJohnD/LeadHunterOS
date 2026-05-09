"""LeadHunterOS v2 - Entry point.

Usage:
  python run_agent.py                          # Run once immediately
  python run_agent.py --schedule               # Run on schedule (every N minutes)
  python run_agent.py --objective "Find VP Sales at SaaS companies that just raised Series A"
  python run_agent.py --status                 # Show backend/Lemonade status and exit

No external scheduler needed - uses stdlib time.sleep() loop.
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from loguru import logger

import config
from agent.hermes_agent import HermesAgent


DEFAULT_OBJECTIVE = (
    f"Hunt for high-quality SMB leads in {config.TARGET_METRO} and the broader {config.TARGET_REGION} market only. "
    "Focus on U.S.-based companies with roughly 5-250 employees in home services, agencies, IT services, legal, accounting, healthcare support, logistics, and local B2B software. "
    "Search for owner, founder, president, general manager, operations manager, and revenue leader titles. "
    "Use public U.S. signals only: hiring, local expansion, funding, new office openings, service-area growth, technology upgrades, and business launches. "
    f"Enrich each lead, score against ICP, and save qualified leads (score >= "
    f"{getattr(config, 'ICP_MIN_SCORE', 70)}/100). "
    "Draft personalized outreach for the top 3 leads."
)


def run_once(objective: str, llm_backend: str | None = None) -> None:
    """Run one agent cycle."""
    logger.info(f"Starting LeadHunterOS agent cycle | {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"Objective: {objective[:120]}..." if len(objective) > 120 else f"Objective: {objective}")

    try:
        agent = HermesAgent(preferred_backend=llm_backend)
        result = agent.run(objective)
        logger.success(f"Agent cycle complete. Result preview: {str(result)[:300]}")
    except Exception as e:
        logger.error(f"Agent cycle failed: {e}")
        raise


def run_scheduled(objective: str, interval_minutes: int, llm_backend: str | None = None) -> None:
    """Run agent on a repeating schedule using stdlib time.sleep().

    No apscheduler or external dependencies needed.
    Press Ctrl+C to stop.
    """
    logger.info(f"Scheduled mode: running every {interval_minutes} minutes. Press Ctrl+C to stop.")

    # Run immediately on first start
    run_once(objective, llm_backend=llm_backend)

    while True:
        next_run = datetime.now(timezone.utc)
        sleep_seconds = interval_minutes * 60
        logger.info(f"Next run in {interval_minutes} minutes. Sleeping...")
        try:
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            logger.info("Scheduled run interrupted by user. Exiting.")
            sys.exit(0)
        run_once(objective, llm_backend=llm_backend)


def show_status() -> None:
    """Show current LLM router status and Lemonade connectivity."""
    from agent.llm_router import LLMRouter
    router = LLMRouter()
    status = router.get_status()
    print("\n=== LeadHunterOS v2 - Backend Status ===")
    print(f"  Default backend:      {status['default_backend']}")
    print(f"  Available backends:   {status['available_backends']}")
    print(f"  Lemonade URL:         {status['lemonade_url']}")
    print(f"  Lemonade model:       {status['lemonade_model']}")
    print(f"  Lemonade reachable:   {status['lemonade_reachable']}")
    print(f"  Claude configured:    {status['claude_configured']}")
    print(f"  OpenAI configured:    {status['openai_configured']}")
    print(f"  Perplexity configured:{status['perplexity_configured']}")
    print("========================================\n")
    if not status['lemonade_reachable']:
        print("  ACTION NEEDED: Lemonade is not reachable.")
        print("  1. Start Lemonade:  lemonade serve")
        print("  2. Load a model:    lemonade load user.Qwen3-7B-Instruct-Q4_K_M-GGUF")
        print("  3. Check status:    lemonade status")
        print(f"  4. Verify URL:      {status['lemonade_url']}/models")
        print("")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LeadHunterOS v2 - AMD-local Hermes agent for B2B lead hunting"
    )
    parser.add_argument(
        "--objective",
        type=str,
        default=DEFAULT_OBJECTIVE,
        help="The lead-hunting objective for this run",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help=f"Run on schedule every {config.AGENT_LOOP_INTERVAL_MINUTES} minutes",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=config.AGENT_LOOP_INTERVAL_MINUTES,
        help="Interval in minutes between scheduled runs (default from config)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show backend status and exit",
    )
    parser.add_argument(
        "--llm",
        choices=["local", "claude", "openai", "perplexity"],
        default=None,
        help="Preferred LLM backend for this run",
    )
    args = parser.parse_args()

    # Configure logger
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO",
    )
    logger.add(
        "leadhunter.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
    )

    if args.status:
        show_status()
        sys.exit(0)

    if args.schedule:
        run_scheduled(args.objective, args.interval, llm_backend=args.llm)
    else:
        run_once(args.objective, llm_backend=args.llm)


if __name__ == "__main__":
    main()
