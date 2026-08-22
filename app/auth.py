"""Authentication and per-user rate limiting for EloJudge."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Daily run limits when using server key
ANONYMOUS_DAILY_LIMIT = 0
GOOGLE_USER_DAILY_LIMIT = 5
WINDOW_SECONDS = 86400  # 24 hours


@dataclass
class UserUsage:
    """Tracks runs within sliding time window."""

    timestamps: list[float] = field(default_factory=list)

    def clean_old(self, now: float) -> None:
        """Remove timestamps older than window."""
        cutoff = now - WINDOW_SECONDS
        self.timestamps = [t for t in self.timestamps if t > cutoff]

    @property
    def count(self) -> int:
        now = time.time()
        self.clean_old(now)
        return len(self.timestamps)

    def record_run(self) -> None:
        self.timestamps.append(time.time())


class RateLimiter:
    """In-memory per-user and per-IP rate limiter."""

    def __init__(self) -> None:
        self._ip_usage: dict[str, UserUsage] = {}
        self._user_usage: dict[str, UserUsage] = {}

    def get_remaining(self, identifier: str, is_google_user: bool = False, has_custom_key: bool = False) -> int:
        """Return remaining free server runs for the identifier."""
        if has_custom_key:
            return 9999  # Unlimited with BYOK
        if not is_google_user:
            return 0  # Login required

        usage = self._user_usage.setdefault(identifier, UserUsage())
        return max(0, GOOGLE_USER_DAILY_LIMIT - usage.count)

    def check_and_record(
        self,
        identifier: str,
        is_google_user: bool = False,
        has_custom_key: bool = False,
    ) -> tuple[bool, int, str]:
        """Check if request is allowed. If allowed, record usage.

        Returns:
            (allowed, remaining_runs, message)
        """
        if has_custom_key:
            return True, 9999, "Custom Gemini API Key active (unlimited runs)."

        if not is_google_user:
            return (
                False,
                0,
                "Sign-in required: Please sign in with your Google account (top right) or add your Gemini API Key in Settings (🔑) to prioritize feedback.",
            )

        usage = self._user_usage.setdefault(identifier, UserUsage())

        if usage.count >= GOOGLE_USER_DAILY_LIMIT:
            msg = (
                f"Daily limit reached ({GOOGLE_USER_DAILY_LIMIT}/{GOOGLE_USER_DAILY_LIMIT} runs for your Google account). "
                "Add your own free Gemini API key in Settings (🔑) for unlimited runs."
            )
            return False, 0, msg

        usage.record_run()
        remaining = max(0, GOOGLE_USER_DAILY_LIMIT - usage.count)
        return True, remaining, "OK"


rate_limiter = RateLimiter()


async def verify_google_id_token(token: str) -> Optional[dict]:
    """Verify Google OAuth ID Token via Google tokeninfo API."""
    if not token or len(token) < 20:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={token}")
            if resp.status_code == 200:
                data = resp.json()
                if "email" in data:
                    return {
                        "email": data.get("email"),
                        "name": data.get("name", data.get("email")),
                        "picture": data.get("picture", ""),
                        "sub": data.get("sub", ""),
                    }
    except Exception as e:
        logger.warning("Google token verification failed: %s", e)

    return None
