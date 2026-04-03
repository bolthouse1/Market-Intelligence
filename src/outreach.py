"""Outreach draft generator — creates personalized cold outreach for HIGH severity findings."""

import logging
import uuid
from datetime import datetime

import anthropic

logger = logging.getLogger(__name__)

OUTREACH_HOOKS = {
    "transformation_failures": (
        "Saw {company} is dealing with {summary_short}. "
        "That's not a technology problem — it's an execution leadership problem."
    ),
    "leadership_turnover": (
        "New CXOs get 90 days before the board starts asking questions. "
        "Most waste it hiring consultants who build dashboards."
    ),
    "earnings_distress": (
        "Restructuring charges at {company} mean someone funded theater instead of outcomes."
    ),
    "vendor_breakups": (
        "Firing {vendor_or_their_vendor} is step one. "
        "Step two is installing the system that makes the next one work."
    ),
    "regulatory_penalties": (
        "Compliance failures are execution failures. "
        "The system that delivers on time is the same one that keeps you compliant."
    ),
    "new_initiative_funding": (
        "{company} just got the budget for {initiative_or_transformation}. "
        "The 30% industry success rate says it won't get delivered. We exist to flip those odds."
    ),
}

TARGET_ROLES = {
    "transformation_failures": "COO or Chief Transformation Officer",
    "leadership_turnover": "Incoming CXO or CEO",
    "earnings_distress": "CFO or COO",
    "vendor_breakups": "CIO/CTO or COO",
    "regulatory_penalties": "COO or Chief Compliance Officer",
    "new_initiative_funding": "Program Sponsor (CFO, COO, or Division President)",
}

DRAFT_PROMPT = """You are writing a cold outreach message on behalf of 120VC (120vc.com). 120VC installs execution leadership systems in Fortune 500 companies — a 25-year framework of daily/weekly rhythms, training, coaching, and embedded consultants through delivery. 98% success rate vs the 30% industry average.

The 120 Standard: all work must measurably improve customer satisfaction, team satisfaction, and profitability — none at the expense of the other.

Write a short outreach message (4-6 sentences max) for this signal:
- Company: {company}
- Signal: {summary}
- Category: {category_label}
- Executives involved: {executives}
- Financial impact: {financial_impact}
- Vendor involved: {vendor}
- Initiative: {initiative}
- Suggested 120VC service: {service_name}
- Hook angle: {hook}

Rules:
- Open with a direct reference to the specific signal. No "I hope this finds you well."
- Be blunt and specific. No consultant-speak, no jargon, no soft-shoe.
- Reference the specific 120VC capability that maps to this signal.
- Include one proof point: "98% success rate across Fortune 500 transformations vs the 30% industry average."
- Close with: "Worth a 20-minute readiness conversation?"
- Tone: peer-to-peer executive, like Jason Scott talking to a COO. Direct, confident, zero fluff.
- Do NOT use bullet points or formatting. Just a clean paragraph.

Return ONLY the draft message text. No JSON, no preamble, no signature block."""


def generate_outreach_drafts(
    findings: list[dict], config: dict
) -> list[dict]:
    """Generate outreach drafts for all HIGH severity findings.

    Args:
        findings: List of HIGH severity finding dicts.
        config: Full config dict with scan_settings and categories.

    Returns:
        List of outreach draft dicts ready for storage.
    """
    high_findings = [f for f in findings if f.get("severity") == "HIGH"]
    if not high_findings:
        logger.info("No HIGH severity findings — skipping outreach generation")
        return []

    client = anthropic.Anthropic()
    model = config.get("scan_settings", {}).get("model", "claude-sonnet-4-20250514")
    drafts = []

    for finding in high_findings:
        try:
            draft = _generate_single_draft(finding, config, client, model)
            if draft:
                drafts.append(draft)
        except Exception as e:
            logger.error(f"Failed to generate outreach for {finding['company']}: {e}")

    logger.info(f"Generated {len(drafts)} outreach drafts")
    return drafts


def _generate_single_draft(
    finding: dict, config: dict, client: anthropic.Anthropic, model: str
) -> dict | None:
    """Generate a single outreach draft for one finding."""
    category = finding.get("category", "transformation_failures")
    cat_config = config.get("categories", {}).get(category, {})
    service_name = cat_config.get("outreach_service", "ELPA")
    category_label = cat_config.get("label", category)

    # Build the hook
    hook_template = OUTREACH_HOOKS.get(category, OUTREACH_HOOKS["transformation_failures"])
    hook = hook_template.format(
        company=finding["company"],
        summary_short=finding["summary"][:80],
        vendor_or_their_vendor=finding.get("vendor") or "their vendor",
        initiative_or_transformation=finding.get("initiative") or "a major transformation",
    )

    # Format executives
    executives = finding.get("executives", [])
    if isinstance(executives, list):
        exec_str = ", ".join(
            f"{e.get('name', '')} ({e.get('title', '')})" for e in executives if e.get("name")
        ) or "Not specified"
    else:
        exec_str = str(executives)

    prompt = DRAFT_PROMPT.format(
        company=finding["company"],
        summary=finding["summary"],
        category_label=category_label,
        executives=exec_str,
        financial_impact=finding.get("financial_impact") or "Not specified",
        vendor=finding.get("vendor") or "Not specified",
        initiative=finding.get("initiative") or "Not specified",
        service_name=service_name,
        hook=hook,
    )

    logger.info(f"Generating outreach draft for {finding['company']}...")
    response = client.messages.create(
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    draft_text = "\n".join(
        block.text for block in response.content if block.type == "text"
    ).strip()

    if not draft_text:
        logger.warning(f"Empty outreach draft for {finding['company']}")
        return None

    return {
        "id": str(uuid.uuid4()),
        "finding_id": finding["id"],
        "company": finding["company"],
        "draft_text": draft_text,
        "service_hook": service_name,
        "target_role": TARGET_ROLES.get(category, "COO"),
        "created_at": datetime.utcnow().isoformat(),
    }
