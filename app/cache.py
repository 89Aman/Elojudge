"""Order-independent exact caching layer for rubrics and pairwise judgments."""

from __future__ import annotations

import hashlib
from typing import Optional
from app.schemas import Rubric


class ExactCache:
    """In-memory cache for rubrics and pairwise comparisons."""

    def __init__(self) -> None:
        # Key: context_hash -> Rubric
        self._rubric_cache: dict[str, Rubric] = {}

        # Key: (context_hash, rubric_hash, frozenset({norm_text_a, norm_text_b})) -> (winner_text, reason, confidence)
        self._pair_cache: dict[tuple[str, str, frozenset[str]], tuple[str, str, float]] = {}

        # Metrics
        self.rubric_hits: int = 0
        self.rubric_misses: int = 0
        self.pair_hits: int = 0
        self.pair_misses: int = 0

    @staticmethod
    def hash_text(text: str) -> str:
        """Create 16-char hex hash of normalized text."""
        return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def hash_rubric(rubric: Rubric) -> str:
        """Create deterministic hash of rubric dimensions."""
        repr_str = "|".join(f"{d.name}:{d.weight:.2f}" for d in sorted(rubric.dimensions, key=lambda x: x.name))
        return hashlib.sha256(repr_str.encode("utf-8")).hexdigest()[:16]

    # ── Rubric Cache ─────────────────────────────────────────────────────────

    def get_rubric(self, product_context: str) -> Optional[Rubric]:
        """Lookup cached rubric by product context."""
        key = self.hash_text(product_context)
        if key in self._rubric_cache:
            self.rubric_hits += 1
            return self._rubric_cache[key]
        self.rubric_misses += 1
        return None

    def set_rubric(self, product_context: str, rubric: Rubric) -> None:
        """Store rubric in cache."""
        key = self.hash_text(product_context)
        self._rubric_cache[key] = rubric

    # ── Pairwise Cache ───────────────────────────────────────────────────────

    def get_pair_judgment(
        self,
        product_context: str,
        rubric: Rubric,
        norm_text_a: str,
        norm_text_b: str,
    ) -> Optional[tuple[str, str, float]]:
        """Lookup cached judgment. Order-independent on text_a / text_b."""
        ctx_hash = self.hash_text(product_context)
        rubric_hash = self.hash_rubric(rubric)
        pair_set = frozenset({norm_text_a, norm_text_b})
        key = (ctx_hash, rubric_hash, pair_set)

        if key in self._pair_cache:
            self.pair_hits += 1
            return self._pair_cache[key]  # (winner_text, reason, confidence)
        self.pair_misses += 1
        return None

    def set_pair_judgment(
        self,
        product_context: str,
        rubric: Rubric,
        norm_text_a: str,
        norm_text_b: str,
        winner_text: str,
        reason: str,
        confidence: float = 0.9,
    ) -> None:
        """Store pairwise judgment in order-independent format."""
        ctx_hash = self.hash_text(product_context)
        rubric_hash = self.hash_rubric(rubric)
        pair_set = frozenset({norm_text_a, norm_text_b})
        key = (ctx_hash, rubric_hash, pair_set)
        self._pair_cache[key] = (winner_text, reason, confidence)

    def clear(self) -> None:
        """Clear all caches."""
        self._rubric_cache.clear()
        self._pair_cache.clear()
        self.rubric_hits = 0
        self.rubric_misses = 0
        self.pair_hits = 0
        self.pair_misses = 0


# Global singleton instance
cache_layer = ExactCache()
