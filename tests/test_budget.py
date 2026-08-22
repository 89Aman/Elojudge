"""Tests for job budget and cost controls."""

import pytest
from app.budget import JobBudget


class TestJobBudget:
    def test_initial_budget(self):
        b = JobBudget(max_llm_requests=5, max_input_tokens=1000)
        assert b.can_make_request() is True
        assert b.is_exhausted is False

    def test_request_limit_exhaustion(self):
        b = JobBudget(max_llm_requests=2)
        assert b.can_make_request() is True

        b.record_usage(input_tokens=100, output_tokens=20)
        assert b.can_make_request() is True

        b.record_usage(input_tokens=100, output_tokens=20)
        assert b.can_make_request() is False
        assert b.is_exhausted is True
        assert "Max LLM requests" in b.exhaustion_reason

    def test_cost_calculation(self):
        b = JobBudget(max_estimated_cost=0.05)
        # 1M input tokens at $0.075 = $0.075 -> exceeds 0.05
        cost = b.calculate_cost(input_tokens=1_000_000, output_tokens=0)
        assert cost == 0.075

        b.record_usage(input_tokens=1_000_000, output_tokens=0)
        assert b.can_make_request() is False
        assert b.is_exhausted is True
