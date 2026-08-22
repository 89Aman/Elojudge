"""Tests for obvious-pair router and model selection."""

import pytest
from app.router import check_obvious_pair, select_model_for_pair
from app.schemas import CandidateState


def _make_candidate(cid: str, text: str, score: float, severity: str = "medium") -> CandidateState:
    return CandidateState(
        id=cid,
        text=text,
        local_pre_rank=score,
        severity=severity,
    )


class TestRouter:
    def test_obvious_pair_severity_disparity(self):
        cand_a = _make_candidate("c1", "App crashes on start", 0.6, severity="critical")
        cand_b = _make_candidate("c2", "Change dark mode icon", 0.5, severity="low")

        is_obvious, winner_id, reason = check_obvious_pair(cand_a, cand_b)
        assert is_obvious is True
        assert winner_id == "c1"
        assert "Critical issue" in reason

    def test_obvious_pair_large_pre_rank_margin(self):
        cand_a = _make_candidate("c1", "Search filters", 0.9, severity="medium")
        cand_b = _make_candidate("c2", "Minor font tweak", 0.4, severity="medium")

        is_obvious, winner_id, reason = check_obvious_pair(cand_a, cand_b, margin=0.35)
        assert is_obvious is True
        assert winner_id == "c1"

    def test_non_obvious_pair(self):
        cand_a = _make_candidate("c1", "Search filters", 0.70, severity="medium")
        cand_b = _make_candidate("c2", "Folder organization", 0.65, severity="medium")

        is_obvious, winner_id, reason = check_obvious_pair(cand_a, cand_b, margin=0.35)
        assert is_obvious is False
        assert winner_id is None

    def test_model_routing_escalates_on_critical(self):
        cand_a = _make_candidate("c1", "Security leak", 0.8, severity="critical")
        cand_b = _make_candidate("c2", "PDF export", 0.7, severity="medium")

        model = select_model_for_pair(cand_a, cand_b)
        assert model is not None
