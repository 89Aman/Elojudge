"""Tests for app.judge — LLM response parsing and validation."""

import pytest

from app.judge import parse_judgment_response


class TestParseJudgmentResponse:
    def test_valid_two_pair(self):
        raw = '''{
            "judgments": [
                {"pair_id": 1, "winner": "A", "reason": "Better alignment with core goals."},
                {"pair_id": 2, "winner": "B", "reason": "Higher user value."}
            ]
        }'''
        result = parse_judgment_response(raw, expected_count=2, expected_pair_ids=[1, 2])
        assert result is not None
        assert len(result) == 2
        assert result[0].winner == "A"
        assert result[1].winner == "B"

    def test_valid_single_pair(self):
        raw = '{"judgments": [{"pair_id": 5, "winner": "A", "reason": "Direct goal impact."}]}'
        result = parse_judgment_response(raw, expected_count=1, expected_pair_ids=[5])
        assert result is not None
        assert len(result) == 1
        assert result[0].pair_id == 5

    def test_invalid_json(self):
        raw = "not json at all"
        result = parse_judgment_response(raw, expected_count=1, expected_pair_ids=[1])
        assert result is None

    def test_wrong_count(self):
        raw = '{"judgments": [{"pair_id": 1, "winner": "A", "reason": "test"}]}'
        result = parse_judgment_response(raw, expected_count=2, expected_pair_ids=[1, 2])
        assert result is None

    def test_wrong_pair_ids(self):
        raw = '''{
            "judgments": [
                {"pair_id": 99, "winner": "A", "reason": "test"},
                {"pair_id": 100, "winner": "B", "reason": "test"}
            ]
        }'''
        result = parse_judgment_response(raw, expected_count=2, expected_pair_ids=[1, 2])
        assert result is None

    def test_invalid_winner(self):
        raw = '{"judgments": [{"pair_id": 1, "winner": "C", "reason": "test"}]}'
        result = parse_judgment_response(raw, expected_count=1, expected_pair_ids=[1])
        assert result is None

    def test_missing_fields(self):
        raw = '{"judgments": [{"pair_id": 1, "winner": "A"}]}'
        result = parse_judgment_response(raw, expected_count=1, expected_pair_ids=[1])
        assert result is None

    def test_empty_judgments(self):
        raw = '{"judgments": []}'
        result = parse_judgment_response(raw, expected_count=1, expected_pair_ids=[1])
        assert result is None

    def test_markdown_wrapped_json(self):
        """LLM sometimes wraps JSON in markdown code blocks — should successfully extract."""
        raw = '```json\n{"judgments": [{"pair_id": 1, "winner": "A", "reason": "test"}]}\n```'
        result = parse_judgment_response(raw, expected_count=1, expected_pair_ids=[1])
        assert result is not None
        assert len(result) == 1
        assert result[0].winner == "A"

    def test_extra_whitespace(self):
        raw = '  \n  {"judgments": [{"pair_id": 1, "winner": "B", "reason": "Stronger impact."}]}  \n  '
        result = parse_judgment_response(raw, expected_count=1, expected_pair_ids=[1])
        assert result is not None
        assert result[0].winner == "B"
