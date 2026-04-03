# SPEC.md — C-Suite Intel Scanner

## 1. Purpose

Build an automated daily intelligence tool that scans the web for signals that Fortune 500 and large enterprise C-suite leaders are struggling with transformation initiatives. The output is a prioritized daily briefing delivered via email, designed to fuel targeted outreach for 120VC (120vc.com).

120VC installs execution leadership systems in Fortune 500 companies — a 25-year framework of daily/weekly rhythms led by executives with their teams to establish project demand, rationalize it, and plan it. Delivered through training, coaching, and embedded consultants through delivery. All work must measurably improve customer satisfaction, team satisfaction, and profitability — none at the expense of the other (the "120 Standard"). 98% success rate vs 30% industry average.

For each HIGH severity finding, the scanner auto-generates a personalized outreach draft in 120VC's voice — blunt, direct, anti-consultant-speak, referencing the specific distress signal detected.

The tool runs as a scheduled Python script on a Windows workstation. No web server, no cloud deployment, no GUI — just a CLI that scans, stores, deduplicates, generates a report, and emails it.

---

## 2. Architecture

```
[Windows Task Scheduler] → run_scan.bat → python -m src.cli scan
                                              │
                                              ▼
                                        ┌─────────────┐
                                        │  scanner.py  │ ← Anthropic API + web_search tool
                                        └──────┬──────┘
                                               │ raw JSON responses
                                               ▼
                                        ┌─────────────┐
                                        │  parser.py   │ ← fault-tolerant JSON extraction
                                        └──────┬──────┘
                                               │ normalized Finding objects
                                               ▼
                                        ┌─────────────┐
                                        │   dedup.py   │ ← compare against SQLite history
                                        └──────┬──────┘
                                               │ net-new findings only
                                               ▼
                                  ┌─────────────┴─────────────┐
                                  │                           │
                           ┌──────┴──────┐             ┌──────┴──────┐
                           │ storage.py  │             │ reporter.py │
                           │ (SQLite)    │             │ (HTML)      │
                           └─────────────┘             └──────┬──────┘
                                                              │
                                                       ┌──────┴──────┐
                                                       │ emailer.py  │
                                                       │ (SMTP)      │
                                                       └─────────────┘
```

---

## 3. Data Model

### 3.1 Finding (core data object)

```python
@dataclass
class Finding:
    id: str                    # UUID4, generated on creation
    scan_id: str               # UUID4 of the scan run that produced this
    category: str              # one of the CATEGORY_IDS below
    company: str               # company name
    executives: list[dict]     # [{"name": str, "title": str}, ...]
    summary: str               # 1-3 sentence description of the signal
    severity: str              # "HIGH", "MEDIUM", "LOW"
    source: str                # publication or source name
    source_url: str | None     # URL if available
    date: str                  # date string from the source
    financial_impact: str | None  # dollar amounts, charges, etc.
    vendor: str | None         # consulting firm or vendor involved
    initiative: str | None     # name of the transformation program
    raw_json: str              # original JSON from API (for debugging)
    created_at: datetime       # when this finding was stored
    is_new: bool               # True if not a duplicate of a prior finding
    dedup_hash: str            # hash for deduplication (see §6)
```

### 3.2 ScanRun (metadata per execution)

```python
@dataclass
class ScanRun:
    id: str                    # UUID4
    started_at: datetime
    completed_at: datetime | None
    categories_scanned: list[str]
    total_findings: int
    new_findings: int
    errors: list[str]
    report_path: str | None    # path to generated HTML report
    email_sent: bool
```

---

## 4. Scan Categories

Each category has an ID, a display label, and a system prompt. The scanner iterates through enabled categories, making one Anthropic API call per category with the `web_search_20250305` tool enabled.

### CATEGORY_IDS and descriptions:

| ID | Label | Signal Being Detected |
|---|---|---|
| `transformation_failures` | Transformation Failures | Digital transformation delays, cost overruns, failed initiatives, strategic pivots |
| `leadership_turnover` | Leadership Turnover | CIO/CTO/CDO departures, firings, replacements — especially mid-transformation |
| `earnings_distress` | Earnings Distress | Restructuring charges, missed guidance, analyst downgrades citing execution risk |
| `vendor_breakups` | Vendor/Consultant Breakups | Terminated consulting engagements, fired vendors, abandoned implementations |
| `regulatory_penalties` | Regulatory & Compliance | CMS penalties, FDA warnings, audit findings related to technology or data |
| `new_initiative_funding` | New Initiative Funding | Major digital transformation budgets approved, new program launches, big capital allocations for tech/ops overhauls |

### 4.1 Category Configuration (config.yaml)

