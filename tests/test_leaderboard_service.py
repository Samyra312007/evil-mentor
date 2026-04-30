"""Unit tests for the LeaderboardService."""

import time
from datetime import datetime, timezone
from uuid import uuid4

import aiosqlite
import pytest
import pytest_asyncio

from src.database.connection import Database
from src.database.migrations import run_migrations
from src.database.repositories import (
    GradeRepository,
    LeaderboardRepository,
    SessionRepository,
    UserRepository,
)
from src.models.domain import (
    DifficultyLevel,
    GradeRecord,
    LeaderboardEntry,
    LetterGrade,
    PlatformType,
    SessionStatus,
    TrainingSession,
    User,
    VulnerabilityType,
)
from src.services.leaderboard_service import LeaderboardService


@pytest_asyncio.fixture
async def db():
    """Create an in-memory SQLite database with schema."""
    database = Database("sqlite:///:memory:")
    conn = await database.connect()
    await run_migrations(conn)
    yield conn
    await database.close()


@pytest_asyncio.fixture
async def repos(db):
    """Create all repository instances."""
    return {
        "leaderboard": LeaderboardRepository(db),
        "user": UserRepository(db),
        "grade": GradeRepository(db),
        "session": SessionRepository(db),
    }


@pytest_asyncio.fixture
async def service(repos):
    """Create a LeaderboardService instance."""
    return LeaderboardService(
        leaderboard_repo=repos["leaderboard"],
        user_repo=repos["user"],
        grade_repo=repos["grade"],
        session_repo=repos["session"],
    )


async def _create_user(user_repo: UserRepository, username: str = "testuser") -> User:
    """Helper to create and persist a user."""
    user = User(
        id=uuid4(),
        platform_id=f"plat-{username}",
        platform_type=PlatformType.TELEGRAM,
        username=username,
        display_name=username.title(),
    )
    await user_repo.create(user)
    return user


async def _create_graded_session(
    session_repo: SessionRepository,
    grade_repo: GradeRepository,
    user_id,
    score: int,
    graded_at: datetime | None = None,
) -> tuple[TrainingSession, GradeRecord]:
    """Helper to create a graded session with a grade record."""
    if graded_at is None:
        graded_at = datetime.now(timezone.utc)

    session = TrainingSession(
        id=uuid4(),
        user_id=user_id,
        intent_id="intent-test",
        repo_path="/tmp/repo",
        branch_name="evil-mentor/session-test",
        difficulty=DifficultyLevel.MEDIUM,
        status=SessionStatus.GRADED,
        injected_at=graded_at,
        graded_at=graded_at,
    )
    await session_repo.create(session)

    grade = GradeRecord(
        id=uuid4(),
        session_id=session.id,
        score=score,
        letter_grade=LetterGrade.B,
        speed_bonus=10,
        missed_penalty=5,
        fp_penalty=3,
        feedback="Good job",
        created_at=graded_at,
    )
    await grade_repo.create(grade)

    return session, grade


