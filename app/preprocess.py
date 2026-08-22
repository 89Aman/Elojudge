"""Local pre-ranking using deterministic signals and cluster metadata."""

from __future__ import annotations

import re
from app.aggregation import (
    CRITICAL_KEYWORDS,
    HIGH_KEYWORDS,
    MEDIUM_KEYWORDS,
    extract_keywords,
    get_severity_weight,
)
from app.schemas import FeedbackCluster


def extract_goal_keywords(product_context: str) -> set[str]:
    """Extract key non-stopword tokens from product context."""
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "used", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "and", "but", "or", "not", "so", "this", "that", "it", "its", "they",
        "we", "you", "your", "our", "all", "any", "some", "more", "most",
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", product_context.lower())
    return {w for w in words if w not in stop_words}


def compute_cluster_score(cluster: FeedbackCluster, goal_keywords: set[str]) -> float:
    """Compute local pre-rank score combining goal overlap, severity, and frequency."""
    words = set(re.findall(r"\b[a-zA-Z]{3,}\b", cluster.normalized))

    # 1. Goal keyword overlap (0.0 to 1.0)
    goal_overlap = len(words & goal_keywords) / max(len(goal_keywords), 1)
    goal_score = min(goal_overlap * 2.5, 1.0)

    # 2. Severity score (normalized)
    sev_weight = get_severity_weight(cluster.severity)  # 0.3 to 3.0
    severity_score = min(sev_weight / 3.0, 1.0)

    # 3. Report frequency bonus (diminishing returns)
    freq_bonus = min((cluster.report_count - 1) * 0.1, 0.4)

    # 4. Impact & urgency keywords
    impact_hits = len(cluster.impact_keywords)
    urgency_hits = len(cluster.urgency_keywords)
    keyword_score = min((impact_hits * 0.15 + urgency_hits * 0.25), 1.0)

    score = (
        0.35 * goal_score
        + 0.35 * severity_score
        + 0.20 * keyword_score
        + 0.10 * freq_bonus
    )

    return round(score, 4)


def pre_rank_clusters(
    clusters: list[FeedbackCluster],
    product_context: str,
    max_candidates: int = 8,
) -> tuple[list[FeedbackCluster], list[FeedbackCluster], dict[str, float]]:
    """Score clusters and select tournament candidates vs lower priority items.

    Returns:
        (tournament_candidates, lower_priority_candidates, scores_dict)
    """
    goal_keywords = extract_goal_keywords(product_context)

    scores: dict[str, float] = {}
    for c in clusters:
        scores[c.id] = compute_cluster_score(c, goal_keywords)

    sorted_clusters = sorted(clusters, key=lambda c: scores[c.id], reverse=True)

    if len(sorted_clusters) <= max_candidates:
        return sorted_clusters, [], scores
    else:
        tournament = sorted_clusters[:max_candidates]
        lower = sorted_clusters[max_candidates:]
        return tournament, lower, scores
