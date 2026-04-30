"""Unit tests for the MessageHandler."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.config import Settings
from src.core.grading_engine import GradingEngine
from src.core.injection_generator import InjectionGenerator
from src.core.vulnerability_engine import VulnerabilityEngine
from src.database.repositories import (
    GradeRepository,
    InjectionRepository,
    ScanResultRepository,
    SessionRepository,
    UserRepository,
)
from src.handlers.message_handler import MessageHandler
from src.models.domain import (
    ChatResponse,
    DifficultyLevel,
    GradeReport,
    InjectionManifest,
    InjectionRecord,
    LeaderboardEntry,
    LetterGrade,
    MatchedVuln,
    MissedVuln,
    PlatformType,
    RateLimitResult,
    ScanFinding,
    ScoreBreakdown,
    SessionStatus,
    TrainingSession,
    User,
    UserContext,
    UserStats,
    VulnerabilityType,
)
from src.services.armorclaw_service import ArmorClawService
from src.services.git_service import GitService
from src.services.leaderboard_service import LeaderboardService
from src.services.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_user(opt_out: bool = False) -> User:
    return User(
        id=uuid4(),
        platform_id="U123",
        platform_type=PlatformType.SLACK,
        username="testuser",
        display_name="Test User",
        opt_out=opt_out,
    )


def _make_user_context() -> UserContext:
    return UserContext(
        platform_id="U123",
        platform_type=PlatformType.SLACK,
        username="testuser",
        display_name="Test User",
    )


def _make_settings(**overrides) -> Settings:
    defaults = {
        "GEMINI_API_KEY": "test",
        "ARMORIQ_API_KEY": "test",
        "ARMORIQ_USER_ID": "test",
        "ARMORIQ_AGENT_ID": "test",
        "TRAINING_START_HOUR": 0,
        "TRAINING_END_HOUR": 24,
        "MAX_INJECTIONS_PER_DAY": 10,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _make_handler(
    settings: Settings | None = None,
    user: User | None = None,
) -> tuple[MessageHandler, dict[str, MagicMock | AsyncMock]]:
    """Create a MessageHandler with all dependencies mocked."""
    settings = settings or _make_settings()
    user = user or _make_user()

    mocks: dict[str, MagicMock | AsyncMock] = {}

    # Repositories
    user_repo = AsyncMock(spec=UserRepository)
    user_repo.get_by_platform_id = AsyncMock(return_value=user)
    user_repo.create = AsyncMock(return_value=user)
    user_repo.update = AsyncMock(return_value=user)
    mocks["user_repo"] = user_repo

    session_repo = AsyncMock(spec=SessionRepository)
    session_repo.create = AsyncMock()
    session_repo.get_latest_for_user = AsyncMock(return_value=None)
    session_repo.update = AsyncMock()
    mocks["session_repo"] = session_repo

    injection_repo = AsyncMock(spec=InjectionRepository)
    injection_repo.create_many = AsyncMock()
    injection_repo.get_by_session = AsyncMock(return_value=[])
    mocks["injection_repo"] = injection_repo

    scan_result_repo = AsyncMock(spec=ScanResultRepository)
    scan_result_repo.create = AsyncMock()
    mocks["scan_result_repo"] = scan_result_repo

    grade_repo = AsyncMock(spec=GradeRepository)
    grade_repo.create = AsyncMock()
    mocks["grade_repo"] = grade_repo

    # Services
    vuln_engine = AsyncMock(spec=VulnerabilityEngine)
    mocks["vuln_engine"] = vuln_engine

    injection_gen = MagicMock(spec=InjectionGenerator)
    injection_gen.apply_injections = AsyncMock()
    injection_gen.validate_manifest = MagicMock(return_value=True)
    mocks["injection_gen"] = injection_gen

    grading_engine = AsyncMock(spec=GradingEngine)
    mocks["grading_engine"] = grading_engine

    git_service = AsyncMock(spec=GitService)
    git_service.create_training_branch = AsyncMock(return_value="evil-mentor/session-test")
    git_service.commit_injections = AsyncMock(return_value="abc123")
    git_service.delete_training_branch = AsyncMock(return_value=True)
    mocks["git_service"] = git_service

    armorclaw = AsyncMock(spec=ArmorClawService)
    mock_token = MagicMock()
    mock_token.token_id = "test-token-id"
    armorclaw.capture_and_get_token = AsyncMock(return_value=mock_token)
    armorclaw.invoke_action = AsyncMock()
    mocks["armorclaw"] = armorclaw

    rate_limiter = AsyncMock(spec=RateLimiter)
    rate_limiter.check_and_increment = AsyncMock(
        return_value=RateLimitResult(
            allowed=True,
            current_count=1,
            max_per_day=10,
            resets_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        )
    )
    mocks["rate_limiter"] = rate_limiter

    leaderboard = AsyncMock(spec=LeaderboardService)
    leaderboard.get_leaderboard = AsyncMock(return_value=[])
    leaderboard.get_user_stats = AsyncMock(
        return_value=UserStats(
            user_id=user.id,
            total_score=0,
            sessions_completed=0,
            avg_score=0.0,
            best_score=0,
            weakest_area=None,
            rank=0,
        )
    )
    leaderboard.update_after_grading = AsyncMock()
    mocks["leaderboard"] = leaderboard

    handler = MessageHandler(
        settings=settings,
        vulnerability_engine=vuln_engine,
        injection_generator=injection_gen,
        grading_engine=grading_engine,
        git_service=git_service,
        armorclaw_service=armorclaw,
        rate_limiter=rate_limiter,
        leaderboard_service=leaderboard,
        user_repo=user_repo,
        session_repo=session_repo,
        injection_repo=injection_repo,
        scan_result_repo=scan_result_repo,
        grade_repo=grade_repo,
    )

    return handler, mocks


# ---------------------------------------------------------------------------
# Command dispatch tests
# ---------------------------------------------------------------------------

class TestHandleDispatch:
    """Tests for the top-level handle() dispatcher."""

    @pytest.mark.asyncio
    async def test_dispatch_unknown_command(self):
        handler, _ = _make_handler()
        resp = await handler.handle("foo", [], _make_user_context())
        assert "Unknown command" in resp.text
        # Req 1.7: help message lists all 5 commands
        assert "/train" in resp.text
        assert "/grade" in resp.text
        assert "/stats" in resp.text
        assert "/leaderboard" in resp.text
        assert "/optout" in resp.text

    @pytest.mark.asyncio
    async def test_dispatch_with_leading_slash(self):
        handler, mocks = _make_handler()
        # /stats should dispatch to handle_stats
        resp = await handler.handle("/stats", [], _make_user_context())
        mocks["leaderboard"].get_user_stats.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_case_insensitive(self):
        handler, mocks = _make_handler()
        resp = await handler.handle("STATS", [], _make_user_context())
        mocks["leaderboard"].get_user_stats.assert_awaited_once()


# ---------------------------------------------------------------------------
# /train tests
# ---------------------------------------------------------------------------

class TestHandleTrain:
    """Tests for handle_train."""

    @pytest.mark.asyncio
    async def test_train_no_args_returns_usage(self):
        handler, _ = _make_handler()
        resp = await handler.handle_train([], _make_user_context())
        assert "Usage" in resp.text

    @pytest.mark.asyncio
    async def test_train_invalid_difficulty(self):
        handler, _ = _make_handler()
        resp = await handler.handle_train(["/tmp/repo", "IMPOSSIBLE"], _make_user_context())
        assert "Invalid difficulty" in resp.text

    @pytest.mark.asyncio
    async def test_train_opted_out_user_rejected(self):
        user = _make_user(opt_out=True)
        handler, _ = _make_handler(user=user)
        resp = await handler.handle_train(["/tmp/repo"], _make_user_context())
        assert "opted out" in resp.text

    @pytest.mark.asyncio
    async def test_train_rate_limited(self):
        handler, mocks = _make_handler()
        mocks["rate_limiter"].check_and_increment = AsyncMock(
            return_value=RateLimitResult(
                allowed=False,
                current_count=10,
                max_per_day=10,
                resets_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            )
        )
        resp = await handler.handle_train(["/tmp/repo"], _make_user_context())
        assert "Daily limit" in resp.text

    @pytest.mark.asyncio
    async def test_train_outside_hours(self):
        settings = _make_settings(TRAINING_START_HOUR=0, TRAINING_END_HOUR=0)
        handler, _ = _make_handler(settings=settings)
        resp = await handler.handle_train(["/tmp/repo"], _make_user_context())
        assert "Training is only available" in resp.text

    @pytest.mark.asyncio
    async def test_train_armoriq_failure(self):
        handler, mocks = _make_handler()
        mocks["armorclaw"].capture_and_get_token = AsyncMock(
            side_effect=Exception("ArmorIQ down")
        )
        resp = await handler.handle_train(["/tmp/repo"], _make_user_context())
        assert "Policy verification failed" in resp.text


# ---------------------------------------------------------------------------
# /grade tests
# ---------------------------------------------------------------------------

class TestHandleGrade:
    """Tests for handle_grade."""

    @pytest.mark.asyncio
    async def test_grade_no_session(self):
        handler, mocks = _make_handler()
        mocks["session_repo"].get_latest_for_user = AsyncMock(return_value=None)
        resp = await handler.handle_grade(_make_user_context())
        assert "No training session found" in resp.text

    @pytest.mark.asyncio
    async def test_grade_armoriq_failure(self):
        handler, mocks = _make_handler()
        session = TrainingSession(
            user_id=uuid4(),
            intent_id="tok",
            repo_path="/tmp",
            branch_name="evil-mentor/session-x",
        )
        mocks["session_repo"].get_latest_for_user = AsyncMock(return_value=session)
        mocks["armorclaw"].capture_and_get_token = AsyncMock(
            side_effect=Exception("fail")
        )
        resp = await handler.handle_grade(_make_user_context())
        assert "Policy verification failed" in resp.text


# ---------------------------------------------------------------------------
# /stats tests
# ---------------------------------------------------------------------------

class TestHandleStats:
    """Tests for handle_stats."""

    @pytest.mark.asyncio
    async def test_stats_no_sessions(self):
        handler, _ = _make_handler()
        resp = await handler.handle_stats(_make_user_context())
        assert "No training sessions completed" in resp.text

    @pytest.mark.asyncio
    async def test_stats_with_data(self):
        user = _make_user()
        handler, mocks = _make_handler(user=user)
        mocks["leaderboard"].get_user_stats = AsyncMock(
            return_value=UserStats(
                user_id=user.id,
                total_score=150,
                sessions_completed=5,
                avg_score=30.0,
                best_score=50,
                weakest_area=VulnerabilityType.XSS,
                rank=3,
            )
        )
        resp = await handler.handle_stats(_make_user_context())
        assert "150" in resp.text
        assert "5" in resp.text
        assert "30.0" in resp.text
        assert "50" in resp.text
        assert "XSS" in resp.text


# ---------------------------------------------------------------------------
# /leaderboard tests
# ---------------------------------------------------------------------------

class TestHandleLeaderboard:
    """Tests for handle_leaderboard."""

    @pytest.mark.asyncio
    async def test_leaderboard_empty(self):
        handler, _ = _make_handler()
        resp = await handler.handle_leaderboard()
        assert "No leaderboard data" in resp.text

    @pytest.mark.asyncio
    async def test_leaderboard_with_entries(self):
        handler, mocks = _make_handler()
        entries = [
            LeaderboardEntry(
                user_id=uuid4(),
                username="alice",
                display_name="Alice",
                total_score=200,
                sessions_completed=10,
                avg_score=20.0,
                best_score=40,
                weakest_area=None,
                rank=1,
            ),
            LeaderboardEntry(
                user_id=uuid4(),
                username="bob",
                display_name="Bob",
                total_score=150,
                sessions_completed=8,
                avg_score=18.75,
                best_score=35,
                weakest_area=None,
                rank=2,
            ),
        ]
        mocks["leaderboard"].get_leaderboard = AsyncMock(return_value=entries)
        resp = await handler.handle_leaderboard()
        assert "Alice" in resp.text
        assert "Bob" in resp.text
        assert "200" in resp.text
        assert "#1" in resp.text
        assert "#2" in resp.text


# ---------------------------------------------------------------------------
# /optout tests
# ---------------------------------------------------------------------------

class TestHandleOptout:
    """Tests for handle_optout."""

    @pytest.mark.asyncio
    async def test_optout_toggle_on(self):
        user = _make_user(opt_out=False)
        handler, mocks = _make_handler(user=user)
        resp = await handler.handle_optout(_make_user_context())
        assert "opted out" in resp.text
        mocks["user_repo"].update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_optout_toggle_off(self):
        user = _make_user(opt_out=True)
        handler, mocks = _make_handler(user=user)
        resp = await handler.handle_optout(_make_user_context())
        assert "opted back in" in resp.text


# ---------------------------------------------------------------------------
# Unknown command tests
# ---------------------------------------------------------------------------

class TestHandleUnknown:
    """Tests for handle_unknown."""

    @pytest.mark.asyncio
    async def test_unknown_lists_all_commands(self):
        handler, _ = _make_handler()
        resp = await handler.handle_unknown("foobar")
        assert "/train" in resp.text
        assert "/grade" in resp.text
        assert "/stats" in resp.text
        assert "/leaderboard" in resp.text
        assert "/optout" in resp.text
        assert "foobar" in resp.text
