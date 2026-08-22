"""Local rule-based feedback cleaner and preprocessor.

Runs entirely locally before any API call. Removes noise, short items,
spam, exact duplicates, and clusters near-duplicates.
"""

from __future__ import annotations

import re
import unicodedata

from app.clustering import cluster_feedback_items
from app.config import settings
from app.schemas import CleaningResult, CleaningSummary


# ── Normalization ────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Lowercase, normalize unicode, collapse whitespace, strip punctuation edges."""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(".,!?;:\"'()-–—")
    return text


# ── Spam & Noise Filtering ───────────────────────────────────────────────────

_URL_ONLY = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)
_REPEATED_CHARS = re.compile(r"(.)\1{4,}")
_MIN_WORD_COUNT = 3


def is_spam(text: str) -> bool:
    """Return True if item matches spam patterns."""
    normalized = normalize_text(text)

    # URL-only
    if _URL_ONLY.match(normalized):
        return True

    # Obvious repeated characters
    if _REPEATED_CHARS.search(normalized):
        return True

    # All caps noise (preserve if contains critical keywords)
    words = text.split()
    if len(words) >= _MIN_WORD_COUNT and text == text.upper() and any(c.isalpha() for c in text):
        # Allow if it mentions crash or outage
        if not any(k in normalized for k in ("crash", "down", "outage", "broken", "loss", "bug")):
            return True

    return False


def is_too_short(text: str) -> bool:
    """Return True if item has fewer than minimum words."""
    words = [w for w in text.split() if len(w) > 0]
    return len(words) < _MIN_WORD_COUNT


# ── Main Cleaner Pipeline ────────────────────────────────────────────────────

def clean_feedback(
    raw_items: list[str],
    near_duplicate_threshold: float = settings.near_duplicate_threshold,
    max_clusters: int = settings.max_clean_clusters,
) -> CleaningResult:
    """Filter, deduplicate, and cluster feedback items locally.

    Returns:
        CleaningResult with summary metrics and feedback clusters.
    """
    total_raw = len(raw_items)
    removed_empty_or_short = 0
    removed_spam = 0
    removed_exact_dupes = 0

    # 1. Filter empty / short / spam
    filtered: list[tuple[str, str]] = []
    for item in raw_items:
        original = item.strip()
        if not original or is_too_short(original):
            removed_empty_or_short += 1
            continue
        if is_spam(original):
            removed_spam += 1
            continue
        filtered.append((original, normalize_text(original)))

    # 2. Exact deduplication
    seen_normalized: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for original, normalized in filtered:
        if normalized in seen_normalized:
            removed_exact_dupes += 1
            continue
        seen_normalized.add(normalized)
        deduped.append((original, normalized))

    # 3. Near-duplicate clustering & aggregation
    clusters, merged_near_dupes = cluster_feedback_items(
        deduped,
        threshold=near_duplicate_threshold,
        max_clusters=max_clusters,
    )

    clean_count = sum(c.report_count for c in clusters)

    summary = CleaningSummary(
        raw_items=total_raw,
        removed_empty_or_short=removed_empty_or_short,
        removed_spam=removed_spam,
        removed_exact_duplicates=removed_exact_dupes,
        merged_near_duplicates=merged_near_dupes,
        clean_items=clean_count,
        unique_clusters=len(clusters),
    )

    return CleaningResult(summary=summary, clusters=clusters)
