"""Unit tests for the RateLimiter service."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.services.rate_limiter import RateLimiter


@pytest.fixture
def limiter():
    return RateLimiter()


class TestCheckAndIncrement:
    """Tests for check_and_increment."""

    @pytest.mark.asyncio
    async def test_first_request_allowed(self, limiter):
        result = await limiter.check_and_increment("user-1", max_per_day=10)
        assert result.allowed is True
        assert result.current_count == 1
        assert result.max_per_day == 10

    @pytest.mark.asyncio
    async def test_increments_count(self, limiter):
        await limiter.check_and_increment("user-1", max_per_day=10)
        result = await limiter.check_and_increment("user-1", max_per_day=10)
        assert result.current_count == 2

    @pytest.mark.asyncio
    async def test_rejects_at_limit(self, limiter):
        for _ in range(5):
            await limiter.check_and_increment("user-1", max_per_day=5)

        result = await limiter.check_and_increment("user-1", max_per_day=5)
        assert result.allowed is False
        assert result.current_count == 5

    @pytest.mark.asyncio
    async def test_different_users_independent(self, limiter):
        for _ in range(5):
            await limiter.check_and_increment("user-a", max_per_day=5)

        result = await limiter.check_and_increment("user-b", max_per_day=5)
        assert result.allowed is True
        assert result.current_count == 1

    @pytest.mark.asyncio
    async def test_resets_at_contains_future_datetime(self, limiter):
        result = await limiter.check_and_increment("user-1", max_per_day=10)
        assert result.resets_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_daily_reset(self, limiter):
        """Counts reset when the date changes."""
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        # Fill up today
        for _ in range(3):
            await limiter.check_and_increment("user-1", max_per_day=3)

        # Simulate date change
        with patch.object(RateLimiter, "_today", return_value=tomorrow):
            result = await limiter.check_and_increment("user-1", max_per_day=3)
            assert result.allowed is True
            assert result.current_count == 1


class TestGetRemaining:
    """Tests for get_remaining."""

    @pytest.mark.asyncio
    async def test_full_remaining(self, limiter):
        remaining = await limiter.get_remaining("user-1", max_per_day=10)
        assert remaining == 10

    @pytest.mark.asyncio
    async def test_decrements_after_use(self, limiter):
        await limiter.check_and_increment("user-1", max_per_day=10)
        await limiter.check_and_increment("user-1", max_per_day=10)
        remaining = await limiter.get_remaining("user-1", max_per_day=10)
        assert remaining == 8

    @pytest.mark.asyncio
    async def test_never_negative(self, limiter):
        for _ in range(12):
            await limiter.check_and_increment("user-1", max_per_day=10)
        remaining = await limiter.get_remaining("user-1", max_per_day=10)
        assert remaining == 0


class TestGetResetTime:
    """Tests for get_reset_time."""

    @pytest.mark.asyncio
    async def test_returns_future_datetime(self, limiter):
        reset = await limiter.get_reset_time("user-1")
        assert isinstance(reset, datetime)
        assert reset > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_reset_is_midnight_tomorrow(self, limiter):
        reset = await limiter.get_reset_time("user-1")
        tomorrow = date.today() + timedelta(days=1)
        assert reset.year == tomorrow.year
        assert reset.month == tomorrow.month
        assert reset.day == tomorrow.day
        assert reset.hour == 0
        assert reset.minute == 0
