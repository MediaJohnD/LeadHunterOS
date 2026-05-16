"""LeadHunterOS v2 - Entry point.

Usage:
  python run_agent.py                          # Run once immediately
  python run_agent.py --schedule               # Run on schedule (every N minutes)
  python run_agent.py --objective "Find VP Sales at SaaS companies that just raised Series A"
  python run_agent.py --status                 # Show backend/Lemonade status and exit

No external scheduler needed - uses stdlib time.sleep() loop.
"""

import argparse
import json
import sys
import time
import subprocess
from datetime import datetime, timezone
from loguru import logger

import config
from agent.trajectory import load_trajectory, replay_summary
from agent.hermes_agent import HermesAgent
from agent.database import export_latest_leads_csv


DEFAULT_OBJECTIVE = (
    f"Hunt for high-quality SMB leads in {config.TARGET_METRO} and the broader {config.TARGET_REGION} market only. "
    f"Restrict all leads to companies operating in or originating from {config.TARGET_COUNTRY}. "
    "Focus on companies with roughly 5-250 employees in home services, agencies, IT services, legal, accounting, healthcare support, logistics, and local B2B software. "
    "Search for owner, founder, president, general manager, operations manager, and revenue leader titles. "
    "Use public in-country signals only: hiring, local expansion, funding, new office openings, service-area growth, technology upgrades, and business launches. "
    f"Enrich each lead, score against ICP, and save qualified leads (score >= "
    f"{getattr(config, 'ICP_MIN_SCORE', 70)}/100). "
    "Prepare CRM handoff notes for the top 3 qualified leads."
)


def _print_timeline(result: dict) -> None:
    timeline = result.get("timeline", [])
    if not timeline:
        print("\nTimeline: no events recorded.\n")
        return
    print("\n=== Run Timeline ===")
    for event in timeline:
        iteration = event.get("iteration", 0)
        name = event.get("event", "event")
        if name == "provider_response":
            print(
                f"  i{iteration} provider={event.get('provider')} "
                f"model={event.get('model')} latency_ms={event.get('latency_ms')}"
            )
        elif name == "tool_called":
            print(f"  i{iteration} tool={event.get('tool_name')}")
        elif name == "gate_block":
            print(f"  i{iteration} gate={event.get('kind')} reason={event.get('reason')}")
        else:
            print(f"  i{iteration} {name}")
    print("====================\n")


def show_replay(path: str) -> None:
    summary = replay_summary(path)
    run = load_trajectory(path)
    print("\n=== Trajectory Replay ===")
    print(f"Run ID:      {summary['run_id']}")
    print(f"Objective:   {summary['objective']}")
    print(f"Steps:       {summary['steps']}")
    print(f"Providers:   {summary['providers']}")
    print(f"Tools:       {summary['tools']}")
    print(f"Errors:      {summary['errors']}")
    print(f"Evaluation:  {summary['evaluation']}")
    print("\nStep Trace:")
    for step in run.steps:
        label = step.kind
        if step.tool_name:
            label += f" tool={step.tool_name}"
        if step.provider:
            label += f" provider={step.provider}"
        if step.latency_ms:
            label += f" latency_ms={step.latency_ms}"
        print(f"  {step.index:02d}. {label}")
    print("=========================\n")


