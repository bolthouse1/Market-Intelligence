"""Cross-scan deduplication logic using hash + fuzzy matching."""

import hashlib
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

DEDUP_WINDOW_DAYS = 14


def compute_dedup_hash(company: str, summary: str) -> str:
    """Generate a dedup hash from company + summary prefix."""
    key = f"{company.lower().strip()}|{summary.lower().strip()[:100]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def is_duplicate(finding: dict, recent_findings: list[dict]) -> bool:
    """Check if this finding duplicates a recent one.

    Uses exact hash match first, then falls back to fuzzy matching
    on company name + summary similarity.
    """
    new_hash = compute_dedup_hash(finding["company"], finding["summary"])

    for existing in recent_findings:
        # Exact hash match
        if existing.get("dedup_hash") == new_hash:
            logger.debug(f"Exact dedup match: {finding['company']}")
            return True

        # Fuzzy company match + similar summary
        company_ratio = SequenceMatcher(
            None, finding["company"].lower(), existing["company"].lower()
        ).ratio()

        if company_ratio > 0.85:
            summary_ratio = SequenceMatcher(
                None,
                finding["summary"].lower()[:150],
                existing.get("summary", "").lower()[:150],
            ).ratio()
            if summary_ratio > 0.6:
                logger.debug(
                    f"Fuzzy dedup match: {finding['company']} ~ {existing['company']} "
                    f"(company={company_ratio:.2f}, summary={summary_ratio:.2f})"
                )
                return True

    return False


def deduplicate_findings(
    findings: list[dict], recent_findings: list[dict]
) -> list[dict]:
    """Filter a list of findings, returning only net-new ones.

    Also sets dedup_hash and is_new on each finding.
    """
    new_findings = []
    for finding in findings:
        finding["dedup_hash"] = compute_dedup_hash(
            finding["company"], finding["summary"]
        )
        if is_duplicate(finding, recent_findings):
            finding["is_new"] = False
            logger.info(f"Duplicate skipped: {finding['company']} — {finding['summary'][:60]}")
        else:
            finding["is_new"] = True
            new_findings.append(finding)
            # Add to recent so we also dedup within this batch
            recent_findings.append(finding)

    return new_findings