class TestUpdateAfterGrading:
    """Tests for update_after_grading."""

    @pytest.mark.asyncio
    async def test_first_session_creates_entry(self, service, repos):
        user = await _create_user(repos["user"])

        await service.update_after_grading(
            user_id=user.id,
            session_score=80,
            vuln_types_missed=["SQL_INJECTION"],
        )

        entry = await repos["leaderboard"].get_by_user(user.id)
        assert entry is not None
        assert entry.total_score == 80
        assert entry.sessions_completed == 1
        assert entry.avg_score == 80.0
        assert entry.best_score == 80
        assert entry.weakest_area == VulnerabilityType.SQL_INJECTION

    @pytest.mark.asyncio
    async def test_second_session_updates_cumulative(self, service, repos):
        user = await _create_user(repos["user"])

        await service.update_after_grading(
            user_id=user.id,
            session_score=80,
            vuln_types_missed=["SQL_INJECTION"],
        )
        await service.update_after_grading(
            user_id=user.id,
            session_score=60,
            vuln_types_missed=["XSS"],
        )

        entry = await repos["leaderboard"].get_by_user(user.id)
        assert entry is not None
        assert entry.total_score == 140
        assert entry.sessions_completed == 2
        assert entry.avg_score == 70.0
        assert entry.best_score == 80

    @pytest.mark.asyncio
    async def test_best_score_updates_when_higher(self, service, repos):
        user = await _create_user(repos["user"])

        await service.update_after_grading(user.id, 50, [])
        await service.update_after_grading(user.id, 90, [])

        entry = await repos["leaderboard"].get_by_user(user.id)
        assert entry.best_score == 90

    @pytest.mark.asyncio
    async def test_best_score_preserved_when_lower(self, service, repos):
        user = await _create_user(repos["user"])

        await service.update_after_grading(user.id, 90, [])
        await service.update_after_grading(user.id, 50, [])

        entry = await repos["leaderboard"].get_by_user(user.id)
        assert entry.best_score == 90

    @pytest.mark.asyncio
    async def test_no_missed_types_preserves_weakest(self, service, repos):
        user = await _create_user(repos["user"])

        await service.update_after_grading(user.id, 80, ["XSS"])
        await service.update_after_grading(user.id, 90, [])

        entry = await repos["leaderboard"].get_by_user(user.id)
        assert entry.weakest_area == VulnerabilityType.XSS

    @pytest.mark.asyncio
    async def test_unknown_user_logs_warning(self, service):
        """Updating a non-existent user should not raise."""
        fake_id = uuid4()
        # Should not raise
        await service.update_after_grading(fake_id, 50, [])

    @pytest.mark.asyncio
    async def test_recalculates_ranks(self, service, repos):
        user_a = await _create_user(repos["user"], "alice")
        user_b = await _create_user(repos["user"], "bob")

        await service.update_after_grading(user_a.id, 50, [])
        await service.update_after_grading(user_b.id, 100, [])

        entry_a = await repos["leaderboard"].get_by_user(user_a.id)
        entry_b = await repos["leaderboard"].get_by_user(user_b.id)

        assert entry_b.rank < entry_a.rank  # bob ranked higher
        assert entry_b.rank == 1
        assert entry_a.rank == 2

    @pytest.mark.asyncio
    async def test_invalidates_cache(self, service, repos):
        user = await _create_user(repos["user"])

        # Populate cache
        await service.get_leaderboard(limit=50)

        await service.update_after_grading(user.id, 80, [])

        # Cache should be cleared
        assert len(service._cache) == 0


class TestGetLeaderboard:
    """Tests for get_leaderboard."""

    @pytest.mark.asyncio
    async def test_empty_leaderboard(self, service):
        entries = await service.get_leaderboard(limit=10)
        assert entries == []

    @pytest.mark.asyncio
    async def test_returns_sorted_by_total_score_desc(self, service, repos):
        user_a = await _create_user(repos["user"], "alice")
        user_b = await _create_user(repos["user"], "bob")
        user_c = await _create_user(repos["user"], "charlie")

        await service.update_after_grading(user_a.id, 50, [])
        await service.update_after_grading(user_b.id, 100, [])
        await service.update_after_grading(user_c.id, 75, [])

        entries = await service.get_leaderboard(limit=10)

        assert len(entries) == 3
        assert entries[0].total_score == 100
        assert entries[1].total_score == 75
        assert entries[2].total_score == 50

    @pytest.mark.asyncio
    async def test_ranks_are_1_based_positions(self, service, repos):
        user_a = await _create_user(repos["user"], "alice")
        user_b = await _create_user(repos["user"], "bob")

        await service.update_after_grading(user_a.id, 50, [])
        await service.update_after_grading(user_b.id, 100, [])

        entries = await service.get_leaderboard(limit=10)

        for idx, entry in enumerate(entries):
            assert entry.rank == idx + 1

    @pytest.mark.asyncio
    async def test_respects_limit(self, service, repos):
        for i in range(5):
            user = await _create_user(repos["user"], f"user{i}")
            await service.update_after_grading(user.id, (i + 1) * 10, [])

        entries = await service.get_leaderboard(limit=3)
        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_caching_returns_same_result(self, service, repos):
        user = await _create_user(repos["user"])
        await service.update_after_grading(user.id, 80, [])

        first = await service.get_leaderboard(limit=50)
        second = await service.get_leaderboard(limit=50)

        assert first == second
        # Cache should have an entry
        assert "leaderboard:50" in service._cache

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self, service, repos):
        user = await _create_user(repos["user"])
        await service.update_after_grading(user.id, 80, [])

        # Fetch to populate cache
        await service.get_leaderboard(limit=50)

        # Manually expire the cache
        cache_key = "leaderboard:50"
        entries, _ = service._cache[cache_key]
        service._cache[cache_key] = (entries, time.monotonic() - 301)

        # This should fetch from DB again (not from expired cache)
        result = await service.get_leaderboard(limit=50)
        assert len(result) == 1


