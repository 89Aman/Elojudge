"""Tests for Elo rating calculations."""

import pytest

from app.tournament import compute_elo_update, K_FACTOR, INITIAL_ELO


class TestEloUpdate:
    def test_equal_ratings_winner_gains(self):
        new_a, new_b = compute_elo_update(1200, 1200, a_wins=True)
        assert new_a > 1200
        assert new_b < 1200

    def test_equal_ratings_symmetric(self):
        new_a, new_b = compute_elo_update(1200, 1200, a_wins=True)
        gain = new_a - 1200
        loss = 1200 - new_b
        assert abs(gain - loss) < 0.01  # symmetric

    def test_equal_ratings_gain_is_half_k(self):
        new_a, _ = compute_elo_update(1200, 1200, a_wins=True)
        expected_gain = K_FACTOR / 2  # K * (1 - 0.5) = K/2
        actual_gain = new_a - 1200
        assert abs(actual_gain - expected_gain) < 0.01

    def test_underdog_win_larger_gain(self):
        """Lower-rated player wins → larger Elo gain."""
        # Underdog (1100) beats favorite (1300)
        new_underdog, new_fav = compute_elo_update(1100, 1300, a_wins=True)
        underdog_gain = new_underdog - 1100

        # Expected win: equal ratings
        new_equal, _ = compute_elo_update(1200, 1200, a_wins=True)
        equal_gain = new_equal - 1200

        assert underdog_gain > equal_gain

    def test_favorite_win_smaller_gain(self):
        """Higher-rated player wins → smaller Elo gain."""
        new_fav, new_underdog = compute_elo_update(1300, 1100, a_wins=True)
        fav_gain = new_fav - 1300

        new_equal, _ = compute_elo_update(1200, 1200, a_wins=True)
        equal_gain = new_equal - 1200

        assert fav_gain < equal_gain

    def test_ratings_conserved(self):
        """Total Elo is conserved (zero-sum)."""
        new_a, new_b = compute_elo_update(1250, 1150, a_wins=True)
        assert abs((new_a + new_b) - (1250 + 1150)) < 0.01

    def test_b_wins(self):
        new_a, new_b = compute_elo_update(1200, 1200, a_wins=False)
        assert new_a < 1200
        assert new_b > 1200

    def test_large_gap(self):
        """Very high rated vs very low rated — expected values near 0/1."""
        new_a, new_b = compute_elo_update(1600, 800, a_wins=True)
        # Favorite wins, very small gain
        gain = new_a - 1600
        assert gain < 2.0  # nearly expected win

    def test_initial_elo_constant(self):
        assert INITIAL_ELO == 1200.0

    def test_k_factor_constant(self):
        assert K_FACTOR == 24
