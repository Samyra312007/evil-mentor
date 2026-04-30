"""REST API Router for the Evil Mentor web dashboard.

Exposes endpoints for user stats, leaderboard, and session history.
All endpoints validate an ArmorIQ token from the Authorization header.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from src.models.domain import (
    GradeReport,
    LeaderboardEntry,
    TrainingSession,
    User,
    UserStats,
    VulnerabilityType,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class UserStatsResponse(BaseModel):
    """Response model for user statistics."""

    user_id: str
    total_score: int
    sessions_completed: int
    avg_score: float
    best_score: int
    weakest_area: str | None
    rank: int


class LeaderboardEntryResponse(BaseModel):
    """A single leaderboard entry in the response."""

    user_id: str
    username: str
    display_name: str | None
    total_score: int
    sessions_completed: int
    avg_score: float
    best_score: int
    weakest_area: str | None
    rank: int


class LeaderboardResponse(BaseModel):
    """Response model for leaderboard."""

    entries: list[LeaderboardEntryResponse]
    total: int


class SessionSummaryResponse(BaseModel):
    """Summary of a training session for list views."""

    id: str
    difficulty: str
    status: str
    injected_at: str
    scanned_at: str | None
    graded_at: str | None


class PaginatedSessionsResponse(BaseModel):
    """Paginated session history response."""

    sessions: list[SessionSummaryResponse]
    page: int
    limit: int
    total: int


class SessionDetailResponse(BaseModel):
    """Detailed session view with grading report."""

    id: str
    user_id: str
    intent_id: str
    repo_path: str
    branch_name: str
    difficulty: str
    status: str
    injected_at: str
    scanned_at: str | None
    graded_at: str | None
    grade: dict | None


class ErrorResponse(BaseModel):
    """Generic error response."""

    error: str


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def get_current_user(request: Request) -> User:
    """Validate ArmorIQ token from Authorization header.

    Extracts the Bearer token from the Authorization header, validates
    it against the ArmorIQ service, and returns the authenticated user.

    Returns 401 for missing or invalid tokens.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Expect "Bearer <token>" format
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")

    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Validate token using the ArmorIQ service stored in app state
    armorclaw_service = getattr(request.app.state, "armorclaw_service", None)
    user_repo = getattr(request.app.state, "user_repo", None)

    if armorclaw_service is None or user_repo is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Use ArmorIQ client to validate the token
        # The token encodes the user identity; we verify it and extract user info
        result = armorclaw_service.client.validate_token(token)
        if result is None or not getattr(result, "valid", False):
            raise HTTPException(status_code=401, detail="Authentication required")

        # Look up the user by the ID from the validated token
        user_id = UUID(result.user_id)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        return user

    except HTTPException:
        raise
    except Exception:
        logger.debug("Token validation failed", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication required")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/user/stats", response_model=UserStatsResponse)
async def get_user_stats(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> UserStatsResponse:
    """Return statistics for the authenticated user."""
    try:
        leaderboard_service = request.app.state.leaderboard_service
        stats: UserStats = await leaderboard_service.get_user_stats(current_user.id)

        return UserStatsResponse(
            user_id=str(stats.user_id),
            total_score=stats.total_score,
            sessions_completed=stats.sessions_completed,
            avg_score=stats.avg_score,
            best_score=stats.best_score,
            weakest_area=stats.weakest_area.value if stats.weakest_area else None,
            rank=stats.rank,
        )
    except Exception:
        logger.exception("Error fetching user stats")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
) -> LeaderboardResponse:
    """Return the leaderboard with optional limit."""
    try:
        leaderboard_service = request.app.state.leaderboard_service
        entries: list[LeaderboardEntry] = await leaderboard_service.get_leaderboard(limit)

        entry_responses = [
            LeaderboardEntryResponse(
                user_id=str(e.user_id),
                username=e.username,
                display_name=e.display_name,
                total_score=e.total_score,
                sessions_completed=e.sessions_completed,
                avg_score=e.avg_score,
                best_score=e.best_score,
                weakest_area=e.weakest_area.value if e.weakest_area else None,
                rank=e.rank,
            )
            for e in entries
        ]

        return LeaderboardResponse(
            entries=entry_responses,
            total=len(entry_responses),
        )
    except Exception:
        logger.exception("Error fetching leaderboard")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions", response_model=PaginatedSessionsResponse)
async def get_sessions(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
) -> PaginatedSessionsResponse:
    """Return paginated session history for the authenticated user."""
    try:
        session_repo = request.app.state.session_repo
        offset = (page - 1) * limit

        sessions: list[TrainingSession] = await session_repo.list_for_user(
            current_user.id, limit=limit, offset=offset,
        )

        session_responses = [
            SessionSummaryResponse(
                id=str(s.id),
                difficulty=s.difficulty.value,
                status=s.status.value,
                injected_at=s.injected_at.isoformat(),
                scanned_at=s.scanned_at.isoformat() if s.scanned_at else None,
                graded_at=s.graded_at.isoformat() if s.graded_at else None,
            )
            for s in sessions
        ]

        return PaginatedSessionsResponse(
            sessions=session_responses,
            page=page,
            limit=limit,
            total=len(session_responses),
        )
    except Exception:
        logger.exception("Error fetching sessions")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> SessionDetailResponse:
    """Return session detail with full grading report."""
    try:
        session_repo = request.app.state.session_repo
        grade_repo = request.app.state.grade_repo

        # Parse and fetch the session
        try:
            sid = UUID(session_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Session not found")

        session: TrainingSession | None = await session_repo.get_by_id(sid)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        # Ensure the session belongs to the authenticated user
        if session.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Session not found")

        # Fetch grade if available
        grade_data: dict | None = None
        grade_record = await grade_repo.get_by_session(session.id)
        if grade_record is not None:
            grade_data = {
                "id": str(grade_record.id),
                "score": grade_record.score,
                "letter_grade": grade_record.letter_grade.value,
                "speed_bonus": grade_record.speed_bonus,
                "missed_penalty": grade_record.missed_penalty,
                "fp_penalty": grade_record.fp_penalty,
                "feedback": grade_record.feedback,
                "created_at": grade_record.created_at.isoformat(),
            }

        return SessionDetailResponse(
            id=str(session.id),
            user_id=str(session.user_id),
            intent_id=session.intent_id,
            repo_path=session.repo_path,
            branch_name=session.branch_name,
            difficulty=session.difficulty.value,
            status=session.status.value,
            injected_at=session.injected_at.isoformat(),
            scanned_at=session.scanned_at.isoformat() if session.scanned_at else None,
            graded_at=session.graded_at.isoformat() if session.graded_at else None,
            grade=grade_data,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error fetching session detail")
        raise HTTPException(status_code=500, detail="Internal server error")
