"""Feedback clustering and deduplication engine."""

from __future__ import annotations

from difflib import SequenceMatcher
from app.aggregation import (
    CRITICAL_KEYWORDS,
    HIGH_KEYWORDS,
    MEDIUM_KEYWORDS,
    determine_severity,
    extract_keywords,
)
from app.schemas import FeedbackCluster


def find_near_duplicate_cluster(
    normalized: str,
    clusters: list[FeedbackCluster],
    threshold: float = 0.85,
) -> int | None:
    """Find index of existing cluster matching normalized text within similarity threshold."""
    for idx, cluster in enumerate(clusters):
        ratio = SequenceMatcher(None, normalized, cluster.normalized).ratio()
        if ratio >= threshold:
            return idx
    return None


def cluster_feedback_items(
    deduped_items: list[tuple[str, str]],
    threshold: float = 0.85,
    max_clusters: int = 30,
) -> tuple[list[FeedbackCluster], int]:
    """Group deduped feedback items into representative clusters.

    Args:
        deduped_items: List of (original_text, normalized_text) tuples.
        threshold: SequenceMatcher similarity threshold.
        max_clusters: Hard cap on distinct clusters.

    Returns:
        (clusters, merged_near_duplicates_count)
    """
    clusters: list[FeedbackCluster] = []
    merged_count = 0

    for original, normalized in deduped_items:
        cluster_idx = find_near_duplicate_cluster(normalized, clusters, threshold)
        if cluster_idx is not None:
            # Merge into cluster
            c = clusters[cluster_idx]
            c.merged_feedback.append(original)
            c.report_count += 1

            # Upgrade severity if merged item is more severe
            merged_severity = determine_severity(original)
            if merged_severity == "critical" or (merged_severity == "high" and c.severity in ("medium", "low")):
                c.severity = merged_severity

            merged_count += 1
        else:
            if len(clusters) < max_clusters:
                severity = determine_severity(original)
                impact_kws = extract_keywords(original, CRITICAL_KEYWORDS | HIGH_KEYWORDS | MEDIUM_KEYWORDS)
                urgency_kws = extract_keywords(original, HIGH_KEYWORDS | CRITICAL_KEYWORDS)

                cluster = FeedbackCluster(
                    id=f"cluster_{len(clusters) + 1}",
                    representative_text=original,
                    normalized=normalized,
                    merged_feedback=[],
                    report_count=1,
                    severity=severity,
                    impact_keywords=impact_kws,
                    urgency_keywords=urgency_kws,
                )
                clusters.append(cluster)
            else:
                # Exceeded max clusters - merge into most similar existing or drop
                merged_count += 1

    return clusters, merged_count
