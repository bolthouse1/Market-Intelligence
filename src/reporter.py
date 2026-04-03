"""HTML report generator using Jinja2 templating."""

import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
REPORTS_DIR = Path(__file__).parent.parent / "reports"

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def render_report(
    findings: list[dict],
    drafts_by_finding: dict[str, dict],
    scan_run: dict,
) -> str:
    """Render an HTML report from findings and outreach drafts.

    Args:
        findings: List of net-new finding dicts.
        drafts_by_finding: Dict mapping finding_id -> outreach draft dict.
        scan_run: Scan run metadata dict.

    Returns:
        Rendered HTML string.
    """
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("report.html")

    # Sort by severity
    sorted_findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.get("severity", "LOW"), 2))

    # Group by severity
    high = [f for f in sorted_findings if f.get("severity") == "HIGH"]
    medium = [f for f in sorted_findings if f.get("severity") == "MEDIUM"]
    low = [f for f in sorted_findings if f.get("severity") == "LOW"]

    # Count categories
    categories_count = len(set(f.get("category", "") for f in findings))

    now = datetime.utcnow()

    html = template.render(
        findings=sorted_findings,
        high_findings=high,
        medium_findings=medium,
        low_findings=low,
        drafts_by_finding=drafts_by_finding,
        scan_run=scan_run,
        total_findings=len(findings),
        high_count=len(high),
        categories_count=categories_count,
        report_date=now.strftime("%B %d, %Y"),
        scan_time=now.strftime("%I:%M %p UTC"),
    )

    return html


def save_report(html: str) -> Path:
    """Save report HTML to the reports directory."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    path = REPORTS_DIR / f"intel_{today}.html"
    path.write_text(html, encoding="utf-8")
    logger.info(f"Report saved to {path}")
    return path


def build_subject(findings: list[dict], config: dict) -> str:
    """Build the email subject line."""
    prefix = config.get("email", {}).get("subject_prefix", "[INTEL]")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    high_count = sum(1 for f in findings if f.get("severity") == "HIGH")

    if not findings:
        return f"{prefix} No new signals — {today}"
    elif high_count:
        return f"{prefix} {len(findings)} signals ({high_count} HIGH) — {today}"
    else:
        return f"{prefix} {len(findings)} signals — {today}"
