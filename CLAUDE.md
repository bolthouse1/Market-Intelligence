# CLAUDE.md — C-Suite Intel Scanner

## Project Overview
Automated daily intelligence scanner that monitors Fortune 500 and large enterprise companies for transformation distress signals. Uses the Anthropic API with web search to find actionable leads for 120VC (120vc.com) outreach.

120VC installs execution leadership systems in Fortune 500 companies — a 25-year framework of daily/weekly rhythms, training, coaching, and embedded consultants. All work must measurably improve customer satisfaction, team satisfaction, and profitability (none at the expense of the other). 98% success rate vs 30% industry average.

For each HIGH severity finding, the scanner auto-generates a personalized outreach draft in 120VC's voice — blunt, anti-consultant-speak, referencing the specific signal.

## Tech Stack
- **Language:** Python 3.10+
- **API:** Anthropic Python SDK (`anthropic`) with web search tool
- **Storage:** SQLite (local), JSON exports
- **Delivery:** HTML email via SMTP (Gmail App Password or SES)
- **Scheduling:** Windows Task Scheduler (primary), cron (secondary)
- **Config:** `.env` file for secrets, `config.yaml` for scan parameters

## Directory Structure
```
C:\Market_Intelligence\
├── CLAUDE.md              # This file
├── SPEC.md                # Full specification
├── config.yaml            # Scan categories, queries, industries, recipients
├── .env                   # ANTHROPIC_API_KEY, SMTP creds (gitignored)
├── .gitignore
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── scanner.py         # Core scan engine — API calls + web search
│   ├── parser.py          # JSON extraction and normalization
│   ├── outreach.py        # Outreach draft generator for HIGH findings
│   ├── briefing.py        # Morning briefing generator + conversation context
│   ├── reporter.py        # HTML report generator
│   ├── emailer.py         # SMTP email delivery
│   ├── storage.py         # SQLite persistence layer
│   ├── dedup.py           # Cross-scan deduplication logic
│   └── cli.py             # CLI entry point (click)
├── templates/
│   └── report.html        # Jinja2 email template
├── data/
│   └── scanner.db         # SQLite database (gitignored)
├── reports/               # Archived HTML reports (gitignored)
├── tests/
│   ├── test_parser.py
│   ├── test_dedup.py
│   └── test_reporter.py
└── scripts/
    ├── install.bat         # One-shot setup: venv + deps + .env scaffold
    ├── run_scan.bat        # Daily scan trigger for Task Scheduler
    └── setup_scheduler.bat # Registers Windows Task Scheduler job
```

## Key Commands
```bash
# Install
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run a full scan
python -m src.cli scan

# Morning briefing — interactive conversation about latest scan
python -m src.cli brief

# Run a single category
python -m src.cli scan --category transformation_failures

# Run a custom query
python -m src.cli query "Siemens Healthineers leadership changes"

# View recent findings
python -m src.cli report --last 7

# Send the latest report via email
python -m src.cli email

# Dry run (scan + report, no email)
python -m src.cli scan --dry-run
```

## Coding Standards
- Type hints on all function signatures
- Docstrings on all public functions (Google style)
- `logging` module throughout — no print statements
- All API calls wrapped in try/except with retry logic (3 attempts, exponential backoff)
- JSON parsing must be fault-tolerant (handle malformed responses gracefully)
- SQLite writes use transactions
- Never store API keys in code — `.env` only

## Important Constraints
- Anthropic API rate limits: add 2-second delay between category scans
- Web search results are real-time — findings will vary run to run
- Deduplication is critical: same company/issue should not appear in consecutive daily reports
- Email must render in Gmail, Outlook, and Apple Mail (inline CSS only, no external stylesheets)
- Total scan time budget: under 5 minutes for all categories

## Testing
- `pytest` for all tests
- Mock the Anthropic API in tests (do not make real API calls in CI)
- Parser tests should cover: valid JSON, JSON in markdown fences, malformed JSON, empty responses
- Dedup tests should cover: exact match, fuzzy company name match, same-issue-different-source
