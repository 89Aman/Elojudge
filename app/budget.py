"""Job budget tracker and cost control policy for EloJudge.

Enforces per-job limits on requests, tokens, estimated spend, and retries.
Stops LLM calls gracefully when limits are reached, falling back to local decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class JobBudget:
    """Tracks consumption and enforces per-job limits."""

    max_llm_requests: int = settings.max_llm_requests_per_job
    max_input_tokens: int = settings.max_input_tokens_per_job
    max_output_tokens: int = settings.max_output_tokens_per_job
    max_estimated_cost: float = settings.max_estimated_cost_per_job
    max_retries: int = settings.max_retries_per_batch

    # Actual usage
    used_llm_requests: int = 0
    used_input_tokens: int = 0
    used_output_tokens: int = 0
    used_retries: int = 0
    estimated_cost: float = 0.0

    # Exhaustion tracking
    is_exhausted: bool = False
    exhaustion_reason: str = ""
    warnings: list[str] = field(default_factory=list)

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated cost based on token counts."""
        input_cost = (input_tokens / 1_000_000.0) * settings.cost_per_m_input_tokens
        output_cost = (output_tokens / 1_000_000.0) * settings.cost_per_m_output_tokens
        return round(input_cost + output_cost, 6)

    def can_make_request(self) -> bool:
        """Check if another LLM request is allowed within budget."""
        if self.is_exhausted:
            return False

        if self.used_llm_requests >= self.max_llm_requests:
            self._exhaust("Max LLM requests reached (%d/%d)" % (self.used_llm_requests, self.max_llm_requests))
            return False

        if self.used_input_tokens >= self.max_input_tokens:
            self._exhaust("Input token budget exceeded (%d/%d)" % (self.used_input_tokens, self.max_input_tokens))
            return False

        if self.used_output_tokens >= self.max_output_tokens:
            self._exhaust("Output token budget exceeded (%d/%d)" % (self.used_output_tokens, self.max_output_tokens))
            return False

        if self.estimated_cost >= self.max_estimated_cost:
            self._exhaust("Cost ceiling reached ($%.4f/$%.4f)" % (self.estimated_cost, self.max_estimated_cost))
            return False

        return True

    def record_usage(self, input_tokens: int = 0, output_tokens: int = 0, is_retry: bool = False) -> None:
        """Record usage from an executed LLM call."""
        self.used_llm_requests += 1
        self.used_input_tokens += input_tokens
        self.used_output_tokens += output_tokens
        if is_retry:
            self.used_retries += 1

        cost = self.calculate_cost(input_tokens, output_tokens)
        self.estimated_cost = round(self.estimated_cost + cost, 6)

        # Check post-record thresholds
        if self.estimated_cost >= self.max_estimated_cost:
            self._exhaust("Cost ceiling reached after request ($%.4f)" % self.estimated_cost)
        elif self.used_llm_requests >= self.max_llm_requests:
            self._exhaust("Max LLM requests reached (%d)" % self.used_llm_requests)

    def _exhaust(self, reason: str) -> None:
        """Mark budget as exhausted and record warning."""
        if not self.is_exhausted:
            self.is_exhausted = True
            self.exhaustion_reason = reason
            self.warnings.append("Budget limit reached: %s. Routing remaining decisions to local fallback." % reason)
            logger.warning("Job budget exhausted: %s", reason)