```yaml
scan_settings:
  inter_category_delay_seconds: 3
  max_retries: 3
  retry_backoff_base: 2
  model: "claude-sonnet-4-20250514"
  max_tokens: 4000

categories:
  transformation_failures:
    enabled: true
    priority: 1
    industries:
      - healthcare
      - medical devices
      - pharma
      - imaging
      - hospital systems
    additional_keywords: []

  leadership_turnover:
    enabled: true
    priority: 2
    industries:
      - healthcare
      - medical devices
      - pharma
    additional_keywords: []

  earnings_distress:
    enabled: true
    priority: 3
    industries:
      - healthcare
      - medical devices
      - pharma
    additional_keywords: []

  vendor_breakups:
    enabled: true
    priority: 4
    industries:
      - healthcare
      - medical devices
    additional_keywords:
      - EHR
      - PACS
      - imaging informatics

  regulatory_penalties:
    enabled: true
    priority: 5
    industries:
      - healthcare
      - hospital systems
      - medical devices
    additional_keywords:
      - CMS
      - FDA
      - HIPAA

  new_initiative_funding:
    enabled: true
    priority: 6
    industries:
      - healthcare
      - medical devices
      - pharma
      - financial services
      - manufacturing
      - energy
    additional_keywords:
      - digital transformation budget
      - capital allocation
      - program launch
      - modernization initiative

email:
  recipients:
    - "darin@bolthouselabs.com"
  from_name: "C-Suite Intel Scanner"
  subject_prefix: "[INTEL]"
  smtp_host: "smtp.gmail.com"
  smtp_port: 587

report:
  archive_days: 90
  timezone: "America/Denver"
```

### 4.2 System Prompts

Each category scan sends a single message to the Anthropic API with the `web_search` tool enabled. The system prompt must instruct the model to:

1. Search the web for signals matching the category
2. Focus on the configured industries (injected from config.yaml)
3. Look for results from the last 30 days
4. Return structured JSON

**Prompt template (populated per category):**

```
You are an executive intelligence analyst. Search the web thoroughly for recent news (last 30 days) about {category_description}.

Focus on these industries: {industries_comma_separated}.
{additional_keywords_line}

Search multiple angles — try company-specific searches, industry publication searches, and general news searches. Cast a wide net.

For each finding, extract:
- company: Company name
- executives: Array of {{name, title}} for involved leaders
- summary: 2-3 sentence description of the signal and why it matters
- severity: HIGH (public failure, major financial impact, C-suite departure) / MEDIUM (delays, budget issues, analyst concern) / LOW (early warning signs, rumored issues)
- source: Publication or source name
- source_url: URL if available
- date: Date of the report
- financial_impact: Dollar amounts, charges, write-downs if mentioned (null if not)
- vendor: Consulting firm or vendor involved (null if not applicable)
- initiative: Name of the specific program or initiative (null if not named)

Return 5-15 findings. Quality over quantity — only include findings with named companies and specific details.

Respond ONLY in valid JSON with this exact structure, no preamble, no markdown fences:
{{"findings": [...]}}
```

---

## 5. Scanner Engine (scanner.py)

### 5.1 API Call Structure

```python
import anthropic
import time
import logging

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

def scan_category(category_id: str, prompt: str, config: dict) -> dict:
    """Execute a single category scan via Anthropic API with web search."""
    for attempt in range(config["max_retries"]):
        try:
            response = client.messages.create(
                model=config["model"],
                max_tokens=config["max_tokens"],
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text blocks from response
            text_content = "\n".join(
                block.text for block in response.content
                if block.type == "text"
            )

            return {"raw": text_content, "category": category_id, "error": None}

        except anthropic.RateLimitError:
            wait = config["retry_backoff_base"] ** (attempt + 1)
            logging.warning(f"Rate limited on {category_id}, waiting {wait}s")
            time.sleep(wait)

        except Exception as e:
            logging.error(f"Scan error for {category_id}: {e}")
            if attempt == config["max_retries"] - 1:
                return {"raw": None, "category": category_id, "error": str(e)}
            time.sleep(config["retry_backoff_base"] ** attempt)
```

### 5.2 Full Scan Orchestration

```python
def run_full_scan(config: dict) -> list[dict]:
    """Run all enabled categories sequentially with delays."""
    results = []
    categories = sorted(
        [(k, v) for k, v in config["categories"].items() if v["enabled"]],
        key=lambda x: x[1]["priority"]
    )

    for category_id, cat_config in categories:
        prompt = build_prompt(category_id, cat_config)
        result = scan_category(category_id, prompt, config["scan_settings"])
        results.append(result)
        time.sleep(config["scan_settings"]["inter_category_delay_seconds"])

    return results
```

