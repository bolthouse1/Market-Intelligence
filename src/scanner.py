"""Core scan engine — Anthropic API calls with web search tool."""

import logging
import time

import anthropic

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are an executive intelligence analyst working for 120VC, a firm that installs execution leadership systems in Fortune 500 companies. Search the web thoroughly for recent news (last 30 days) about {category_description}.

Focus on these industries: {industries}.
{additional_keywords_line}

Search multiple angles — try company-specific searches, industry publication searches, and general news searches. Cast a wide net. Look for Fortune 500 and large enterprise companies specifically.

For each finding, extract:
- company: Company name (full legal name preferred)
- executives: Array of {{"name": "Full Name", "title": "Their Title"}} for involved leaders
- summary: 2-3 sentence description of the signal and why it matters for execution leadership
- severity: HIGH (public failure, major financial impact, C-suite departure, >$50M at stake) / MEDIUM (delays, budget issues, analyst concern) / LOW (early warning signs, rumored issues)
- source: Publication or source name
- source_url: URL if available
- date: Date of the report
- financial_impact: Dollar amounts, charges, write-downs if mentioned (null if not)
- vendor: Consulting firm or vendor involved (null if not applicable)
- initiative: Name of the specific program or initiative (null if not named)

Return 5-15 findings. Quality over quantity — only include findings with named companies and specific details. Prioritize findings where a company clearly needs execution leadership help.

Respond ONLY in valid JSON with this exact structure, no preamble, no markdown fences:
{{"findings": [...]}}"""


def build_prompt(category_id: str, cat_config: dict) -> str:
    """Build the scan prompt for a category from config."""
    industries = ", ".join(cat_config.get("industries", []))
    keywords = cat_config.get("additional_keywords", [])
    keywords_line = (
        f"Also look for mentions of: {', '.join(keywords)}" if keywords else ""
    )

    return PROMPT_TEMPLATE.format(
        category_description=cat_config.get("description", category_id),
        industries=industries,
        additional_keywords_line=keywords_line,
    )


def scan_category(
    category_id: str, prompt: str, scan_settings: dict
) -> dict:
    """Execute a single category scan via Anthropic API with web search.

    Returns dict with keys: raw, category, error.
    """
    client = anthropic.Anthropic()
    max_retries = scan_settings.get("max_retries", 3)
    backoff_base = scan_settings.get("retry_backoff_base", 2)
    model = scan_settings.get("model", "claude-sonnet-4-20250514")
    max_tokens = scan_settings.get("max_tokens", 4000)

    for attempt in range(max_retries):
        try:
            logger.info(f"Scanning {category_id} (attempt {attempt + 1}/{max_retries})")
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
                messages=[{"role": "user", "content": prompt}],
            )

            text_content = "\n".join(
                block.text for block in response.content if block.type == "text"
            )

            logger.info(f"Scan complete for {category_id}: {len(text_content)} chars")
            return {"raw": text_content, "category": category_id, "error": None}

        except anthropic.RateLimitError as e:
            wait = backoff_base ** (attempt + 1)
            logger.warning(f"Rate limited on {category_id}, waiting {wait}s: {e}")
            time.sleep(wait)

        except anthropic.APIError as e:
            logger.error(f"API error for {category_id}: {e}")
            if attempt == max_retries - 1:
                return {"raw": None, "category": category_id, "error": str(e)}
            time.sleep(backoff_base ** attempt)

        except Exception as e:
            logger.error(f"Unexpected error for {category_id}: {e}")
            if attempt == max_retries - 1:
                return {"raw": None, "category": category_id, "error": str(e)}
            time.sleep(backoff_base ** attempt)

    return {"raw": None, "category": category_id, "error": "Max retries exceeded"}


def run_full_scan(config: dict) -> list[dict]:
    """Run all enabled categories sequentially with delays."""
    results = []
    categories = sorted(
        [(k, v) for k, v in config["categories"].items() if v.get("enabled", True)],
        key=lambda x: x[1].get("priority", 99),
    )

    delay = config.get("scan_settings", {}).get("inter_category_delay_seconds", 3)
    scan_settings = config.get("scan_settings", {})

    for i, (category_id, cat_config) in enumerate(categories):
        prompt = build_prompt(category_id, cat_config)
        result = scan_category(category_id, prompt, scan_settings)
        results.append(result)

        if i < len(categories) - 1:
            logger.info(f"Waiting {delay}s before next category...")
            time.sleep(delay)

    return results


def run_custom_query(query: str, config: dict) -> dict:
    """Run a one-off custom search query."""
    prompt = f"""You are an executive intelligence analyst working for 120VC. Search the web for: {query}

For each finding, extract:
- company: Company name
- executives: Array of {{"name": "Full Name", "title": "Their Title"}} for involved leaders
- summary: 2-3 sentence description
- severity: HIGH / MEDIUM / LOW
- source: Publication or source name
- source_url: URL if available
- date: Date of the report
- financial_impact: Dollar amounts if mentioned (null if not)
- vendor: Vendor involved (null if not applicable)
- initiative: Name of specific program (null if not named)

Return findings with named companies and specific details only.

Respond ONLY in valid JSON: {{"findings": [...]}}"""

    scan_settings = config.get("scan_settings", {})
    return scan_category("custom", prompt, scan_settings)
