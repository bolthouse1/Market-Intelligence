"""Tests for dedup.py — hash generation and fuzzy matching."""

from src.dedup import compute_dedup_hash, deduplicate_findings, is_duplicate


class TestComputeHash:
    def test_deterministic(self):
        h1 = compute_dedup_hash("Acme Corp", "Failed ERP implementation")
        h2 = compute_dedup_hash("Acme Corp", "Failed ERP implementation")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = compute_dedup_hash("ACME CORP", "Failed ERP")
        h2 = compute_dedup_hash("acme corp", "Failed ERP")
        assert h1 == h2

    def test_different_companies_differ(self):
        h1 = compute_dedup_hash("Acme Corp", "Failed ERP")
        h2 = compute_dedup_hash("BigCo", "Failed ERP")
        assert h1 != h2

    def test_strips_whitespace(self):
        h1 = compute_dedup_hash("  Acme Corp  ", "Failed ERP")
        h2 = compute_dedup_hash("Acme Corp", "Failed ERP")
        assert h1 == h2


class TestIsDuplicate:
    def test_exact_hash_match(self):
        finding = {"company": "Acme Corp", "summary": "Failed ERP implementation"}
        recent = [{"company": "Acme Corp", "summary": "Failed ERP implementation",
                    "dedup_hash": compute_dedup_hash("Acme Corp", "Failed ERP implementation")}]
        assert is_duplicate(finding, recent) is True

    def test_fuzzy_company_match(self):
        finding = {"company": "Acme Corp Inc", "summary": "Failed ERP implementation costs mount"}
        recent = [{"company": "Acme Corp Inc.", "summary": "Failed ERP implementation costs rising",
                    "dedup_hash": "different_hash"}]
        assert is_duplicate(finding, recent) is True

    def test_same_company_different_issue(self):
        finding = {"company": "Acme Corp", "summary": "CEO fired after board dispute over strategy"}
        recent = [{"company": "Acme Corp", "summary": "Failed ERP implementation costs mount",
                    "dedup_hash": "different_hash"}]
        # Different enough summary should NOT be duplicate
        assert is_duplicate(finding, recent) is False

    def test_completely_different(self):
        finding = {"company": "Tesla", "summary": "Autonomous driving program delays"}
        recent = [{"company": "Acme Corp", "summary": "Failed ERP implementation",
                    "dedup_hash": "some_hash"}]
        assert is_duplicate(finding, recent) is False

    def test_empty_recent(self):
        finding = {"company": "Acme", "summary": "Some issue"}
        assert is_duplicate(finding, []) is False


class TestDeduplicateFindings:
    def test_all_new(self):
        findings = [
            {"company": "Acme", "summary": "Issue A"},
            {"company": "BigCo", "summary": "Issue B"},
        ]
        result = deduplicate_findings(findings, [])
        assert len(result) == 2
        assert all(f["is_new"] for f in result)

    def test_filters_duplicates(self):
        recent = [{"company": "Acme", "summary": "Issue A",
                    "dedup_hash": compute_dedup_hash("Acme", "Issue A")}]
        findings = [
            {"company": "Acme", "summary": "Issue A"},
            {"company": "BigCo", "summary": "Issue B"},
        ]
        result = deduplicate_findings(findings, recent)
        assert len(result) == 1
        assert result[0]["company"] == "BigCo"

    def test_within_batch_dedup(self):
        findings = [
            {"company": "Acme", "summary": "Same issue here"},
            {"company": "Acme", "summary": "Same issue here"},
        ]
        result = deduplicate_findings(findings, [])
        assert len(result) == 1
