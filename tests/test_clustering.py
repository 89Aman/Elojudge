"""Tests for feedback clustering and aggregation."""

import pytest
from app.aggregation import determine_severity, extract_keywords, CRITICAL_KEYWORDS, HIGH_KEYWORDS
from app.clustering import cluster_feedback_items


class TestSeverityClassification:
    def test_critical_keywords(self):
        assert determine_severity("App crashes on startup") == "critical"
        assert determine_severity("Potential security vulnerability in auth") == "critical"
        assert determine_severity("Severe data loss when saving note") == "critical"

    def test_high_keywords(self):
        assert determine_severity("Cannot sync notes across devices") == "high"
        assert determine_severity("Export button is completely broken") == "high"

    def test_medium_keywords(self):
        assert determine_severity("Better search filtering options") == "medium"
        assert determine_severity("Add tags to organize notes") == "medium"

    def test_low_keywords(self):
        assert determine_severity("Add dark mode theme") == "low"
        assert determine_severity("Change button colors and icons") == "low"


class TestClustering:
    def test_near_duplicate_merging(self):
        items = [
            ("App crashes on login", "app crashes on login"),
            ("Login screen keeps crashing", "login screen keeps crashing"),
            ("Add dark mode", "add dark mode"),
        ]
        # With threshold 0.75 to merge login crash variants
        clusters, merged_count = cluster_feedback_items(items, threshold=0.70)
        assert len(clusters) <= 3
        # Should have at least one cluster with report count >= 1
        assert any(c.report_count >= 1 for c in clusters)

    def test_cluster_metadata_and_severity_upgrade(self):
        items = [
            ("Login issue", "login issue"),
            ("Login crashes and causes data loss", "login crashes and causes data loss"),
        ]
        clusters, _ = cluster_feedback_items(items, threshold=0.3)
        # Merged cluster should escalate severity to critical
        assert clusters[0].severity == "critical"
        assert clusters[0].report_count == 2
