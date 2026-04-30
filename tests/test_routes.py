"""Unit tests for the REST API Router."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.routes import router
from src.models.domain import (
    DifficultyLevel,
    GradeRecord,
    LeaderboardEntry,
    LetterGrade,
    PlatformType,
    SessionStatus,
    TrainingSession,
    User,
    UserStats,
    VulnerabilityType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_user(user_id: UUID | None = None) -> User:
    uid = user_id or uuid4()
    return User(
        id=uid,
        platform_id="test-platform-id",
        platform_type=PlatformType.SLACK,
        username="testuser",
        display_name="Test User",
    )


def _make_app(
    user: User | None = None,
    leaderboard_service: object | None = None,
    session_repo: object | None = None,
    grade_repo: object | None = None,
) -> FastAPI:
    """Create a FastAPI app with mocked state for testing."""
    app = FastAPI()
    app.include_router(router)

    # Mock ArmorClaw service that validates tokens
    armorclaw_service = MagicMock()
    if user is not None:
        token_result = SimpleNamespace(valid=True, user_id=str(user.id))
        armorclaw_service.client.validate_token.return_value = token_result
    else:
        armorclaw_service.client.validate_token.return_value = None

    # Mock user repo
    user_repo = AsyncMock()
    if user is not None:
        user_repo.get_by_id.return_value = user
    else:
        user_repo.get_by_id.return_value = None

    app.state.armorclaw_service = armorclaw_service
    app.state.user_repo = user_repo
    app.state.leaderboard_service = leaderboard_service
    app.state.session_repo = session_repo
    app.state.grade_repo = grade_repo

    return app


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_auth_header_returns_401():
    """Requests without Authorization header get 401."""
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/user/stats")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication required"


@pytest.mark.asyncio
async def test_invalid_auth_format_returns_401():
    """Requests with malformed Authorization header get 401."""
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/user/stats",
            headers={"Authorization": "InvalidFormat"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_empty_bearer_token_returns_401():
    """Requests with empty Bearer token get 401."""
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/user/stats",
            headers={"Authorization": "Bearer "},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_returns_401():
    """Requests with invalid token get 401."""
    app = _make_app(user=None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/user/stats",
            headers={"Authorization": "Bearer bad-token"},
        )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/user/stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_stats_success():
    """Authenticated user gets their stats."""
    user = _make_user()
    stats = UserStats(
        user_id=user.id,
        total_score=150,
        sessions_completed=5,
        avg_score=30.0,
        best_score=50,
        weakest_area=VulnerabilityType.XSS,
        rank=3,
    )
    leaderboard_service = AsyncMock()
    leaderboard_service.get_user_stats.return_value = stats

    app = _make_app(user=user, leaderboard_service=leaderboard_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/user/stats",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == str(user.id)
    assert data["total_score"] == 150
    assert data["sessions_completed"] == 5
    assert data["avg_score"] == 30.0
    assert data["best_score"] == 50
    assert data["weakest_area"] == "XSS"
    assert data["rank"] == 3


@pytest.mark.asyncio
async def test_get_user_stats_no_weakest_area():
    """Stats with no weakest area returns null."""
    user = _make_user()
    stats = UserStats(
        user_id=user.id,
        total_score=0,
        sessions_completed=0,
        avg_score=0.0,
        best_score=0,
        weakest_area=None,
        rank=0,
    )
    leaderboard_service = AsyncMock()
    leaderboard_service.get_user_stats.return_value = stats

    app = _make_app(user=user, leaderboard_service=leaderboard_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/user/stats",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 200
    assert resp.json()["weakest_area"] is None


@pytest.mark.asyncio
async def test_get_user_stats_internal_error_returns_500():
    """Internal errors return 500 without leaking details."""
    user = _make_user()
    leaderboard_service = AsyncMock()
    leaderboard_service.get_user_stats.side_effect = RuntimeError("DB connection lost")

    app = _make_app(user=user, leaderboard_service=leaderboard_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/user/stats",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 500
    body = resp.json()
    assert "DB connection lost" not in str(body)
    assert body["detail"] == "Internal server error"


# ---------------------------------------------------------------------------
# GET /api/leaderboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_leaderboard_success():
    """Leaderboard returns entries sorted by score."""
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
            total_score=100,
            sessions_completed=5,
            avg_score=20.0,
            best_score=30,
            weakest_area=VulnerabilityType.SQL_INJECTION,
            rank=2,
        ),
    ]
    leaderboard_service = AsyncMock()
    leaderboard_service.get_leaderboard.return_value = entries

    # Leaderboard doesn't require auth
    app = _make_app(leaderboard_service=leaderboard_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/leaderboard")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["entries"]) == 2
    assert data["entries"][0]["username"] == "alice"
    assert data["entries"][1]["weakest_area"] == "SQL_INJECTION"


@pytest.mark.asyncio
async def test_get_leaderboard_with_limit():
    """Leaderboard respects the limit query param."""
    leaderboard_service = AsyncMock()
    leaderboard_service.get_leaderboard.return_value = []

    app = _make_app(leaderboard_service=leaderboard_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/leaderboard?limit=10")

    assert resp.status_code == 200
    leaderboard_service.get_leaderboard.assert_called_once_with(10)


@pytest.mark.asyncio
async def test_get_leaderboard_invalid_limit():
    """Leaderboard rejects limit < 1."""
    leaderboard_service = AsyncMock()
    app = _make_app(leaderboard_service=leaderboard_service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/leaderboard?limit=0")

    assert resp.status_code == 422  # Validation error


# ---------------------------------------------------------------------------
# GET /api/sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sessions_success():
    """Authenticated user gets paginated sessions."""
    user = _make_user()
    now = datetime.utcnow()
    sessions = [
        TrainingSession(
            id=uuid4(),
            user_id=user.id,
            intent_id="intent-1",
            repo_path="/repo",
            branch_name="evil-mentor/session-1",
            difficulty=DifficultyLevel.MEDIUM,
            status=SessionStatus.GRADED,
            injected_at=now,
            graded_at=now,
        ),
    ]
    session_repo = AsyncMock()
    session_repo.list_for_user.return_value = sessions

    app = _make_app(user=user, session_repo=session_repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/sessions?page=1&limit=10",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["page"] == 1
    assert data["limit"] == 10
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["status"] == "graded"


@pytest.mark.asyncio
async def test_get_sessions_pagination_offset():
    """Pagination calculates correct offset."""
    user = _make_user()
    session_repo = AsyncMock()
    session_repo.list_for_user.return_value = []

    app = _make_app(user=user, session_repo=session_repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/sessions?page=3&limit=20",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 200
    # page=3, limit=20 → offset=40
    session_repo.list_for_user.assert_called_once_with(
        user.id, limit=20, offset=40,
    )


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_detail_success():
    """Authenticated user gets session detail with grade."""
    user = _make_user()
    session_id = uuid4()
    now = datetime.utcnow()

    session = TrainingSession(
        id=session_id,
        user_id=user.id,
        intent_id="intent-1",
        repo_path="/repo",
        branch_name="evil-mentor/session-1",
        difficulty=DifficultyLevel.HARD,
        status=SessionStatus.GRADED,
        injected_at=now,
        graded_at=now,
    )
    grade = GradeRecord(
        id=uuid4(),
        session_id=session_id,
        score=85,
        letter_grade=LetterGrade.B,
        speed_bonus=5,
        missed_penalty=10,
        fp_penalty=3,
        feedback="Good job!",
        created_at=now,
    )

    session_repo = AsyncMock()
    session_repo.get_by_id.return_value = session
    grade_repo = AsyncMock()
    grade_repo.get_by_session.return_value = grade

    app = _make_app(user=user, session_repo=session_repo, grade_repo=grade_repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/sessions/{session_id}",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(session_id)
    assert data["difficulty"] == "HARD"
    assert data["grade"] is not None
    assert data["grade"]["score"] == 85
    assert data["grade"]["letter_grade"] == "B"
    assert data["grade"]["feedback"] == "Good job!"


@pytest.mark.asyncio
async def test_get_session_detail_not_found():
    """Non-existent session returns 404."""
    user = _make_user()
    session_repo = AsyncMock()
    session_repo.get_by_id.return_value = None
    grade_repo = AsyncMock()

    app = _make_app(user=user, session_repo=session_repo, grade_repo=grade_repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/sessions/{uuid4()}",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_detail_wrong_user():
    """Session belonging to another user returns 404."""
    user = _make_user()
    other_user_id = uuid4()
    session_id = uuid4()

    session = TrainingSession(
        id=session_id,
        user_id=other_user_id,  # Different user
        intent_id="intent-1",
        repo_path="/repo",
        branch_name="evil-mentor/session-1",
    )

    session_repo = AsyncMock()
    session_repo.get_by_id.return_value = session
    grade_repo = AsyncMock()

    app = _make_app(user=user, session_repo=session_repo, grade_repo=grade_repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/sessions/{session_id}",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_detail_invalid_uuid():
    """Invalid session ID format returns 404."""
    user = _make_user()
    session_repo = AsyncMock()
    grade_repo = AsyncMock()

    app = _make_app(user=user, session_repo=session_repo, grade_repo=grade_repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/sessions/not-a-uuid",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_session_detail_no_grade():
    """Session without a grade returns null grade field."""
    user = _make_user()
    session_id = uuid4()

    session = TrainingSession(
        id=session_id,
        user_id=user.id,
        intent_id="intent-1",
        repo_path="/repo",
        branch_name="evil-mentor/session-1",
        status=SessionStatus.INJECTED,
    )

    session_repo = AsyncMock()
    session_repo.get_by_id.return_value = session
    grade_repo = AsyncMock()
    grade_repo.get_by_session.return_value = None

    app = _make_app(user=user, session_repo=session_repo, grade_repo=grade_repo)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/sessions/{session_id}",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert resp.status_code == 200
    assert resp.json()["grade"] is None
