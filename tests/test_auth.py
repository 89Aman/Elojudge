"""Unit tests for auth and rate limiting."""

from app.auth import RateLimiter


class TestRateLimiter:
    def test_anonymous_blocked_without_login(self):
        limiter = RateLimiter()
        ip = "192.168.1.100"

        # Anonymous has 0 free runs without login or BYOK key
        assert limiter.get_remaining(ip, is_google_user=False) == 0
        allowed, rem, msg = limiter.check_and_record(ip, is_google_user=False)
        assert allowed is False
        assert rem == 0
        assert "Sign-in required" in msg

    def test_google_user_limit(self):
        limiter = RateLimiter()
        email = "student@example.com"

        # Allowed 5 runs
        assert limiter.get_remaining(email, is_google_user=True) == 5
        for i in range(5):
            allowed, _, _ = limiter.check_and_record(email, is_google_user=True)
            assert allowed is True

        # 6th run blocked
        allowed, _, msg = limiter.check_and_record(email, is_google_user=True)
        assert allowed is False
        assert "5/5 runs" in msg

    def test_custom_key_unlimited(self):
        limiter = RateLimiter()
        ip = "192.168.1.1"

        # Custom key always unlimited
        assert limiter.get_remaining(ip, has_custom_key=True) == 9999
        for _ in range(10):
            allowed, rem, _ = limiter.check_and_record(ip, has_custom_key=True)
            assert allowed is True
            assert rem == 9999
