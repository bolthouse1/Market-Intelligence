"""SQLite persistence layer for findings and outreach drafts."""

import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "scanner.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scan_runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    categories_scanned TEXT,
    total_findings INTEGER DEFAULT 0,
    new_findings INTEGER DEFAULT 0,
    errors TEXT,
    report_path TEXT,
    email_sent INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    category TEXT NOT NULL,
    company TEXT NOT NULL,
    executives TEXT,
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

CREATE TABLE IF NOT EXISTS conversation_log (
    id TEXT PRIMARY KEY,
    scan_id TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    companies_discussed TEXT,
    categories_discussed TEXT,
    findings_explored TEXT,
    conversation_number INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS andrew_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preference_type TEXT NOT NULL,
    key TEXT NOT NULL,
    value REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(preference_type, key)
);

CREATE INDEX IF NOT EXISTS idx_findings_dedup ON findings(dedup_hash);
CREATE INDEX IF NOT EXISTS idx_findings_created ON findings(created_at);
CREATE INDEX IF NOT EXISTS idx_findings_company ON findings(company);
CREATE INDEX IF NOT EXISTS idx_findings_category ON findings(category);
CREATE INDEX IF NOT EXISTS idx_findings_scan_id ON findings(scan_id);
CREATE INDEX IF NOT EXISTS idx_outreach_finding ON outreach_drafts(finding_id);
CREATE INDEX IF NOT EXISTS idx_convo_scan ON conversation_log(scan_id);
CREATE INDEX IF NOT EXISTS idx_prefs_type ON andrew_preferences(preference_type, key);
"""


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with retry logic."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(3):
        try:
            conn = sqlite3.connect(str(path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn
        except sqlite3.OperationalError as e:
            if attempt < 2:
                logger.warning(f"SQLite locked, retrying in 1s: {e}")
                time.sleep(1)
            else:
                raise


def init_db(db_path: Path | None = None) -> None:
    """Create tables and indexes if they don't exist."""
    conn = _get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        logger.info("Database initialized")
    finally:
        conn.close()


