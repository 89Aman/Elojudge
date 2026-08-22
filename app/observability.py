"""Observability, metrics collection, and token estimation."""

from __future__ import annotations

import time
from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """Estimate token count: roughly 1 token per 4 chars or 0.75 words."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class RequestMetric:
    """Individual model or step metric."""

    step_name: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cache_hit: bool
    fallback: bool
    estimated_cost: float


class ObservabilityTracker:
    """Tracks end-to-end execution metrics and telemetry."""

    def __init__(self) -> None:
        self.start_time: float = time.time()
        self.records: list[RequestMetric] = []
        self.local_decisions: int = 0
        self.cache_hits: int = 0
        self.fallback_decisions: int = 0

    def record_request(
        self,
        step_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        cache_hit: bool = False,
        fallback: bool = False,
        cost: float = 0.0,
    ) -> None:
        """Record model call telemetry."""
        if cache_hit:
            self.cache_hits += 1
        if fallback:
            self.fallback_decisions += 1

        self.records.append(
            RequestMetric(
                step_name=step_name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=round(latency_ms, 2),
                cache_hit=cache_hit,
                fallback=fallback,
                estimated_cost=cost,
            )
        )

    def record_local_decision(self) -> None:
        """Increment local obvious-pair decision counter."""
        self.local_decisions += 1
