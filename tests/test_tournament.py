"""Tests for app.tournament — Swiss pairing, early stopping, and tournament logic."""

import pytest

from app.budget import JobBudget
from app.schemas import CandidateState, FeedbackCluster, MatchRecord
from app.tournament import (
    apply_match_result,
    assign_tiers,
    check_early_stopping,
    compute_num_rounds,
    generate_pairings,
    init_candidates,
    rank_candidates,
)


def _make_clusters(n: int) -> list[FeedbackCluster]:
    """Create n test FeedbackClusters."""
    return [
        FeedbackCluster(
            id=f"cluster_{i+1}",
            representative_text=f"Feature {i+1}",
            normalized=f"feature {i+1}",
            report_count=1,
            severity="medium",
        )
        for i in range(n)
    ]


def _make_scores(n: int) -> dict[str, float]:
    """Create descending pre-rank scores."""
    return {f"cluster_{i+1}": round(1.0 - i * 0.1, 2) for i in range(n)}


class TestComputeNumRounds:
    def test_two_candidates(self):
        assert compute_num_rounds(2) == 2

    def test_four_candidates(self):
        assert compute_num_rounds(4) == 3

    def test_eight_candidates(self):
        assert compute_num_rounds(8) == 4

    def test_one_candidate(self):
        assert compute_num_rounds(1) == 0


class TestGeneratePairings:
    def test_eight_candidates_round1(self):
        clusters = _make_clusters(8)
        scores = _make_scores(8)
        candidates = init_candidates(clusters, scores)
        pairings = generate_pairings(candidates, round_num=1)

        assert len(pairings) == 4
        all_ids = [cid for pair in pairings for cid in pair]
        assert len(set(all_ids)) == 8

    def test_no_rematch(self):
        clusters = _make_clusters(4)
        scores = _make_scores(4)
        candidates = init_candidates(clusters, scores)

        round1_pairs = generate_pairings(candidates, round_num=1)
        for id_a, id_b in round1_pairs:
            for c in candidates:
                if c.id == id_a:
                    c.opponents.append(id_b)
                elif c.id == id_b:
                    c.opponents.append(id_a)

        round2_pairs = generate_pairings(candidates, round_num=2)
        r1_sets = [frozenset(p) for p in round1_pairs]
        r2_sets = [frozenset(p) for p in round2_pairs]
        for s in r2_sets:
            assert s not in r1_sets

    def test_odd_candidates_bye(self):
        clusters = _make_clusters(5)
        scores = _make_scores(5)
        candidates = init_candidates(clusters, scores)
        pairings = generate_pairings(candidates, round_num=1)

        assert len(pairings) == 2
        all_ids = [cid for pair in pairings for cid in pair]
        assert len(set(all_ids)) == 4


class TestApplyMatchResult:
    def test_winner_gains_elo(self):
        clusters = _make_clusters(2)
        scores = _make_scores(2)
        candidates = init_candidates(clusters, scores)

        match = MatchRecord(
            round=1,
            pair_id=1,
            item_a_id="cluster_1",
            item_b_id="cluster_2",
            winner_id="cluster_1",
            reason="Better alignment.",
            source="AI judgment",
        )
        apply_match_result(candidates, match)

        winner = next(c for c in candidates if c.id == "cluster_1")
        loser = next(c for c in candidates if c.id == "cluster_2")

        assert winner.elo > 1200.0
        assert loser.elo < 1200.0
        assert winner.wins == 1
        assert loser.losses == 1


class TestEarlyStopping:
    def test_early_stopping_on_budget_exhaustion(self):
        clusters = _make_clusters(4)
        scores = _make_scores(4)
        candidates = init_candidates(clusters, scores)

        budget = JobBudget(max_llm_requests=1)
        budget.record_usage(input_tokens=100, output_tokens=20)

        stopped, reason = check_early_stopping(
            round_num=2,
            total_rounds=3,
            candidates=candidates,
            previous_top_ids=[],
            budget=budget,
        )
        assert stopped is True
        assert "Budget ceiling" in reason

    def test_early_stopping_on_stable_ranking(self):
        clusters = _make_clusters(4)
        scores = _make_scores(4)
        candidates = init_candidates(clusters, scores)
        candidates[0].elo = 1350.0  # Decisive margin
        candidates[1].elo = 1220.0

        budget = JobBudget(max_llm_requests=10)
        previous_top_ids = [candidates[0].id, candidates[1].id, candidates[2].id]

        stopped, reason = check_early_stopping(
            round_num=3,
            total_rounds=4,
            candidates=candidates,
            previous_top_ids=previous_top_ids,
            budget=budget,
        )
        assert stopped is True
        assert "stabilized" in reason


class TestRankAndTiers:
    def test_rank_by_elo(self):
        clusters = _make_clusters(3)
        scores = _make_scores(3)
        candidates = init_candidates(clusters, scores)

        candidates[0].elo = 1250
        candidates[1].elo = 1200
        candidates[2].elo = 1150

        ranked = rank_candidates(candidates)
        assert ranked[0].id == "cluster_1"
        assert ranked[-1].id == "cluster_3"

    def test_tiers_assigned(self):
        clusters = _make_clusters(6)
        scores = _make_scores(6)
        candidates = init_candidates(clusters, scores)

        for i, c in enumerate(candidates):
            c.elo = 1300 - i * 20

        ranked = rank_candidates(candidates)
        tiered = assign_tiers(ranked)

        assert tiered[0].tier == "Now"
        assert any(c.tier == "Next" for c in tiered)
        assert any(c.tier == "Later" for c in tiered)