def insert_scan_run(scan_run: dict, db_path: Path | None = None) -> None:
    """Insert a scan run record."""
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO scan_runs (id, started_at, completed_at, categories_scanned,
               total_findings, new_findings, errors, report_path, email_sent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scan_run["id"],
                scan_run["started_at"],
                scan_run.get("completed_at"),
                json.dumps(scan_run.get("categories_scanned", [])),
                scan_run.get("total_findings", 0),
                scan_run.get("new_findings", 0),
                json.dumps(scan_run.get("errors", [])),
                scan_run.get("report_path"),
                int(scan_run.get("email_sent", False)),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_scan_run(scan_id: str, updates: dict, db_path: Path | None = None) -> None:
    """Update fields on a scan run."""
    conn = _get_connection(db_path)
    try:
        set_clauses = []
        values = []
        for key, value in updates.items():
            set_clauses.append(f"{key} = ?")
            if key in ("categories_scanned", "errors"):
                values.append(json.dumps(value))
            elif key == "email_sent":
                values.append(int(value))
            else:
                values.append(value)
        values.append(scan_id)
        conn.execute(
            f"UPDATE scan_runs SET {', '.join(set_clauses)} WHERE id = ?", values
        )
        conn.commit()
    finally:
        conn.close()


def insert_finding(finding: dict, db_path: Path | None = None) -> None:
    """Insert a single finding."""
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO findings (id, scan_id, category, company, executives,
               summary, severity, source, source_url, date, financial_impact,
               vendor, initiative, raw_json, dedup_hash, is_new, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                finding["id"],
                finding["scan_id"],
                finding["category"],
                finding["company"],
                json.dumps(finding.get("executives", [])),
                finding.get("summary", ""),
                finding.get("severity", "MEDIUM"),
                finding.get("source", "Unknown"),
                finding.get("source_url"),
                finding.get("date"),
                finding.get("financial_impact"),
                finding.get("vendor"),
                finding.get("initiative"),
                finding.get("raw_json", ""),
                finding["dedup_hash"],
                int(finding.get("is_new", True)),
                finding["created_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def insert_outreach_draft(draft: dict, db_path: Path | None = None) -> None:
    """Insert an outreach draft."""
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO outreach_drafts (id, finding_id, company, draft_text,
               service_hook, target_role, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                draft["id"],
                draft["finding_id"],
                draft["company"],
                draft["draft_text"],
                draft.get("service_hook"),
                draft.get("target_role"),
                draft["created_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_recent_findings(days: int = 14, db_path: Path | None = None) -> list[dict]:
    """Get findings from the last N days for dedup comparison."""
    conn = _get_connection(db_path)
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = conn.execute(
            "SELECT * FROM findings WHERE created_at >= ? ORDER BY created_at DESC",
            (cutoff,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_findings_by_scan(scan_id: str, db_path: Path | None = None) -> list[dict]:
    """Get all findings for a specific scan run."""
    conn = _get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM findings WHERE scan_id = ? AND is_new = 1 ORDER BY severity, company",
            (scan_id,),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["executives"] = json.loads(d["executives"]) if d["executives"] else []
            results.append(d)
        return results
    finally:
        conn.close()


def get_outreach_drafts_by_scan(scan_id: str, db_path: Path | None = None) -> list[dict]:
    """Get outreach drafts for findings in a specific scan."""
    conn = _get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT od.* FROM outreach_drafts od
               JOIN findings f ON od.finding_id = f.id
               WHERE f.scan_id = ?
               ORDER BY od.created_at""",
            (scan_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_findings_by_date_range(
    start: str, end: str, category: str | None = None, db_path: Path | None = None
) -> list[dict]:
    """Get findings within a date range, optionally filtered by category."""
    conn = _get_connection(db_path)
    try:
        query = "SELECT * FROM findings WHERE created_at >= ? AND created_at <= ? AND is_new = 1"
        params: list[Any] = [start, end]
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY severity, company"
        rows = conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["executives"] = json.loads(d["executives"]) if d["executives"] else []
            results.append(d)
        return results
    finally:
        conn.close()


def get_scan_stats(db_path: Path | None = None) -> dict:
    """Get aggregate scan statistics."""
    conn = _get_connection(db_path)
    try:
        total_scans = conn.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
        total_findings = conn.execute("SELECT COUNT(*) FROM findings WHERE is_new = 1").fetchone()[0]

        by_category = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM findings WHERE is_new = 1 GROUP BY category ORDER BY cnt DESC"
        ).fetchall()

        top_companies = conn.execute(
            "SELECT company, COUNT(*) as cnt FROM findings WHERE is_new = 1 GROUP BY company ORDER BY cnt DESC LIMIT 20"
        ).fetchall()

        return {
            "total_scans": total_scans,
            "total_findings": total_findings,
            "by_category": {row["category"]: row["cnt"] for row in by_category},
            "top_companies": {row["company"]: row["cnt"] for row in top_companies},
        }
    finally:
        conn.close()


def prune_old_data(days: int = 90, db_path: Path | None = None) -> int:
    """Delete findings and scan runs older than N days. Returns count deleted."""
    conn = _get_connection(db_path)
    try:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        # Delete outreach drafts for old findings
        conn.execute(
            "DELETE FROM outreach_drafts WHERE finding_id IN (SELECT id FROM findings WHERE created_at < ?)",
            (cutoff,),
        )

        cursor = conn.execute("DELETE FROM findings WHERE created_at < ?", (cutoff,))
        deleted = cursor.rowcount

        conn.execute("DELETE FROM scan_runs WHERE started_at < ?", (cutoff,))
        conn.commit()
        logger.info(f"Pruned {deleted} findings older than {days} days")
        return deleted
    finally:
        conn.close()


def get_conversation_count(db_path: Path | None = None) -> int:
    """Get total number of briefing conversations held."""
    conn = _get_connection(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]
    finally:
        conn.close()


def log_conversation(convo: dict, db_path: Path | None = None) -> None:
    """Log a completed briefing conversation."""
    conn = _get_connection(db_path)
    try:
        # Get next conversation number
        count = conn.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]
        conn.execute(
            """INSERT INTO conversation_log (id, scan_id, started_at, ended_at,
               companies_discussed, categories_discussed, findings_explored,
               conversation_number)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                convo["id"],
                convo.get("scan_id"),
                convo["started_at"],
                convo.get("ended_at"),
                json.dumps(convo.get("companies_discussed", [])),
                json.dumps(convo.get("categories_discussed", [])),
                json.dumps(convo.get("findings_explored", [])),
                count + 1,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_preference(
    pref_type: str, key: str, value: float, db_path: Path | None = None
) -> None:
    """Upsert a preference score (e.g., category interest, company interest)."""
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO andrew_preferences (preference_type, key, value, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(preference_type, key)
               DO UPDATE SET value = value + ?, updated_at = ?""",
            (pref_type, key, value, datetime.utcnow().isoformat(),
             value, datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_preferences(pref_type: str | None = None, db_path: Path | None = None) -> list[dict]:
    """Get preference scores, optionally filtered by type."""
    conn = _get_connection(db_path)
    try:
        if pref_type:
            rows = conn.execute(
                "SELECT * FROM andrew_preferences WHERE preference_type = ? ORDER BY value DESC",
                (pref_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM andrew_preferences ORDER BY preference_type, value DESC"
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_latest_scan_id(db_path: Path | None = None) -> str | None:
    """Get the most recent scan run ID."""
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM scan_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()