---

## 6. Parser (parser.py)

The parser must handle these response formats gracefully:
- Clean JSON
- JSON wrapped in ```json fences
- JSON with preamble text before/after
- Malformed JSON (return empty findings list, log the error)
- Multiple JSON objects (take the first valid one)

```python
import json
import re
import logging

def parse_findings(raw_text: str, category: str) -> list[dict]:
    """Extract findings from API response text. Fault-tolerant."""
    if not raw_text:
        return []

    # Try direct parse
    try:
        data = json.loads(raw_text.strip())
        return normalize_findings(data.get("findings", []), category)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    cleaned = re.sub(r'```json\s*', '', raw_text)
    cleaned = re.sub(r'```\s*', '', cleaned)
    try:
        data = json.loads(cleaned.strip())
        return normalize_findings(data.get("findings", []), category)
    except json.JSONDecodeError:
        pass

    # Find first JSON object
    match = re.search(r'\{[\s\S]*\}', raw_text)
    if match:
        try:
            data = json.loads(match.group())
            return normalize_findings(data.get("findings", []), category)
        except json.JSONDecodeError:
            pass

    logging.error(f"Failed to parse findings for {category}: {raw_text[:200]}")
    return []


def normalize_findings(findings: list, category: str) -> list[dict]:
    """Ensure all findings have required fields with defaults."""
    normalized = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        if not f.get("company"):
            continue  # skip findings without a company name

        normalized.append({
            "category": category,
            "company": f.get("company", "Unknown"),
            "executives": f.get("executives", []),
            "summary": f.get("summary", f.get("issue", f.get("context", ""))),
            "severity": f.get("severity", "MEDIUM").upper(),
            "source": f.get("source", "Unknown"),
            "source_url": f.get("source_url"),
            "date": f.get("date", "Unknown"),
            "financial_impact": f.get("financial_impact"),
            "vendor": f.get("vendor"),
            "initiative": f.get("initiative"),
        })

    return normalized
```

---

## 7. Deduplication (dedup.py)

Dedup prevents the same signal from appearing in consecutive daily reports. The strategy:

1. Generate a `dedup_hash` from: lowercase(company) + lowercase(first 100 chars of summary)
2. Use fuzzy matching on company names (Levenshtein ratio > 0.85 = same company)
3. A finding is "new" if no finding with a matching hash exists in the last 14 days
4. If the same company appears with a genuinely different issue, it should still be surfaced

```python
import hashlib
from difflib import SequenceMatcher

DEDUP_WINDOW_DAYS = 14

def compute_dedup_hash(company: str, summary: str) -> str:
    """Generate a dedup hash from company + summary."""
    key = f"{company.lower().strip()}|{summary.lower().strip()[:100]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def is_duplicate(finding: dict, recent_findings: list[dict]) -> bool:
    """Check if this finding duplicates a recent one."""
    new_hash = compute_dedup_hash(finding["company"], finding["summary"])

    for existing in recent_findings:
        # Exact hash match
        if existing["dedup_hash"] == new_hash:
            return True

        # Fuzzy company match + similar summary
        company_ratio = SequenceMatcher(
            None,
            finding["company"].lower(),
            existing["company"].lower()
        ).ratio()

        if company_ratio > 0.85:
            summary_ratio = SequenceMatcher(
                None,
                finding["summary"].lower()[:150],
                existing["summary"].lower()[:150]
            ).ratio()
            if summary_ratio > 0.6:
                return True

    return False
```

---

## 8. Storage (storage.py)

SQLite database with two tables. Location: `data/scanner.db`.

### Schema

```sql
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    category TEXT NOT NULL,
    company TEXT NOT NULL,
    executives TEXT,          -- JSON string
    summary TEXT,
    severity TEXT,
    source TEXT,
    source_url TEXT,
    date TEXT,
    financial_impact TEXT,
    vendor TEXT,
    initiative TEXT,
    raw_json TEXT,
    dedup_hash TEXT NOT NULL,
    is_new INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (scan_id) REFERENCES scan_runs(id)
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    categories_scanned TEXT,  -- JSON string
    total_findings INTEGER DEFAULT 0,
    new_findings INTEGER DEFAULT 0,
    errors TEXT,              -- JSON string
    report_path TEXT,
    email_sent INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_findings_dedup ON findings(dedup_hash);
