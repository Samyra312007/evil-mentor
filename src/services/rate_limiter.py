"""In-memory rate limiter for training sessions.

Uses a dict with date-based keys for automatic daily reset.
Designed as a zero-dependency MVP replacement for Redis-backed
rate limiting described in the design document.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from src.models.domain import RateLimitResult

logger = logging.getLogger(__name__)


class RateLimiter:
    """In-memory rate limiter with daily reset.

    Tracks the number of training sessions per user per day using
    an in-memory dictionary keyed by ``(user_id, date)``.  Entries
    for past dates are lazily cleaned up on access.
    """

    def __init__(self) -> None:
        # Mapping of (user_id, date_str) -> count
        self._counts: dict[tuple[str, str], int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_and_increment(
        self, user_id: str, max_per_day: int
    ) -> RateLimitResult:
        """Check if the user is within the daily limit and increment if allowed.

        Args:
            user_id: Unique identifier for the user.
            max_per_day: Maximum allowed sessions per day.

        Returns:
            A ``RateLimitResult`` indicating whether the request is allowed,
            the current count, the configured maximum, and when the limit resets.
        """
        today = self._today()
        key = (user_id, today)
        current = self._counts.get(key, 0)
        resets_at = self._next_reset_time()

        if current >= max_per_day:
            logger.info(
                "Rate limit exceeded for user %s: %d/%d (resets at %s)",
                user_id,
                current,
                max_per_day,
                resets_at.isoformat(),
            )
            return RateLimitResult(
                allowed=False,
                current_count=current,
                max_per_day=max_per_day,
                resets_at=resets_at,
            )

        self._counts[key] = current + 1
        self._cleanup_old_entries(user_id)

        logger.debug(
            "Rate limit check passed for user %s: %d/%d",
            user_id,
            current + 1,
            max_per_day,
        )
        return RateLimitResult(
            allowed=True,
            current_count=current + 1,
            max_per_day=max_per_day,
            resets_at=resets_at,
        )

    async def get_remaining(self, user_id: str, max_per_day: int) -> int:
        """Return the number of sessions the user has left today.

        Args:
            user_id: Unique identifier for the user.
            max_per_day: Maximum allowed sessions per day.

        Returns:
            Non-negative integer of remaining allowed sessions.
        """
        today = self._today()
        current = self._counts.get((user_id, today), 0)
        return max(0, max_per_day - current)

    async def get_reset_time(self, user_id: str) -> datetime:
        """Return when the rate limit resets for this user.

        The limit resets at midnight UTC of the next day, regardless
        of whether the user has any recorded activity.

        Args:
            user_id: Unique identifier for the user (unused in the
                current implementation but kept for interface parity
                with a future Redis-backed version).

        Returns:
            A timezone-aware ``datetime`` for the next reset.
        """
        return self._next_reset_time()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _today() -> str:
        """Return today's date as an ISO-format string (UTC)."""
        return date.today().isoformat()

    @staticmethod
    def _next_reset_time() -> datetime:
        """Return midnight UTC of the next day."""
        tomorrow = date.today() + timedelta(days=1)
        return datetime(
            tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone.utc
        )

    def _cleanup_old_entries(self, user_id: str) -> None:
        """Remove entries for past dates to prevent unbounded memory growth."""
        today = self._today()
        stale_keys = [
            k for k in self._counts if k[0] == user_id and k[1] != today
        ]
        for k in stale_keys:
            del self._counts[k]
