"""CLI entry point for the C-Suite Intel Scanner."""

import json
import logging
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv

from . import briefing, dedup, emailer, outreach, parser, reporter, scanner, storage

load_dotenv()

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _load_config() -> dict:
    """Load config.yaml from project root."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    if not config_path.exists():
        click.echo(f"Error: config.yaml not found at {config_path}", err=True)
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """120VC C-Suite Intel Scanner — find transformation distress signals."""
    _setup_logging(verbose)


@cli.command()
@click.option("--category", "-c", default=None, help="Run only one category")
@click.option("--dry-run", is_flag=True, help="Scan + report, skip email")
@click.option("--no-email", is_flag=True, help="Scan + store + report, skip email")
def scan(category: str | None, dry_run: bool, no_email: bool) -> None:
    """Run a scan across all enabled categories (or one specific category)."""
    logger = logging.getLogger("cli.scan")
    config = _load_config()
    storage.init_db()

    # Create scan run
    scan_id = str(uuid.uuid4())
    scan_run = {
        "id": scan_id,
        "started_at": datetime.utcnow().isoformat(),
        "categories_scanned": [],
        "total_findings": 0,
        "new_findings": 0,
        "errors": [],
    }
    storage.insert_scan_run(scan_run)

    # Filter categories if specified
    if category:
        if category not in config["categories"]:
            click.echo(f"Unknown category: {category}", err=True)
            click.echo(f"Available: {', '.join(config['categories'].keys())}", err=True)
            return
        scan_config = {
            **config,
            "categories": {category: config["categories"][category]},
        }
    else:
        scan_config = config

    # Run scans
    click.echo(f"Starting scan [{scan_id[:8]}]...")
    results = scanner.run_full_scan(scan_config)

    # Parse and dedup
    recent = storage.get_recent_findings(days=dedup.DEDUP_WINDOW_DAYS)
    all_findings = []
    errors = []
    categories_scanned = []

    for result in results:
        categories_scanned.append(result["category"])
        if result["error"]:
            errors.append(f"{result['category']}: {result['error']}")
            logger.error(f"Scan error: {result['category']}: {result['error']}")
            continue

        findings = parser.parse_findings(result["raw"], result["category"])
        logger.info(f"{result['category']}: parsed {len(findings)} findings")
        all_findings.extend(findings)

    # Dedup
    new_findings = dedup.deduplicate_findings(all_findings, recent)
    click.echo(f"Found {len(all_findings)} total, {len(new_findings)} new after dedup")

    # Store findings
    for finding in all_findings:
        finding["id"] = str(uuid.uuid4())
        finding["scan_id"] = scan_id
        finding["created_at"] = datetime.utcnow().isoformat()
        finding["raw_json"] = json.dumps(finding)
        storage.insert_finding(finding)

    # Generate outreach drafts for HIGH severity new findings
    drafts = outreach.generate_outreach_drafts(new_findings, config)
    for draft in drafts:
        storage.insert_outreach_draft(draft)
    if drafts:
        click.echo(f"Generated {len(drafts)} outreach drafts")

    # Build report
    drafts_by_finding = {d["finding_id"]: d for d in drafts}
    report_html = reporter.render_report(new_findings, drafts_by_finding, scan_run)
    report_path = reporter.save_report(report_html)
    click.echo(f"Report saved: {report_path}")

    # Update scan run
    storage.update_scan_run(scan_id, {
        "completed_at": datetime.utcnow().isoformat(),
        "categories_scanned": categories_scanned,
        "total_findings": len(all_findings),
        "new_findings": len(new_findings),
        "errors": errors,
        "report_path": str(report_path) if report_path else None,
    })

    # Send email
    if not dry_run and not no_email:
        try:
            subject = reporter.build_subject(new_findings, config)
            emailer.send_report(report_html, config["email"]["recipients"], subject, config["email"])
            storage.update_scan_run(scan_id, {"email_sent": True})
            click.echo("Email sent!")
        except Exception as e:
            logger.error(f"Email failed: {e}")
            click.echo(f"Email failed: {e}. Report saved to {report_path}", err=True)

    click.echo("Scan complete.")


@cli.command()
def brief() -> None:
    """Launch the morning briefing — conversational review of the latest scan."""
    storage.init_db()

    scan_id = storage.get_latest_scan_id()
    if not scan_id:
        click.echo("No scans found. Run a scan first: python -m src.cli scan")
        return

    # Generate the briefing
    click.echo("Loading today's intel...\n")
    brief_text = briefing.generate_briefing(scan_id)
    click.echo(brief_text)
    click.echo()

    # Build context for follow-up conversation
    context = briefing.build_context_for_conversation(scan_id)

    # Log the conversation start
    convo_id = str(uuid.uuid4())
    storage.log_conversation({
        "id": convo_id,
        "scan_id": scan_id,
        "started_at": datetime.utcnow().isoformat(),
        "companies_discussed": [],
        "categories_discussed": [],
        "findings_explored": [],
    })

    # Interactive conversation loop
    client = __import__("anthropic").Anthropic()
    messages = [
        {"role": "assistant", "content": brief_text},
    ]

    companies_discussed = []
    categories_discussed = []

    while True:
        try:
            user_input = click.prompt("Andrew", prompt_suffix=" > ", default="", show_default=False)
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input.strip():
            continue
        if user_input.strip().lower() in ("quit", "exit", "done", "bye", "later"):
            # Generate sign-off
            messages.append({"role": "user", "content": user_input})
            messages.append({"role": "user", "content": "(Andrew is wrapping up. Give a short sign-off and ask ONE question about how you can improve — keep it real, one sentence.)"})
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                system=context,
                messages=messages,
            )
            sign_off = "\n".join(b.text for b in response.content if b.type == "text").strip()
            click.echo(f"\n{sign_off}\n")

            # Update conversation log
            storage.log_conversation({
                "id": str(uuid.uuid4()),
                "scan_id": scan_id,
                "started_at": datetime.utcnow().isoformat(),
                "ended_at": datetime.utcnow().isoformat(),
                "companies_discussed": companies_discussed,
                "categories_discussed": categories_discussed,
                "findings_explored": [],
            })

            # Update preferences based on what was discussed
            for company in companies_discussed:
                storage.update_preference("company_interest", company, 1.0)
            for cat in categories_discussed:
                storage.update_preference("category_interest", cat, 1.0)

            break

        messages.append({"role": "user", "content": user_input})

        # Track what Andrew is asking about
        findings = storage.get_findings_by_scan(scan_id)
        for f in findings:
            if f["company"].lower() in user_input.lower():
                if f["company"] not in companies_discussed:
                    companies_discussed.append(f["company"])
                if f["category"] not in categories_discussed:
                    categories_discussed.append(f["category"])

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=context,
            messages=messages,
        )

        reply = "\n".join(b.text for b in response.content if b.type == "text").strip()
        messages.append({"role": "assistant", "content": reply})
        click.echo(f"\n{reply}\n")


@cli.command()
@click.argument("query_text")
def query(query_text: str) -> None:
    """Run a one-off custom search query."""
    config = _load_config()
    storage.init_db()

    click.echo(f"Searching: {query_text}")
    result = scanner.run_custom_query(query_text, config)

    if result["error"]:
        click.echo(f"Error: {result['error']}", err=True)
        return

    findings = parser.parse_findings(result["raw"], "custom")
    click.echo(f"Found {len(findings)} results:\n")

    for f in findings:
        severity_icon = {"HIGH": "!!!", "MEDIUM": " ! ", "LOW": "   "}.get(f["severity"], "   ")
        click.echo(f"[{severity_icon}] {f['company']}")
        click.echo(f"     {f['summary']}")
        if f.get("executives"):
            execs = ", ".join(f"{e['name']} ({e['title']})" for e in f["executives"] if e.get("name"))
            if execs:
                click.echo(f"     Executives: {execs}")
        if f.get("source"):
            click.echo(f"     Source: {f['source']}")
        click.echo()


@cli.command()
@click.option("--last", "-l", default=1, help="Show last N days of findings")
@click.option("--category", "-c", default=None, help="Filter by category")
def report(last: int, category: str | None) -> None:
    """Display recent findings."""
    config = _load_config()
    storage.init_db()

    end = datetime.utcnow().isoformat()
    start = (datetime.utcnow() - timedelta(days=last)).isoformat()
    findings = storage.get_findings_by_date_range(start, end, category)

    if not findings:
        click.echo(f"No findings in the last {last} day(s).")
        return

    click.echo(f"\n{'='*60}")
    click.echo(f"  FINDINGS — Last {last} day(s)  ({len(findings)} results)")
    click.echo(f"{'='*60}\n")

    for f in findings:
        severity_icon = {"HIGH": "!!!", "MEDIUM": " ! ", "LOW": "   "}.get(f.get("severity", ""), "   ")
        click.echo(f"[{severity_icon}] {f['company']} — {f['category']}")
        click.echo(f"     {f.get('summary', '')}")
        click.echo()


@cli.command()
@click.option("--date", "-d", default=None, help="Re-send report for YYYY-MM-DD (default: today)")
def email(date: str | None) -> None:
    """Re-send a report for a given date."""
    config = _load_config()

    if date:
        report_path = Path(__file__).parent.parent / "reports" / f"intel_{date}.html"
    else:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        report_path = Path(__file__).parent.parent / "reports" / f"intel_{today}.html"

    if not report_path.exists():
        click.echo(f"No report found at {report_path}", err=True)
        return

    html_content = report_path.read_text(encoding="utf-8")
    subject = f"{config['email']['subject_prefix']} Daily Intel Briefing — {report_path.stem.replace('intel_', '')}"

    try:
        emailer.send_report(html_content, config["email"]["recipients"], subject, config["email"])
        click.echo("Email sent!")
    except Exception as e:
        click.echo(f"Email failed: {e}", err=True)


@cli.command()
def stats() -> None:
    """Show scan history and statistics."""
    storage.init_db()
    s = storage.get_scan_stats()

    click.echo(f"\n{'='*40}")
    click.echo(f"  SCAN STATISTICS")
    click.echo(f"{'='*40}")
    click.echo(f"  Total scans:    {s['total_scans']}")
    click.echo(f"  Total findings: {s['total_findings']}")
    click.echo()

    if s["by_category"]:
        click.echo("  By Category:")
        for cat, count in s["by_category"].items():
            click.echo(f"    {cat}: {count}")
        click.echo()

    if s["top_companies"]:
        click.echo("  Top Companies:")
        for company, count in list(s["top_companies"].items())[:10]:
            click.echo(f"    {company}: {count}")
    click.echo()


@cli.command()
@click.option("--days", "-d", default=90, help="Delete data older than N days")
def prune(days: int) -> None:
    """Delete old findings and reports."""
    storage.init_db()
    deleted = storage.prune_old_data(days)
    click.echo(f"Pruned {deleted} findings older than {days} days.")

    # Prune old report files
    reports_dir = Path(__file__).parent.parent / "reports"
    if reports_dir.exists():
        cutoff = datetime.utcnow() - timedelta(days=days)
        pruned_files = 0
        for f in reports_dir.glob("intel_*.html"):
            try:
                date_str = f.stem.replace("intel_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    f.unlink()
                    pruned_files += 1
            except ValueError:
                continue
        if pruned_files:
            click.echo(f"Pruned {pruned_files} old report files.")


if __name__ == "__main__":
    cli()