CREATE INDEX IF NOT EXISTS idx_findings_created ON findings(created_at);
CREATE INDEX IF NOT EXISTS idx_findings_company ON findings(company);
CREATE INDEX IF NOT EXISTS idx_findings_category ON findings(category);
```

---

## 9. Reporter (reporter.py)

Generates an HTML email report from the day's net-new findings. Uses Jinja2 templating.

### Report Structure

```
╔══════════════════════════════════════════════════╗
║  C-SUITE INTEL BRIEFING — April 2, 2026         ║
║  14 new signals across 5 categories             ║
║  3 HIGH severity findings                       ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  ⚠ HIGH SEVERITY                                 ║
║  ────────────────                                ║
║  [Company] — [Category]                          ║
║  Executives: Name (Title), Name (Title)          ║
║  Summary text...                                 ║
║  Source: [publication] | Date: [date]             ║
║                                                  ║
║  ... more HIGH findings ...                      ║
║                                                  ║
║  📉 MEDIUM SEVERITY                              ║
║  ────────────────                                ║
║  ... medium findings ...                         ║
║                                                  ║
║  📋 LOW SEVERITY                                 ║
║  ────────────────                                ║
║  ... low findings ...                            ║
║                                                  ║
╠══════════════════════════════════════════════════╣
║  Scan completed at 6:00 AM MDT                   ║
║  5 categories scanned | 0 errors                 ║
╚══════════════════════════════════════════════════╝
```

### Template Requirements
- Inline CSS only (Gmail/Outlook compatibility)
- Dark background (#0a0a0f) with light text
- Color-coded severity: HIGH=#ff4444, MEDIUM=#ffaa00, LOW=#44aaff
- Executive names highlighted in purple (#aa88ff)
- Responsive — readable on mobile
- Total report width: 640px max
- Footer with scan metadata and unsubscribe note

### Report Archival
Save each report as `reports/intel_YYYY-MM-DD.html`. Prune reports older than `report.archive_days` from config.

---

## 10. Outreach Draft Generator (outreach.py)

For every HIGH severity finding, a second Anthropic API call generates a personalized outreach draft. This is the feature that turns the scanner from an intelligence report into a revenue tool.

### 10.1 Outreach Mapping

Each signal category maps to a specific 120VC play:

| Signal | Hook Angle | 120VC Service |
|---|---|---|
| `transformation_failures` | "Saw [company] wrote down $X on [initiative]. That's not a technology problem, it's an execution leadership problem." | ELPA / Enterprise Transformation |
| `leadership_turnover` | "New CXOs get 90 days before the board starts asking questions. Most waste it hiring consultants who build dashboards." | Leadership Team Transformation |
| `earnings_distress` | "Restructuring charges mean someone funded theater instead of outcomes." | Kill the Cost Center / Portfolio Services |
| `vendor_breakups` | "Firing [vendor] is step one. Step two is installing the system that makes the next one work." | Managed Services / ELPA |
| `regulatory_penalties` | "Compliance failures are execution failures. The system that delivers on time is the same one that keeps you compliant." | Enterprise Transformation |
| `new_initiative_funding` | "You just got the budget. The 30% success rate says you won't deliver it. We exist to flip those odds." | ELPA |

### 10.2 Draft Generation Prompt

```
You are writing a cold outreach message on behalf of 120VC (120vc.com). 120VC installs execution leadership systems in Fortune 500 companies. 98% success rate vs the 30% industry average.

The 120 Standard: all work must measurably improve customer satisfaction, team satisfaction, and profitability — none at the expense of the other.

Write a short outreach message (4-6 sentences max) for this signal:
- Company: {company}
- Signal: {summary}
- Category: {category_label}
- Executives involved: {executives}
- Financial impact: {financial_impact}

Rules:
- Open with a direct reference to the specific signal. No "I hope this finds you well."
- Be blunt and specific. No consultant-speak, no jargon, no soft-shoe.
- Reference the 120VC service that maps to this signal: {service_name}
- Include one proof point: "98% success rate across Fortune 500 transformations vs the 30% industry average."
- Close with: "Worth a 20-minute readiness conversation?"
- Tone: peer-to-peer executive, like Jason Scott talking to a COO. Direct, confident, zero fluff.

Return ONLY the draft message text, no JSON, no preamble.
```

### 10.3 Draft Data Model

```python
@dataclass
class OutreachDraft:
    id: str                    # UUID4
    finding_id: str            # FK to the finding that triggered this
    company: str
    draft_text: str            # The generated outreach message
    service_hook: str          # Which 120VC service was referenced
    target_role: str           # Suggested recipient role (COO, CIO, etc.)
    created_at: datetime