class TestGetUserStats:
    """Tests for get_user_stats."""

    @pytest.mark.asyncio
    async def test_returns_zeroed_stats_for_new_user(self, service):
        stats = await service.get_user_stats(uuid4())
        assert stats.total_score == 0
        assert stats.sessions_completed == 0
        assert stats.avg_score == 0.0
        assert stats.best_score == 0
        assert stats.weakest_area is None
        assert stats.rank == 0

    @pytest.mark.asyncio
    async def test_returns_correct_stats(self, service, repos):
        user = await _create_user(repos["user"])
        await service.update_after_grading(user.id, 80, ["SQL_INJECTION"])
        await service.update_after_grading(user.id, 60, ["XSS"])

        stats = await service.get_user_stats(user.id)

        assert stats.user_id == user.id
        assert stats.total_score == 140
        assert stats.sessions_completed == 2
        assert stats.avg_score == 70.0
        assert stats.best_score == 80
        assert stats.rank >= 1


class TestGetWeeklyStats:
    """Tests for get_weekly_stats."""

    @pytest.mark.asyncio
    async def test_empty_week(self, service):
        stats = await service.get_weekly_stats()
        assert stats.total_sessions == 0
        assert stats.avg_score == 0.0
        assert stats.top_performer is None

    @pytest.mark.asyncio
    async def test_counts_sessions_this_week(self, service, repos):
        user = await _create_user(repos["user"], "alice")
        await service.update_after_grading(user.id, 80, [])

        now = datetime.now(timezone.utc)
        await _create_graded_session(
            repos["session"], repos["grade"], user.id, 80, graded_at=now
        )

        stats = await service.get_weekly_stats()
        assert stats.total_sessions == 1
        assert stats.avg_score == 80.0
        assert stats.top_performer == "alice"

    @pytest.mark.asyncio
    async def test_multiple_users_top_performer(self, service, repos):
        alice = await _create_user(repos["user"], "alice")
        bob = await _create_user(repos["user"], "bob")

        await service.update_after_grading(alice.id, 80, [])
        await service.update_after_grading(bob.id, 100, [])

        now = datetime.now(timezone.utc)
        await _create_graded_session(
            repos["session"], repos["grade"], alice.id, 80, graded_at=now
        )
        await _create_graded_session(
            repos["session"], repos["grade"], bob.id, 100, graded_at=now
        )

        stats = await service.get_weekly_stats()
        assert stats.total_sessions == 2
        assert stats.avg_score == 90.0
        assert stats.top_performer == "bob"


class TestDetermineWeakestArea:
    """Tests for the _determine_weakest_area static method."""

    def test_no_missed_preserves_current(self):
        result = LeaderboardService._determine_weakest_area(
            VulnerabilityType.XSS, []
        )
        assert result == VulnerabilityType.XSS

    def test_no_missed_no_current_returns_none(self):
        result = LeaderboardService._determine_weakest_area(None, [])
        assert result is None

    def test_single_missed_type(self):
        result = LeaderboardService._determine_weakest_area(
            None, ["SQL_INJECTION"]
        )
        assert result == VulnerabilityType.SQL_INJECTION

    def test_most_frequent_missed_wins(self):
        result = LeaderboardService._determine_weakest_area(
            None, ["SQL_INJECTION", "XSS", "SQL_INJECTION"]
        )
        assert result == VulnerabilityType.SQL_INJECTION

    def test_unknown_type_preserves_current(self):
        result = LeaderboardService._determine_weakest_area(
            VulnerabilityType.XSS, ["UNKNOWN_TYPE"]
        )
        assert result == VulnerabilityType.XSS
