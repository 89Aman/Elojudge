"""Tests for app.cleaner — local feedback cleaning pipeline."""

import pytest

from app.cleaner import (
    clean_feedback,
    is_spam,
    is_too_short,
    normalize_text,
)


# ── normalize_text ───────────────────────────────────────────────────────────

class TestNormalizeText:
    def test_basic(self):
        assert normalize_text("  Hello World  ") == "hello world"

    def test_collapses_whitespace(self):
        assert normalize_text("hello   world") == "hello world"

    def test_strips_punctuation_edges(self):
        assert normalize_text("...hello!") == "hello"

    def test_unicode_normalization(self):
        result = normalize_text("Ｈello")
        assert "hello" in result.lower()


# ── is_too_short ─────────────────────────────────────────────────────────────

class TestIsTooShort:
    def test_empty(self):
        assert is_too_short("") is True

    def test_one_word(self):
        assert is_too_short("hello") is True

    def test_two_words(self):
        assert is_too_short("hello world") is True

    def test_three_words(self):
        assert is_too_short("add dark mode") is False

    def test_long_text(self):
        assert is_too_short("this is a long feedback item") is False


# ── is_spam ──────────────────────────────────────────────────────────────────

class TestIsSpam:
    def test_url_only(self):
        assert is_spam("https://example.com/page") is True

    def test_www_url(self):
        assert is_spam("www.example.com") is True

    def test_all_caps_spam(self):
        assert is_spam("THIS IS ALL CAPS SPAM TEXT") is True

    def test_normal_text_not_spam(self):
        assert is_spam("Add dark mode") is False

    def test_repeated_chars(self):
        assert is_spam("aaaaaaa this is bad") is True

    def test_short_caps_not_spam(self):
        assert is_spam("OK") is False


# ── clean_feedback ───────────────────────────────────────────────────────────

class TestCleanFeedback:
    def test_removes_empty(self):
        result = clean_feedback(["", "   ", "Add dark mode", "Export to PDF", "Better search"])
        assert result.summary.removed_empty_or_short >= 2
        assert result.summary.clean_items >= 1

    def test_removes_short_items(self):
        result = clean_feedback(["hi", "ok", "Add dark mode", "Export notes to PDF", "Better search"])
        assert result.summary.removed_empty_or_short >= 2

    def test_removes_spam(self):
        result = clean_feedback([
            "https://spam.com",
            "AAAAAAA SPAM TEXT HERE",
            "Add dark mode to the app",
            "Export notes to PDF format",
            "Better search with filters",
        ])
        assert result.summary.removed_spam >= 1

    def test_exact_dedup(self):
        result = clean_feedback([
            "Add dark mode",
            "add dark mode",
            "ADD DARK MODE",
            "Export notes to PDF",
            "Better search option",
        ])
        assert result.summary.removed_exact_duplicates >= 1

    def test_near_dedup(self):
        result = clean_feedback([
            "App crashes on login",
            "Login screen keeps crashing",
            "Export notes to PDF",
            "Better search with filters",
        ])
        assert result.summary.unique_clusters <= 4

    def test_preserves_original_text(self):
        result = clean_feedback([
            "  Add Dark Mode  ",
            "Export Notes to PDF",
            "Better search with filters",
        ])
        texts = [c.representative_text for c in result.clusters]
        assert "Add Dark Mode" in texts

    def test_returns_cluster_ids(self):
        result = clean_feedback([
            "Add dark mode feature",
            "Export notes to PDF",
            "Better search filtering",
        ])
        for c in result.clusters:
            assert c.id.startswith("cluster_")

    def test_cleaning_summary_counts(self):
        result = clean_feedback([
            "Add dark mode feature",
            "Export notes to PDF",
            "Better search option",
        ])
        s = result.summary
        assert s.raw_items == 3
        assert s.clean_items == sum(c.report_count for c in result.clusters)
