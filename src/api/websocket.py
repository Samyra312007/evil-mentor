"""WebSocket Notifier for real-time dashboard updates.

Manages active WebSocket connections and pushes grade notifications
to connected dashboard clients.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from src.models.domain import GradeReport

logger = logging.getLogger(__name__)


class WebSocketNotifier:
    """WebSocket manager for real-time dashboard updates.

    Maintains a mapping of user IDs to active WebSocket connections.
    When a grade is recorded, the notifier pushes the report to the
    connected client for that user (if any).
    """

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """Register a client WebSocket connection.

        Accepts the WebSocket handshake and stores the connection
        keyed by user_id. If a previous connection exists for the
        same user, it is silently replaced.

        Args:
            websocket: The incoming WebSocket connection.
            user_id: The user identifier to associate with this connection.
        """
        await websocket.accept()

        # If there's an existing connection for this user, close it silently
        existing = self._connections.get(user_id)
        if existing is not None:
            try:
                await existing.close()
            except Exception:
                pass  # Handle dropped connections silently

        self._connections[user_id] = websocket
        logger.info("WebSocket connected for user %s", user_id)

    async def disconnect(self, user_id: str) -> None:
        """Remove a client connection.

        Removes the WebSocket connection for the given user_id.
        If no connection exists, this is a no-op.

        Args:
            user_id: The user identifier to disconnect.
        """
        ws = self._connections.pop(user_id, None)
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass  # Handle dropped connections silently
            logger.info("WebSocket disconnected for user %s", user_id)

    async def notify_grade(self, user_id: str, grade_report: GradeReport) -> None:
        """Push a grade notification to a connected dashboard client.

        Serializes the grade report to JSON and sends it over the
        WebSocket connection for the given user. If the connection
        has been dropped, it is silently removed.

        Args:
            user_id: The user to notify.
            grade_report: The grading report to send.
        """
        ws = self._connections.get(user_id)
        if ws is None:
            logger.debug("No WebSocket connection for user %s, skipping notification", user_id)
            return

        try:
            payload = {
                "type": "grade_notification",
                "data": {
                    "session_id": str(grade_report.session_id),
                    "score": grade_report.score_breakdown.total_score,
                    "letter_grade": grade_report.letter_grade.value,
                    "detection_rate": grade_report.score_breakdown.detection_rate,
                    "difficulty": grade_report.difficulty.value,
                    "feedback": grade_report.feedback,
                    "time_elapsed_seconds": grade_report.time_elapsed_seconds,
                    "matched_count": len(grade_report.matched),
                    "missed_count": len(grade_report.missed),
                    "false_positive_count": len(grade_report.false_positives),
                },
            }
            await ws.send_json(payload)
            logger.info("Grade notification sent to user %s", user_id)
        except (WebSocketDisconnect, RuntimeError, Exception):
            # Connection was dropped — remove it silently
            self._connections.pop(user_id, None)
            logger.debug(
                "WebSocket connection dropped for user %s, removed from active connections",
                user_id,
            )

    @property
    def active_connections(self) -> int:
        """Return the number of active WebSocket connections."""
        return len(self._connections)