```

### 10.4 Storage

Add an `outreach_drafts` table:

```sql
CREATE TABLE IF NOT EXISTS outreach_drafts (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    company TEXT NOT NULL,
    draft_text TEXT NOT NULL,
    service_hook TEXT,
    target_role TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (finding_id) REFERENCES findings(id)
);
```

### 10.5 Report Integration

Outreach drafts appear in the email report directly below their associated HIGH severity finding, in a visually distinct block (slightly indented, different background color, copy-friendly formatting).

---

## 11. Emailer (emailer.py)


```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_report(
    html_content: str,
    recipients: list[str],
    subject: str,
    config: dict
) -> bool:
    """Send the HTML report via SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config['from_name']} <{config['smtp_user']}>"
    msg["To"] = ", ".join(recipients)

    # Plain text fallback
    plain = "Your daily C-Suite Intel Briefing is ready. View in an HTML-capable email client."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
        server.starttls()
        server.login(config["smtp_user"], config["smtp_password"])
        server.send_message(msg)

    return True
```

### Email Credentials (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

---

## 12. CLI (cli.py)

Use the `click` library for CLI interface.

### Commands

```
csuite-intel scan [--category CATEGORY] [--dry-run] [--no-email]
    Run a scan. Default: all enabled categories.
    --category: run only one category
    --dry-run: scan + report, skip email
    --no-email: scan + store + report, skip email

csuite-intel query "free text query"
    Run a one-off custom search. Results printed to console and stored in DB
    under category "custom".

csuite-intel report [--last N] [--category CATEGORY]
    Display recent findings. Default: last 24 hours.
    --last N: show last N days
    --category: filter by category

csuite-intel email [--date YYYY-MM-DD]
    Re-send a report for a given date. Default: today.

csuite-intel stats
    Show scan history: total scans, findings by category, top companies.

csuite-intel prune [--days N]
    Delete findings and reports older than N days. Default: 90.
```

---

## 13. Scheduling (Windows Task Scheduler)

### setup_scheduler.bat

```batch
@echo off
:: Register daily scan at 6:00 AM Mountain Time
schtasks /create /tn "CsuiteIntelScan" /tr "C:\Market_Intelligence\scripts\run_scan.bat" /sc daily /st 06:00 /f
echo Task scheduled. Run 'schtasks /query /tn CsuiteIntelScan' to verify.
```

### run_scan.bat

```batch
@echo off
cd /d C:\Market_Intelligence
call .venv\Scripts\activate
python -m src.cli scan
```

---

## 14. Requirements

```
anthropic>=0.40.0
click>=8.1.0
jinja2>=3.1.0
python-dotenv>=1.0.0
pyyaml>=6.0
```

No heavy dependencies. The tool should install and run in under 30 seconds.

---

## 15. Error Handling

| Error | Behavior |
|---|---|
| Anthropic API down | Retry 3x with exponential backoff, log error, continue to next category |
| Rate limit hit | Wait per `retry-after` header or backoff, retry |
| Malformed JSON response | Log raw response, return empty findings for that category, continue |
| SMTP failure | Log error, save report to disk, report can be re-sent via `csuite-intel email` |
| SQLite locked | Retry with 1s delay, max 3 attempts |
| No new findings | Send email with "No new signals today" message (don't skip the email) |

---

## 16. Build Sequence

Implement in this order. Each step should be independently testable.

1. **Project scaffold** — directory structure, requirements.txt, .env.example, config.yaml, .gitignore
2. **storage.py** — SQLite schema creation (findings + outreach_drafts tables), insert/query functions
3. **parser.py** — JSON extraction + normalization, tested with fixture data
4. **dedup.py** — hash generation + fuzzy matching, tested with fixture data
5. **scanner.py** — Anthropic API integration with web search, tested with a single category
6. **outreach.py** — draft generator for HIGH severity findings, maps signal → 120VC service
7. **cli.py** — `scan` command wiring scanner → parser → dedup → storage → outreach
8. **reporter.py** — Jinja2 HTML report with outreach drafts below HIGH findings
9. **emailer.py** — SMTP delivery
10. **cli.py** — remaining commands (report, email, query, stats, prune)
11. **scripts/** — install.bat, run_scan.bat, setup_scheduler.bat
12. **tests/** — full test suite with mocked API responses
13. **End-to-end test** — full scan → store → dedup → outreach → report → email pipeline

---

## 17. Future Enhancements (Not in V1)

- Slack webhook delivery as an alternative to email
- Company watchlist: user-defined list of specific companies to always monitor
- Weekly digest: aggregated weekly summary in addition to daily reports
- CRM integration: push findings into HubSpot or Pipedrive as leads
- Sentiment trend tracking: track whether a company's transformation sentiment is improving or deteriorating over time
- RSS feed output for consumption in Feedly/Inoreader
