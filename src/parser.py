"""Fault-tolerant JSON extraction and normalization of scan results."""

import json
import logging
import re

logger = logging.getLogger(__name__)


def parse_findings(raw_text: str, category: str) -> list[dict]:
    """Extract findings from API response text. Fault-tolerant.

    Handles: clean JSON, markdown-fenced JSON, JSON with preamble,
    malformed JSON, and multiple JSON objects.
    """
    if not raw_text:
        return []

    # Try direct parse
    try:
        data = json.loads(raw_text.strip())
        return normalize_findings(data.get("findings", []), category)
    except (json.JSONDecodeError, AttributeError):
        pass

    # Strip markdown fences
    cleaned = re.sub(r"```json\s*", "", raw_text)
    cleaned = re.sub(r"```\s*", "", cleaned)
    try:
        data = json.loads(cleaned.strip())
        return normalize_findings(data.get("findings", []), category)
    except (json.JSONDecodeError, AttributeError):
        pass

    # Find first JSON object containing "findings"
    for match in re.finditer(r"\{[\s\S]*?\}", raw_text):
        try:
            data = json.loads(match.group())
            if "findings" in data:
                return normalize_findings(data["findings"], category)
        except json.JSONDecodeError:
            continue

    # Find largest JSON object as fallback
    match = re.search(r"\{[\s\S]*\}", raw_text)
    if match:
        try:
            data = json.loads(match.group())
            return normalize_findings(data.get("findings", []), category)
        except json.JSONDecodeError:
            pass

    logger.error(f"Failed to parse findings for {category}: {raw_text[:200]}")
    return []


def normalize_findings(findings: list, category: str) -> list[dict]:
    """Ensure all findings have required fields with defaults."""
    normalized = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        if not f.get("company"):
            continue

        severity = str(f.get("severity", "MEDIUM")).upper()
        if severity not in ("HIGH", "MEDIUM", "LOW"):
            severity = "MEDIUM"

        normalized.append(
            {
                "category": category,
                "company": f.get("company", "Unknown").strip(),
                "executives": _normalize_executives(f.get("executives", [])),
                "summary": f.get("summary", f.get("issue", f.get("context", ""))),
                "severity": severity,
                "source": f.get("source", "Unknown"),
                "source_url": f.get("source_url"),
                "date": f.get("date", "Unknown"),
                "financial_impact": f.get("financial_impact"),
                "vendor": f.get("vendor"),
                "initiative": f.get("initiative"),
            }
        )

    return normalized


def _normalize_executives(executives: list | str | None) -> list[dict]:
    """Normalize executives field to list of {name, title} dicts."""
    if not executives:
        return []
    if isinstance(executives, str):
        return [{"name": executives, "title": ""}]
    result = []
    for ex in executives:
        if isinstance(ex, dict):
            result.append({"name": ex.get("name", ""), "title": ex.get("title", "")})
        elif isinstance(ex, str):
            result.append({"name": ex, "title": ""})
    return result
