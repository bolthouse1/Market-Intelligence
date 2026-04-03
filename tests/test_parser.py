"""Tests for parser.py — JSON extraction and normalization."""

import json

from src.parser import normalize_findings, parse_findings


class TestParseFindingsCleanJson:
    def test_valid_json(self):
        raw = json.dumps({"findings": [
            {"company": "Acme Corp", "summary": "Failed ERP rollout", "severity": "HIGH"},
            {"company": "BigCo", "summary": "CTO departure", "severity": "MEDIUM"},
        ]})
        result = parse_findings(raw, "transformation_failures")
        assert len(result) == 2
        assert result[0]["company"] == "Acme Corp"
        assert result[0]["category"] == "transformation_failures"

    def test_empty_findings(self):
        raw = json.dumps({"findings": []})
        result = parse_findings(raw, "test")
        assert result == []

    def test_empty_string(self):
        assert parse_findings("", "test") == []

    def test_none_input(self):
        assert parse_findings(None, "test") == []


class TestParseFindingsMarkdownFences:
    def test_json_in_fences(self):
        raw = '```json\n{"findings": [{"company": "TestCo", "summary": "Issues"}]}\n```'
        result = parse_findings(raw, "test")
        assert len(result) == 1
        assert result[0]["company"] == "TestCo"

    def test_json_with_preamble(self):
        raw = 'Here are the findings:\n\n{"findings": [{"company": "TestCo", "summary": "Issues"}]}'
        result = parse_findings(raw, "test")
        assert len(result) == 1


class TestParseFindingsMalformed:
    def test_completely_invalid(self):
        result = parse_findings("this is not json at all", "test")
        assert result == []

    def test_json_missing_findings_key(self):
        raw = json.dumps({"results": [{"company": "Test"}]})
        result = parse_findings(raw, "test")
        assert result == []

    def test_truncated_json(self):
        raw = '{"findings": [{"company": "Test", "summary": "Tr'
        result = parse_findings(raw, "test")
        assert result == []


class TestNormalize:
    def test_defaults(self):
        findings = [{"company": "TestCo"}]
        result = normalize_findings(findings, "test")
        assert len(result) == 1
        assert result[0]["severity"] == "MEDIUM"
        assert result[0]["source"] == "Unknown"

    def test_skip_no_company(self):
        findings = [{"summary": "No company here"}]
        result = normalize_findings(findings, "test")
        assert result == []

    def test_invalid_severity_defaults(self):
        findings = [{"company": "Test", "severity": "CRITICAL"}]
        result = normalize_findings(findings, "test")
        assert result[0]["severity"] == "MEDIUM"

    def test_executives_normalization(self):
        findings = [{"company": "Test", "executives": [
            {"name": "Jane Doe", "title": "CTO"},
            "John Smith",
        ]}]
        result = normalize_findings(findings, "test")
        assert len(result[0]["executives"]) == 2
        assert result[0]["executives"][0]["name"] == "Jane Doe"
        assert result[0]["executives"][1]["name"] == "John Smith"

    def test_executives_string(self):
        findings = [{"company": "Test", "executives": "Jane Doe"}]
        result = normalize_findings(findings, "test")
        assert result[0]["executives"] == [{"name": "Jane Doe", "title": ""}]

    def test_non_dict_findings_skipped(self):
        findings = [{"company": "Good"}, "bad", 42, None]
        result = normalize_findings(findings, "test")
        assert len(result) == 1
