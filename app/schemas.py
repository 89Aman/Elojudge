"""Pydantic models and data schemas for EloJudge."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ── Request Models ────────────────────────────────────────────────────────────

class BudgetConfig(BaseModel):
    """Optional per-request budget overrides."""

    max_llm_requests: Optional[int] = Field(default=None, ge=1, le=50)
    max_input_tokens: Optional[int] = Field(default=None, ge=1000)
    max_output_tokens: Optional[int] = Field(default=None, ge=500)
    max_estimated_cost: Optional[float] = Field(default=None, ge=0.01)


class RankRequest(BaseModel):
    """Input payload for POST /rank."""

    product_context: str = Field(
        ...,
        min_length=20,
        max_length=2500,
        description="Description of the product, goals, and constraints.",
    )
    feedback_items: list[str] = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Raw feedback items, one per entry.",
    )
    max_candidates: int = Field(
        default=8,
        ge=2,
        le=30,
        description="Maximum candidates entering the tournament.",
    )
    budget: Optional[BudgetConfig] = Field(
        default=None,
        description="Optional custom budget limits for this run.",
    )
    user_api_key: Optional[str] = Field(
        default=None,
        description="Optional Bring-Your-Own-Key Gemini API Key from user.",
    )
    google_id_token: Optional[str] = Field(
        default=None,
        description="Optional Google OAuth ID token for authenticated rate limits.",
    )

    @field_validator("feedback_items", mode="before")
    @classmethod
    def clean_feedback_items(cls, v: list[str]) -> list[str]:
        """Trim whitespace, drop blanks, cap each item at 300 chars."""
        cleaned = []
        for item in v:
            trimmed = str(item).strip()
            if trimmed:
                cleaned.append(trimmed[:300])
        if len(cleaned) < 2:
            raise ValueError("Need at least 2 non-empty feedback items.")
        if len(cleaned) > 100:
            raise ValueError("Maximum 100 raw feedback items allowed per request.")
        return cleaned


# ── Rubric Models ────────────────────────────────────────────────────────────

class RubricDimension(BaseModel):
    """Single rubric dimension."""

    name: str
    weight: float = Field(ge=0.0)
    description: str


class Rubric(BaseModel):
    """Structured rubric with 3–5 weighted dimensions."""

    dimensions: list[RubricDimension] = Field(min_length=3, max_length=5)


# ── Cleaning & Clustering Models ─────────────────────────────────────────────

class CleanedItem(BaseModel):
    """Raw cleaned item before cluster aggregation."""

    id: str
    text: str
    normalized: str
    merged_feedback: list[str] = Field(default_factory=list)


class FeedbackCluster(BaseModel):
    """Aggregated feedback cluster."""

    id: str
    representative_text: str
    normalized: str
    merged_feedback: list[str] = Field(default_factory=list)
    report_count: int = 1
    severity: str = "medium"  # "critical" | "high" | "medium" | "low"
    impact_keywords: list[str] = Field(default_factory=list)
    urgency_keywords: list[str] = Field(default_factory=list)


class CleaningSummary(BaseModel):
    """Statistics from cleaning and clustering pass."""

    raw_items: int
    removed_empty_or_short: int = 0
    removed_spam: int = 0
    removed_exact_duplicates: int = 0
    merged_near_duplicates: int = 0
    clean_items: int = 0
    unique_clusters: int = 0


class CleaningResult(BaseModel):
    """Output of cleaning and clustering stage."""

    summary: CleaningSummary
    clusters: list[FeedbackCluster]


# ── Tournament & Match Models ────────────────────────────────────────────────

class MatchRecord(BaseModel):
    """Record of one pairwise comparison."""

    round: int
    pair_id: int
    item_a_id: str
    item_b_id: str
    winner_id: str
    reason: str
    source: str = "AI judgment"  # "AI judgment" | "Cached AI judgment" | "Local rule (obvious pair)" | "Local fallback" | "Demo dataset result"
    model: str = ""
    confidence: Optional[float] = None
    cache_hit: bool = False
    elo_before_a: float = 1200.0
    elo_before_b: float = 1200.0
    elo_after_a: float = 1200.0
    elo_after_b: float = 1200.0


class CandidateState(BaseModel):
    """Tournament candidate state."""

    id: str
    text: str
    merged_feedback: list[str] = Field(default_factory=list)
    report_count: int = 1
    severity: str = "medium"
    elo: float = 1200.0
    wins: int = 0
    losses: int = 0
    local_pre_rank: float = 0.0
    opponents: list[str] = Field(default_factory=list)
    history: list[MatchRecord] = Field(default_factory=list)
    tier: str = "Later"  # "Now" | "Next" | "Later"


# ── LLM Judgment Models ──────────────────────────────────────────────────────

class SingleJudgment(BaseModel):
    """Single judgment returned by LLM."""

    pair_id: int
    winner: str = Field(pattern=r"^[AB]$")
    reason: str = Field(max_length=200)
    confidence: Optional[float] = None


class JudgmentBatch(BaseModel):
    """Batch of judgments returned by LLM."""

    judgments: list[SingleJudgment]


# ── Final Response Models ────────────────────────────────────────────────────

class RankedItem(BaseModel):
    """Ranked item in the final backlog."""

    rank: int
    id: str
    text: str
    merged_feedback: list[str] = Field(default_factory=list)
    report_count: int = 1
    severity: str = "medium"
    elo: float
    wins: int
    losses: int
    tier: str = "Later"  # "Now" | "Next" | "Later"
    reasons: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)
    beaten_items: list[str] = Field(default_factory=list)
    lost_to_items: list[str] = Field(default_factory=list)


class LowerPriorityItem(BaseModel):
    """Item not selected for tournament."""

    id: str
    text: str
    local_pre_rank_score: float
    report_count: int = 1
    severity: str = "medium"
    merged_feedback: list[str] = Field(default_factory=list)


class PipelineSummary(BaseModel):
    """High-level metrics and cost tracking for the pipeline run."""

    raw_items: int
    unique_clusters: int
    clean_items: int
    tournament_candidates: int
    rounds: int
    pairwise_comparisons: int
    llm_requests: int
    cache_hits: int
    local_decisions: int
    fallback_decisions: int
    early_stopped: bool = False
    early_stop_reason: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0


class RankResponse(BaseModel):
    """Complete response from POST /rank."""

    rubric: Rubric
    cleaning_summary: CleaningSummary
    summary: PipelineSummary
    ranked_items: list[RankedItem]
    lower_priority_candidates: list[LowerPriorityItem] = Field(default_factory=list)
    matches: list[MatchRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