def run_once(
    objective: str,
    llm_backend: str | None = None,
    print_timeline: bool = False,
    strict_pass: bool = False,
) -> int:
    """Run one agent cycle."""
    logger.info(f"Starting LeadHunterOS agent cycle | {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"Objective: {objective[:120]}..." if len(objective) > 120 else f"Objective: {objective}")

    try:
        agent = HermesAgent(preferred_backend=llm_backend)
        result = agent.run(objective)
        logger.success(f"Agent cycle complete. Result preview: {str(result)[:300]}")
        if print_timeline:
            _print_timeline(result)
        if config.EXPORT_LEADS_TO_CSV:
            export = export_latest_leads_csv(config.LEADS_CSV_PATH, limit=config.LEAD_MAX_RESULTS)
            logger.info(f"CSV export complete: {export['path']} ({export['rows']} rows)")
        if strict_pass and (result.get("failed") or int(result.get("leads_saved", 0)) < int(getattr(config, "RUN_FAIL_MIN_SAVED_LEADS", 3))):
            logger.error("Strict pass failed: run did not meet hard save contract.")
            return 2
        return 0
    except Exception as e:
        logger.error(f"Agent cycle failed: {e}")
        raise


def run_scheduled(
    objective: str,
    interval_minutes: int,
    llm_backend: str | None = None,
    print_timeline: bool = False,
) -> None:
    """Run agent on a repeating schedule using stdlib time.sleep().

    No apscheduler or external dependencies needed.
    Press Ctrl+C to stop.
    """
    logger.info(f"Scheduled mode: running every {interval_minutes} minutes. Press Ctrl+C to stop.")

    # Run immediately on first start
    run_once(objective, llm_backend=llm_backend, print_timeline=print_timeline)

    while True:
        next_run = datetime.now(timezone.utc)
        sleep_seconds = interval_minutes * 60
        logger.info(f"Next run in {interval_minutes} minutes. Sleeping...")
        try:
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            logger.info("Scheduled run interrupted by user. Exiting.")
            sys.exit(0)
        run_once(objective, llm_backend=llm_backend, print_timeline=print_timeline)


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
    parser.add_argument(
        "--timeline",
        action="store_true",
        help="Print a human-readable run timeline after execution",
    )
    parser.add_argument(
        "--strict-pass",
        action="store_true",
        help="Exit non-zero unless run meets hard save contract.",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="Run deterministic daily HOT lead batch and digest generation.",
    )
    parser.add_argument(
        "--replay",
        type=str,
        default="",
        help="Path to a saved trajectory JSON to replay and inspect",
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
    if args.replay:
        show_replay(args.replay)
        sys.exit(0)

    if args.daily:
        batch_cmd = [
            "python",
            "scripts/run_daily_hot_batch.py",
            "--gating",
            "ops/hot_warm_gating.yaml",
            "--target-hot",
            str(getattr(config, "DAILY_HOT_TARGET", 10)),
            "--target-warm",
            str(getattr(config, "DAILY_WARM_TARGET", 100)),
            "--objective",
            args.objective,
        ]
        batch = subprocess.run(batch_cmd, cwd=".", capture_output=True, text=True, check=False)
        print(batch.stdout)
        if batch.returncode != 0:
            alert_payload = {
                "status": "FAILED",
                "reason": "DAILY_HOT_TARGET_UNMET",
                "target_hot": getattr(config, "DAILY_HOT_TARGET", 10),
                "objective": args.objective,
                "details": (batch.stdout or batch.stderr)[-3000:],
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            print(alert_payload)
            try:
                from urllib.request import Request, urlopen
                if getattr(config, "SLACK_WEBHOOK_URL", "").strip():
                    req = Request(
                        config.SLACK_WEBHOOK_URL,
                        data=json.dumps({"text": f":rotating_light: LeadHunterOS daily failed\n```{json.dumps(alert_payload, indent=2)}```"}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(req, timeout=8):
                        pass
            except Exception as exc:
                logger.error(f"Slack alert send failed: {exc}")
            sys.exit(2)
        digest = subprocess.run(
            ["python", "scripts/generate_morning_digest.py", "--hot-limit", str(getattr(config, "DAILY_HOT_TARGET", 10)), "--warm-limit", str(getattr(config, "DAILY_WARM_TARGET", 100))],
            cwd=".",
            capture_output=True,
            text=True,
            check=False,
        )
        print(digest.stdout)
        if digest.returncode != 0:
            logger.error(digest.stderr or "Morning digest generation failed")
            sys.exit(3)
        sys.exit(0)

    if args.schedule:
        run_scheduled(args.objective, args.interval, llm_backend=args.llm, print_timeline=args.timeline)
    else:
        rc = run_once(args.objective, llm_backend=args.llm, print_timeline=args.timeline, strict_pass=args.strict_pass)
        sys.exit(rc)


if __name__ == "__main__":
    main()
