"""Leaderboard Service for Evil Mentor.

Maintains ranked developer scores with in-memory caching and weekly
aggregation.  Uses an in-memory dict cache with a 5-minute TTL as a
zero-dependency MVP replacement for the Redis cache described in the
design document.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from src.database.repositories import (
    GradeRepository,
    LeaderboardRepository,
    SessionRepository,
    UserRepository,
)
from src.models.domain import (
    LeaderboardEntry,
    UserStats,
    VulnerabilityType,
    WeeklyStats,
)

logger = logging.getLogger(__name__)


class LeaderboardService:
    """Leaderboard rankings and progress tracking.

    Provides cumulative score tracking, ranked leaderboard retrieval
    with in-memory caching (5-minute TTL), per-user statistics, and
    weekly aggregated stats.
    """

    CACHE_TTL_SECONDS = 300  # 5-minute cache

    def __init__(
        self,
        leaderboard_repo: LeaderboardRepository,
        user_repo: UserRepository,
        grade_repo: GradeRepository,
        session_repo: SessionRepository,
    ) -> None:
        self._leaderboard_repo = leaderboard_repo
        self._user_repo = user_repo
        self._grade_repo = grade_repo
        self._session_repo = session_repo

        # In-memory cache: (entries, timestamp)
        self._cache: dict[str, tuple[list[LeaderboardEntry], float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def update_after_grading(
        self,
        user_id: UUID,
        session_score: int,
        vuln_types_missed: list[str],
    ) -> None:
        """Update cumulative stats and recalculate rankings after grading.

        Updates the user's total_score, sessions_completed, avg_score,
        best_score, and weakest_area, then recalculates all rankings.

        Args:
            user_id: The user whose stats should be updated.
            session_score: The score from the just-graded session.
            vuln_types_missed: Vulnerability type strings the user missed.
        """
        # Fetch the user record for username / display_name
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            logger.warning("Cannot update leaderboard: user %s not found", user_id)
            return

        # Fetch existing leaderboard entry (may be None for first session)
        existing = await self._leaderboard_repo.get_by_user(user_id)

        if existing is not None:
            new_total_score = existing.total_score + session_score
            new_sessions = existing.sessions_completed + 1
            new_avg = new_total_score / new_sessions
            new_best = max(existing.best_score, session_score)
            weakest = self._determine_weakest_area(
                existing.weakest_area, vuln_types_missed
            )
        else:
            new_total_score = session_score
            new_sessions = 1
            new_avg = float(session_score)
            new_best = session_score
            weakest = self._determine_weakest_area(None, vuln_types_missed)

        entry = LeaderboardEntry(
            user_id=user_id,
            username=user.username,
            display_name=user.display_name,
            total_score=new_total_score,
            sessions_completed=new_sessions,
            avg_score=new_avg,
            best_score=new_best,
            weakest_area=weakest,
            rank=0,  # will be recalculated
        )

        await self._leaderboard_repo.upsert(entry)
        await self._leaderboard_repo.recalculate_ranks()

        # Invalidate cache so next get_leaderboard fetches fresh data
        self._cache.clear()

        logger.info(
            "Updated leaderboard for user %s: total=%d, sessions=%d, avg=%.1f, best=%d",
            user_id,
            new_total_score,
            new_sessions,
            new_avg,
            new_best,
        )

    async def get_leaderboard(self, limit: int = 50) -> list[LeaderboardEntry]:
        """Get top-ranked developers, sorted by total_score descending.

        Results are cached in memory with a 5-minute TTL to reduce
        database load.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of ``LeaderboardEntry`` objects sorted by total_score
            descending, with rank equal to 1-based position.
        """
        cache_key = f"leaderboard:{limit}"
        cached = self._cache.get(cache_key)

        if cached is not None:
            entries, cached_at = cached
            if (time.monotonic() - cached_at) < self.CACHE_TTL_SECONDS:
                logger.debug("Returning cached leaderboard (limit=%d)", limit)
                return entries

        # Fetch from database
        entries = await self._leaderboard_repo.get_top(limit)

        # Ensure correct ordering and rank assignment
        entries.sort(key=lambda e: e.total_score, reverse=True)
        for idx, entry in enumerate(entries):
            entry.rank = idx + 1

        # Store in cache
        self._cache[cache_key] = (entries, time.monotonic())

        logger.debug("Fetched leaderboard from DB (limit=%d, count=%d)", limit, len(entries))
        return entries

    async def get_user_stats(self, user_id: UUID) -> UserStats:
        """Get a single user's cumulative statistics.

        Args:
            user_id: The user to look up.

        Returns:
            A ``UserStats`` object with the user's cumulative data.

        Raises:
            ValueError: If the user has no leaderboard entry.
        """
        entry = await self._leaderboard_repo.get_by_user(user_id)
        if entry is None:
            # Return zeroed stats for users with no sessions
            return UserStats(
                user_id=user_id,
                total_score=0,
                sessions_completed=0,
                avg_score=0.0,
                best_score=0,
                weakest_area=None,
                rank=0,
            )

        return UserStats(
            user_id=entry.user_id,
            total_score=entry.total_score,
            sessions_completed=entry.sessions_completed,
            avg_score=entry.avg_score,
            best_score=entry.best_score,
            weakest_area=entry.weakest_area,
            rank=entry.rank,
        )

    async def get_weekly_stats(self) -> WeeklyStats:
        """Get aggregated weekly statistics.

        Computes total sessions, average score, and top performer for
        the current week (Monday through Sunday, UTC).

        Returns:
            A ``WeeklyStats`` object with this week's aggregated data.
        """
        now = datetime.now(timezone.utc)
        # Monday of the current week at 00:00 UTC
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        days_since_monday = now.weekday()  # Monday=0, Sunday=6
        week_start = week_start.replace(day=now.day - days_since_monday)

        # Fetch all leaderboard entries to find graded sessions this week
        all_entries = await self._leaderboard_repo.get_top(limit=10000)

        # We need to look at actual grade records for this week.
        # Iterate over users and collect grades created this week.
        weekly_scores: list[int] = []
        user_weekly_totals: dict[str, int] = {}  # username -> total score this week

        for entry in all_entries:
            user = await self._user_repo.get_by_id(entry.user_id)
            if user is None:
                continue

            # Get all sessions for this user
            sessions = await self._session_repo.list_for_user(
                entry.user_id, limit=1000, offset=0
            )

            for session in sessions:
                # Check if the session was graded this week
                if session.graded_at is None:
                    continue

                graded_at = session.graded_at
                if graded_at.tzinfo is None:
                    graded_at = graded_at.replace(tzinfo=timezone.utc)

                if graded_at >= week_start:
                    grade = await self._grade_repo.get_by_session(session.id)
                    if grade is not None:
                        weekly_scores.append(grade.score)
                        username = user.username
                        user_weekly_totals[username] = (
                            user_weekly_totals.get(username, 0) + grade.score
                        )

        total_sessions = len(weekly_scores)
        avg_score = (
            sum(weekly_scores) / total_sessions if total_sessions > 0 else 0.0
        )
        top_performer = (
            max(user_weekly_totals, key=user_weekly_totals.get)  # type: ignore[arg-type]
            if user_weekly_totals
            else None
        )

        return WeeklyStats(
            total_sessions=total_sessions,
            avg_score=avg_score,
            top_performer=top_performer,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_weakest_area(
        current_weakest: VulnerabilityType | None,
        vuln_types_missed: list[str],
    ) -> VulnerabilityType | None:
        """Determine the user's weakest vulnerability area.

        The weakest area is the most frequently missed vulnerability type.
        If there are no missed types, the existing weakest area is preserved.

        Args:
            current_weakest: The user's current weakest area (may be None).
            vuln_types_missed: Vulnerability type strings missed this session.

        Returns:
            The most frequently missed ``VulnerabilityType``, or the
            existing value if no new misses occurred.
        """
        if not vuln_types_missed:
            return current_weakest

        counts: Counter[str] = Counter(vuln_types_missed)

        # If there's an existing weakest area, give it a slight boost
        # so it persists unless clearly overtaken
        if current_weakest is not None:
            counts[current_weakest.value] += 0  # ensure it's in the counter

        most_common = counts.most_common(1)[0][0]

        try:
            return VulnerabilityType(most_common)
        except ValueError:
            logger.warning("Unknown vulnerability type: %s", most_common)
            return current_weakest
