"""Tests for reporter.py — HTML report generation."""

from src.reporter import build_subject, render_report


def _make_finding(company="TestCo", severity="HIGH", category="transformation_failures", **kwargs):
    return {
        "id": "test-123",
        "company": company,
        "severity": severity,
        "category": category,
        "summary": "A test finding about transformation failure.",
        "executives": [{"name": "Jane Doe", "title": "CTO"}],
        "source": "Reuters",
        "source_url": "https://example.com",
        "date": "2026-04-01",
        "financial_impact": "$50M write-down",
        "vendor": "Accenture",
        "initiative": "ERP Modernization",
        **kwargs,
    }


def _make_scan_run():
    return {
        "id": "scan-abc",
        "started_at": "2026-04-02T06:00:00",
        "errors": [],
    }


class TestRenderReport:
    def test_renders_html(self):
        findings = [_make_finding()]
        html = render_report(findings, {}, _make_scan_run())
        assert "C-SUITE INTEL BRIEFING" in html
        assert "TestCo" in html

    def test_includes_outreach_draft(self):
        finding = _make_finding()
        drafts = {"test-123": {
            "draft_text": "Your ERP is on fire. We fix that.",
            "target_role": "COO",
        }}
        html = render_report([finding], drafts, _make_scan_run())
        assert "OUTREACH DRAFT" in html
        assert "Your ERP is on fire" in html
        assert "COO" in html

    def test_no_findings_message(self):
        html = render_report([], {}, _make_scan_run())
        assert "No new signals today" in html

    def test_severity_grouping(self):
        findings = [
            _make_finding(company="HighCo", severity="HIGH"),
            _make_finding(company="MedCo", severity="MEDIUM", id="med-1"),
            _make_finding(company="LowCo", severity="LOW", id="low-1"),
        ]
        html = render_report(findings, {}, _make_scan_run())
        assert "HIGH SEVERITY" in html
        assert "MEDIUM SEVERITY" in html
        assert "LOW SEVERITY" in html

    def test_executives_rendered(self):
        html = render_report([_make_finding()], {}, _make_scan_run())
        assert "Jane Doe" in html
        assert "CTO" in html


class TestBuildSubject:
    def test_with_high_findings(self):
        config = {"email": {"subject_prefix": "[INTEL]"}}
        findings = [_make_finding(severity="HIGH"), _make_finding(severity="MEDIUM")]
        subject = build_subject(findings, config)
        assert "[INTEL]" in subject
        assert "1 HIGH" in subject

    def test_no_findings(self):
        config = {"email": {"subject_prefix": "[INTEL]"}}
        subject = build_subject([], config)
        assert "No new signals" in subject

    def test_no_high(self):
        config = {"email": {"subject_prefix": "[INTEL]"}}
        findings = [_make_finding(severity="MEDIUM")]
        subject = build_subject(findings, config)
        assert "HIGH" not in subject
        assert "1 signals" in subject
