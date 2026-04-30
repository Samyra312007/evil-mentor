"""Evil Mentor — FastAPI application entry point.

Wires together all services, repositories, and engines, runs database
migrations on startup, and exposes the REST API, WebSocket, health,
and webhook endpoints.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.api.routes import router as api_router
from src.api.websocket import WebSocketNotifier
from src.config import Settings
from src.core.grading_engine import GradingEngine
from src.core.injection_generator import InjectionGenerator
from src.core.vulnerability_engine import VulnerabilityEngine
from src.database.connection import Database
from src.database.migrations import run_migrations
from src.database.repositories import (
    GradeRepository,
    InjectionRepository,
    LeaderboardRepository,
    ScanResultRepository,
    SessionRepository,
    UserRepository,
)
from src.handlers.message_handler import MessageHandler
from src.services.armorclaw_service import ArmorClawService
from src.services.git_service import GitService
from src.services.leaderboard_service import LeaderboardService
from src.services.llm_service import LLMService
from src.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Request / response models for the webhook endpoint
# ---------------------------------------------------------------------------


class WebhookRequest(BaseModel):
    """Incoming chat platform message routed through the OpenClaw Gateway."""

    command: str
    args: list[str] = []
    platform_id: str
    platform_type: str = "telegram"
    username: str
    display_name: str | None = None


class WebhookResponse(BaseModel):
    """Response returned to the chat platform."""

    text: str
    attachments: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""

    # --- Startup -----------------------------------------------------------
    settings = Settings()

    # Database
    database = Database(db_url=settings.DATABASE_URL)
    connection = await database.connect()
    await run_migrations(connection)
    logger.info("Database migrations completed")

    # Repositories
    user_repo = UserRepository(connection)
    session_repo = SessionRepository(connection)
    injection_repo = InjectionRepository(connection)
    scan_result_repo = ScanResultRepository(connection)
    grade_repo = GradeRepository(connection)
    leaderboard_repo = LeaderboardRepository(connection)

    # Services
    llm_service = LLMService(settings=settings)
    armorclaw_service = ArmorClawService(
        api_key=settings.ARMORIQ_API_KEY,
        user_id=settings.ARMORIQ_USER_ID,
        agent_id=settings.ARMORIQ_AGENT_ID,
    )
    git_service = GitService(settings=settings)
    rate_limiter = RateLimiter()

    # Core engines
    vulnerability_engine = VulnerabilityEngine(llm_service=llm_service)
    injection_generator = InjectionGenerator()
    grading_engine = GradingEngine(llm_service=llm_service)

    # Leaderboard service
    leaderboard_service = LeaderboardService(
        leaderboard_repo=leaderboard_repo,
        user_repo=user_repo,
        grade_repo=grade_repo,
        session_repo=session_repo,
    )

    # WebSocket notifier
    ws_notifier = WebSocketNotifier()

    # Message handler (orchestration layer)
    message_handler = MessageHandler(
        settings=settings,
        vulnerability_engine=vulnerability_engine,
        injection_generator=injection_generator,
        grading_engine=grading_engine,
        git_service=git_service,
        armorclaw_service=armorclaw_service,
        rate_limiter=rate_limiter,
        leaderboard_service=leaderboard_service,
        user_repo=user_repo,
        session_repo=session_repo,
        injection_repo=injection_repo,
        scan_result_repo=scan_result_repo,
        grade_repo=grade_repo,
    )

    # Store references on app.state so route handlers can access them
    app.state.settings = settings
    app.state.database = database
    app.state.armorclaw_service = armorclaw_service
    app.state.user_repo = user_repo
    app.state.session_repo = session_repo
    app.state.injection_repo = injection_repo
    app.state.scan_result_repo = scan_result_repo
    app.state.grade_repo = grade_repo
    app.state.leaderboard_repo = leaderboard_repo
    app.state.leaderboard_service = leaderboard_service
    app.state.message_handler = message_handler
    app.state.ws_notifier = ws_notifier

    logger.info("Evil Mentor started successfully")

    yield

    # --- Shutdown ----------------------------------------------------------
    armorclaw_service.close()
    await database.close()
    logger.info("Evil Mentor shut down cleanly")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Evil Mentor", lifespan=lifespan)

# Include the REST API router (prefix /api)
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Webhook endpoint — accepts chat platform messages
# ---------------------------------------------------------------------------


@app.post("/webhook", response_model=WebhookResponse)
async def webhook(payload: WebhookRequest) -> WebhookResponse:
    """Accept a chat platform message and route it through the MessageHandler."""
    from src.models.domain import PlatformType, UserContext

    try:
        platform = PlatformType(payload.platform_type.lower())
    except ValueError:
        platform = PlatformType.TELEGRAM

    user_context = UserContext(
        platform_id=payload.platform_id,
        platform_type=platform,
        username=payload.username,
        display_name=payload.display_name,
    )

    handler: MessageHandler = app.state.message_handler
    response = await handler.handle(
        command=payload.command,
        args=payload.args,
        user_context=user_context,
    )

    return WebhookResponse(text=response.text, attachments=response.attachments)


# ---------------------------------------------------------------------------
# WebSocket endpoint — real-time dashboard notifications
# ---------------------------------------------------------------------------


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
    """WebSocket connection for real-time grade notifications."""
    notifier: WebSocketNotifier = app.state.ws_notifier
    await notifier.connect(websocket, user_id)
    try:
        # Keep the connection alive; the server pushes notifications.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await notifier.disconnect(user_id)
