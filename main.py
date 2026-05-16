"""
ARGUS Sentinel — CLI Entry Point
Usage:
  python main.py --query "What is OpenAI planning in the next 30 days?"
  python main.py --query "Monitor Stripe M&A signals" --watch
  python main.py --dashboard
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# ------------------------------------------------------------------ #
#  Rich terminal output (degrades gracefully if not installed)        #
# ------------------------------------------------------------------ #
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.text import Text
    from rich import print as rprint
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None

from orchestrator import ArgusOrchestrator, ArgusReport
from config import CONFIG

logging.basicConfig(
    level=logging.WARNING,  # Suppress noisy logs in CLI mode
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("argus.main")


# ------------------------------------------------------------------ #
#  Terminal rendering                                                  #
# ------------------------------------------------------------------ #

def score_color(v: float) -> str:
    if v >= 8: return "bold red"
    if v >= 5: return "bold yellow"
    if v >= 3: return "yellow"
    return "dim white"


def render_report_rich(report: ArgusReport):
    """Render a full intelligence report to the terminal using Rich."""
    console.print()
    console.rule("[bold blue]ARGUS Sentinel — Intelligence Report[/]")
    console.print(f"  [dim]Query:[/] {report.query}")
    console.print(f"  [dim]Entities:[/] {', '.join(report.entities)}")
    console.print(f"  [dim]Processed in:[/] {report.processing_time_s:.1f}s")

    if report.alert_triggered:
        console.print(
            Panel("⚠  ALERT TRIGGERED — Velocity threshold exceeded. "
                  "Immediate analyst review recommended.",
                  style="bold red", border_style="red")
        )

    for profile in report.profiles:
        console.print()
        console.rule(f"[cyan]Entity: {profile.entity}[/]")

        # Velocity scores
        table = Table(show_header=True, header_style="bold dim", box=None, padding=(0, 2))
        table.add_column("Source", style="dim")
        table.add_column("Velocity", justify="right")
        table.add_column("Composite", justify="right")
        table.add_column("Trajectory")
        table.add_column("Anomaly")

        for src, vel in profile.source_velocities.items():
            color = score_color(vel)
            table.add_row(
                src.upper(),
                f"[{color}]{vel:.1f}/10[/]",
                f"[{score_color(profile.velocity_score)}]{profile.velocity_score:.1f}/10[/]" if src == list(profile.source_velocities.keys())[0] else "",
                f"slope {profile.trajectory_slope:+.3f}" if src == list(profile.source_velocities.keys())[0] else "",
                "[red]YES[/]" if (profile.anomaly_detected and src == list(profile.source_velocities.keys())[0]) else "",
            )
        console.print(table)

        # Prediction
        confidence_pct = int(profile.prediction_confidence * 100)
        bar_filled = "█" * (confidence_pct // 5)
        bar_empty = "░" * (20 - confidence_pct // 5)
        console.print()
        console.print(Panel(
            f"[white]{profile.prediction}[/]\n\n"
            f"  Confidence: [{score_color(profile.prediction_confidence * 10)}]{bar_filled}[/][dim]{bar_empty}[/]  "
            f"[{score_color(profile.prediction_confidence * 10)}]{confidence_pct}%[/]",
            title="[bold]Prediction[/]",
            border_style="blue",
        ))

        # Top signals
        if profile.top_signals:
            console.print()
            console.print("  [bold dim]TOP SIGNALS[/]")
            for s in profile.top_signals[:6]:
                src_color = {"news": "blue", "finance": "green", "site": "cyan", "social": "magenta"}.get(s["source"], "white")
                console.print(
                    f"  [{src_color}][{s['source'].upper()}][/] "
                    f"{s['content'][:110]}  [dim]w={s['weight']}[/]"
                )

    # Executive summary
    if report.executive_summary:
        console.print()
        console.print(Panel(
            report.executive_summary,
            title="[bold]Executive Summary[/]",
            border_style="green",
        ))

    if report.key_findings:
        console.print()
        console.print("  [bold dim]KEY FINDINGS[/]")
        for f in report.key_findings:
            console.print(f"  [blue]→[/] {f}")

    if report.recommended_actions:
        console.print()
        console.print("  [bold dim]RECOMMENDED ACTIONS[/]")
        for a in report.recommended_actions:
            console.print(f"  [green]✓[/] {a}")

    console.print()
    console.rule("[dim]End of report[/]")


def render_report_plain(report: ArgusReport):
    """Fallback renderer for terminals without Rich."""
    print("\n" + "=" * 60)
    print("ARGUS SENTINEL — INTELLIGENCE REPORT")
    print("=" * 60)
    print(f"Query:      {report.query}")
    print(f"Entities:   {', '.join(report.entities)}")
    print(f"Time:       {report.processing_time_s:.1f}s")
    if report.alert_triggered:
        print("\n*** ALERT TRIGGERED ***")

    for p in report.profiles:
        print(f"\n--- Entity: {p.entity} ---")
        print(f"Composite velocity: {p.velocity_score:.1f}/10")
        print(f"Trajectory slope:   {p.trajectory_slope:+.3f}")
        print(f"Prediction:         {p.prediction}")
        print(f"Confidence:         {p.prediction_confidence:.0%}")
        print(f"Anomaly detected:   {p.anomaly_detected}")
        print("\nTop signals:")
        for s in p.top_signals[:5]:
            print(f"  [{s['source'].upper()}] {s['content'][:100]}")

    if report.executive_summary:
        print(f"\nSummary: {report.executive_summary}")
    print("=" * 60)


def render_report(report: ArgusReport):
    if HAS_RICH:
        render_report_rich(report)
    else:
        render_report_plain(report)


# ------------------------------------------------------------------ #
#  Save report to disk                                                 #
# ------------------------------------------------------------------ #

def save_report(report: ArgusReport, output_dir: str = "./reports"):
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = int(report.timestamp)
    entity_slug = report.entities[0].lower().replace(" ", "_") if report.entities else "unknown"
    filename = f"{output_dir}/argus_{entity_slug}_{ts}.json"
    with open(filename, "w") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)
    if HAS_RICH:
        console.print(f"\n[dim]Report saved to {filename}[/]")
    else:
        print(f"\nReport saved to {filename}")
    return filename


# ------------------------------------------------------------------ #
#  Watch mode (continuous monitoring)                                  #
# ------------------------------------------------------------------ #

async def watch_mode(query: str, interval_minutes: int = 30):
    """
    Continuously re-runs the intelligence pipeline at a set interval.
    Velocity scores will build up over time as the temporal engine
    accumulates historical snapshots.
    """
    orchestrator = ArgusOrchestrator()
    run = 0
    if HAS_RICH:
        console.print(f"[bold blue]ARGUS Watch mode[/] — polling every {interval_minutes}m")
        console.print(f"[dim]Query: {query}[/]\n")

    while True:
        run += 1
        if HAS_RICH:
            console.print(f"[dim]Run #{run} at {time.strftime('%H:%M:%S')}…[/]")
        try:
            report = await orchestrator.run(query)
            render_report(report)
            save_report(report)

            if report.alert_triggered:
                if HAS_RICH:
                    console.print("[bold red]ALERT — Check report above.[/]")
                # In production: send to Slack/email/PagerDuty here
        except Exception as e:
            logger.error("Watch run failed: %s", e)
            if HAS_RICH:
                console.print(f"[red]Run failed: {e}[/]")

        if HAS_RICH:
            console.print(f"[dim]Next run in {interval_minutes} minutes…[/]")
        await asyncio.sleep(interval_minutes * 60)


# ------------------------------------------------------------------ #
#  Main                                                                #
# ------------------------------------------------------------------ #

def main():
    parser = argparse.ArgumentParser(
        description="ARGUS Sentinel — Autonomous Temporal Web Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --query "What is OpenAI planning to launch?"
  python main.py --query "Monitor Stripe M&A signals" --watch --interval 15
  python main.py --dashboard
  python main.py --query "Anthropic vs DeepMind hiring" --output ./my_reports
        """,
    )
    parser.add_argument("--query", "-q", help="Intelligence query (natural language)")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring mode")
    parser.add_argument("--interval", type=int, default=30, help="Watch interval in minutes (default: 30)")
    parser.add_argument("--dashboard", action="store_true", help="Launch the web dashboard")
    parser.add_argument("--output", default="./reports", help="Output directory for reports")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger("argus").setLevel(logging.DEBUG)

    # Validate API keys
    missing = []
    if not CONFIG.bright_data.api_key:
        missing.append("BRIGHT_DATA_API_KEY")
    if not CONFIG.bright_data.serp_key:
        missing.append("BRIGHT_DATA_SERP_KEY")

    if missing:
        if HAS_RICH:
            console.print(f"[red]Missing environment variables: {', '.join(missing)}[/]")
            console.print("[dim]Copy .env.example to .env and fill in your credentials.[/]")
        else:
            print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    # Launch dashboard
    if args.dashboard:
        if HAS_RICH:
            console.print("[bold blue]Starting ARGUS Sentinel dashboard…[/]")
            console.print(f"[dim]Open http://localhost:{CONFIG.dashboard.port}[/]")
        import uvicorn
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "dashboard"))
        from dashboard.app import app
        uvicorn.run(app, host=CONFIG.dashboard.host, port=CONFIG.dashboard.port)
        return

    if not args.query:
        parser.print_help()
        sys.exit(0)

    # Single run or watch mode
    if args.watch:
        asyncio.run(watch_mode(args.query, args.interval))
    else:
        if HAS_RICH:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                progress.add_task("Running ARGUS Sentinel…", total=None)
                report = asyncio.run(ArgusOrchestrator().run(args.query))
        else:
            print("Running ARGUS Sentinel…")
            report = asyncio.run(ArgusOrchestrator().run(args.query))

        render_report(report)
        save_report(report, args.output)


if __name__ == "__main__":
    main()
