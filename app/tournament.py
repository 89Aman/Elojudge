"""Swiss tournament engine with Elo rating updates and early stopping."""

from __future__ import annotations

import math

from app.budget import JobBudget
from app.config import settings
from app.schemas import CandidateState, FeedbackCluster, MatchRecord

K_FACTOR = 24
INITIAL_ELO = 1200.0


# ── Elo Mathematics ──────────────────────────────────────────────────────────

def compute_elo_update(
    rating_a: float,
    rating_b: float,
    a_wins: bool,
) -> tuple[float, float]:
    """Compute new Elo ratings after a match. Returns (new_rating_a, new_rating_b)."""
    expected_a = 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))
    expected_b = 1.0 - expected_a

    score_a = 1.0 if a_wins else 0.0
    score_b = 1.0 - score_a

    new_a = rating_a + K_FACTOR * (score_a - expected_a)
    new_b = rating_b + K_FACTOR * (score_b - expected_b)

    return round(new_a, 2), round(new_b, 2)


# ── Tournament Initialization ────────────────────────────────────────────────

def init_candidates(
    clusters: list[FeedbackCluster],
    pre_rank_scores: dict[str, float],
) -> list[CandidateState]:
    """Initialize candidate tournament states from feedback clusters."""
    candidates = []
    for c in clusters:
        candidates.append(
            CandidateState(
                id=c.id,
                text=c.representative_text,
                merged_feedback=c.merged_feedback,
                report_count=c.report_count,
                severity=c.severity,
                elo=INITIAL_ELO,
                wins=0,
                losses=0,
                local_pre_rank=pre_rank_scores.get(c.id, 0.0),
                opponents=[],
                history=[],
                tier="Later",
            )
        )
    return candidates


def compute_num_rounds(n_candidates: int) -> int:
    """Compute max Swiss rounds: ceil(log2(n)) + 1."""
    if n_candidates <= 1:
        return 0
    return math.ceil(math.log2(n_candidates)) + 1


# ── Swiss Pairings ───────────────────────────────────────────────────────────

def _sort_key(c: CandidateState) -> tuple:
    """Sort key: wins desc, Elo desc, local pre-rank desc."""
    return (-c.wins, -c.elo, -c.local_pre_rank)


def generate_pairings(
    candidates: list[CandidateState],
    round_num: int,
) -> list[tuple[str, str]]:
    """Generate Swiss pairings for a round, avoiding rematches and handling byes."""
    if round_num == 1:
        sorted_cands = sorted(candidates, key=lambda c: -c.local_pre_rank)
    else:
        sorted_cands = sorted(candidates, key=_sort_key)

    active = list(sorted_cands)

    # Bye for odd candidate count
    if len(active) % 2 == 1:
        bye_cand = None
        for c in reversed(active):
            if not getattr(c, "_had_bye", False):
                bye_cand = c
                break
        if bye_cand is None:
            bye_cand = active[-1]
        active.remove(bye_cand)
        setattr(bye_cand, "_had_bye", True)

    pairs: list[tuple[str, str]] = []
    used: set[str] = set()

    if round_num == 1:
        # Top-half vs bottom-half
        half = len(active) // 2
        for i in range(half):
            a = active[i]
            b = active[half + i]
            pairs.append((a.id, b.id))
            used.add(a.id)
            used.add(b.id)
    else:
        # Greedy adjacent pairing with rematch avoidance
        remaining = list(active)
        while len(remaining) >= 2:
            a = remaining.pop(0)
            if a.id in used:
                continue

            paired = False
            for j, b in enumerate(remaining):
                if b.id in used:
                    continue
                if b.id not in a.opponents:
                    pairs.append((a.id, b.id))
                    used.add(a.id)
                    used.add(b.id)
                    remaining.pop(j)
                    paired = True
                    break

            if not paired and remaining:
                b = remaining.pop(0)
                pairs.append((a.id, b.id))
                used.add(a.id)
                used.add(b.id)

    return pairs


# ── Match Result Application ─────────────────────────────────────────────────

def apply_match_result(
    candidates: list[CandidateState],
    match: MatchRecord,
) -> None:
    """Update candidate Elo, records, and history in place."""
    cand_map = {c.id: c for c in candidates}
    a = cand_map[match.item_a_id]
    b = cand_map[match.item_b_id]

    match.elo_before_a = a.elo
    match.elo_before_b = b.elo

    a_wins = match.winner_id == a.id
    new_a, new_b = compute_elo_update(a.elo, b.elo, a_wins)

    match.elo_after_a = new_a
    match.elo_after_b = new_b

    a.elo = new_a
    b.elo = new_b

    if a_wins:
        a.wins += 1
        b.losses += 1
    else:
        a.losses += 1
        b.wins += 1

    a.opponents.append(b.id)
    b.opponents.append(a.id)

    a.history.append(match)
    b.history.append(match)


# ── Early Stopping Checks ────────────────────────────────────────────────────

def check_early_stopping(
    round_num: int,
    total_rounds: int,
    candidates: list[CandidateState],
    previous_top_ids: list[str],
    budget: JobBudget,
) -> tuple[bool, str]:
    """Check if tournament can stop early without sacrificing ranking accuracy."""
    if not settings.enable_early_stopping or round_num < 2:
        return False, ""

    # 1. Budget exhausted or nearly exhausted
    if budget.is_exhausted or budget.used_llm_requests >= budget.max_llm_requests:
        return True, f"Stopped early: Budget ceiling reached ({budget.used_llm_requests} requests)."

    # 2. Ranking stability (top 3 unchanged)
    ranked = rank_candidates(candidates)
    current_top_ids = [c.id for c in ranked[:3]]

    if previous_top_ids and current_top_ids == previous_top_ids and round_num >= 3:
        # Check if top item has decisive Elo margin (>= 40 Elo over #2)
        if len(ranked) >= 2 and (ranked[0].elo - ranked[1].elo >= 40.0):
            return True, "Stopped early: Top candidate ranking stabilized with decisive Elo margin."

    return False, ""


# ── Final Ranking & Tier Assignment ──────────────────────────────────────────

def rank_candidates(candidates: list[CandidateState]) -> list[CandidateState]:
    """Sort candidates by Elo desc, wins desc, pre-rank desc."""
    return sorted(candidates, key=lambda c: (-c.elo, -c.wins, -c.local_pre_rank))


def assign_tiers(ranked: list[CandidateState]) -> list[CandidateState]:
    """Assign Now / Next / Later tiers based on position."""
    n = len(ranked)
    for i, c in enumerate(ranked):
        if i == 0:
            c.tier = "Now"
        elif i <= max(1, n // 3):
            c.tier = "Next"
        else:
            c.tier = "Later"
    return ranked
