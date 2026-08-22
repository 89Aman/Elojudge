"""Router for obvious-pair resolution, model selection, and fallback routing."""

from __future__ import annotations

from typing import Optional
from app.config import settings
from app.schemas import CandidateState


def check_obvious_pair(
    cand_a: CandidateState,
    cand_b: CandidateState,
    margin: float = settings.local_decision_margin,
) -> tuple[bool, Optional[str], Optional[str]]:
    """Determine if a pair can be resolved locally without LLM inference.

    Rules for local obvious resolution:
    1. Critical severity (e.g. crash/data loss) vs Low severity (cosmetic theme).
    2. Local pre-rank score difference exceeds configured decision margin.

    Returns:
        (is_obvious, winner_id, reason)
    """
    if not settings.enable_local_decisions:
        return False, None, None

    # Severity disparity rule
    if cand_a.severity == "critical" and cand_b.severity in ("low", "medium"):
        return True, cand_a.id, "Critical issue resolution prioritized over lower-severity request."
    if cand_b.severity == "critical" and cand_a.severity in ("low", "medium"):
        return True, cand_b.id, "Critical issue resolution prioritized over lower-severity request."

    # Pre-rank margin rule
    score_diff = cand_a.local_pre_rank - cand_b.local_pre_rank
    if abs(score_diff) >= margin:
        if score_diff > 0:
            return True, cand_a.id, f"Clear pre-ranking priority ({cand_a.local_pre_rank:.2f} vs {cand_b.local_pre_rank:.2f})."
        else:
            return True, cand_b.id, f"Clear pre-ranking priority ({cand_b.local_pre_rank:.2f} vs {cand_a.local_pre_rank:.2f})."

    return False, None, None


def select_model_for_pair(
    cand_a: CandidateState,
    cand_b: CandidateState,
) -> str:
    """Select appropriate model (cheap vs strong) based on severity and ambiguity."""
    # Escalate to strong model for critical security/crash issues
    if cand_a.severity == "critical" or cand_b.severity == "critical":
        return settings.model_strong

    # Default to cheap model for normal comparisons
    return settings.model_cheap
