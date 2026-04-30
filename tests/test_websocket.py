"""Unit tests for the WebSocket Notifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.api.websocket import WebSocketNotifier
from src.models.domain import (
    DifficultyLevel,
    FalsePositive,
    GradeReport,
    InjectionRecord,
    LetterGrade,
    MatchedVuln,
    MissedVuln,
    ScanFinding,
    ScoreBreakdown,
    VulnerabilityType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_grade_report() -> GradeReport:
    """Create a minimal GradeReport for testing."""
    session_id = uuid4()
    injection = InjectionRecord(
        session_id=session_id,
        vuln_type=VulnerabilityType.XSS,
        difficulty=DifficultyLevel.MEDIUM,
        file_path="app.py",
        line_number=10,
        original_code="safe()",
        injected_code="unsafe()",
        description="XSS vuln",
    )
    finding = ScanFinding(
        finding_type="XSS",
        severity="HIGH",
        file_path="app.py",
        line_number=10,
    )
    return GradeReport(
        session_id=session_id,
        score_breakdown=ScoreBreakdown(
            found_points=10,
            type_bonus_points=2,
            missed_penalty=0,
            false_positive_penalty=0,
            speed_bonus=5,
            total_score=17,
            detection_rate=1.0,
        ),
        letter_grade=LetterGrade.A,
        matched=[MatchedVuln(injection=injection, finding=finding, type_match=True)],
        missed=[],
        false_positives=[],
        feedback="Great work!",
        difficulty=DifficultyLevel.MEDIUM,
        time_elapsed_seconds=120.0,
    )


def _make_mock_websocket(*, accept_raises: bool = False, send_raises: bool = False) -> AsyncMock:
    """Create a mock WebSocket."""
    ws = AsyncMock()
    if accept_raises:
        ws.accept.side_effect = RuntimeError("Connection refused")
    if send_raises:
        ws.send_json.side_effect = RuntimeError("Connection lost")
    return ws


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_registers_connection():
    """connect() accepts the websocket and stores it."""
    notifier = WebSocketNotifier()
    ws = _make_mock_websocket()

    await notifier.connect(ws, "user-1")

    ws.accept.assert_called_once()
    assert notifier.active_connections == 1


@pytest.mark.asyncio
async def test_connect_replaces_existing_connection():
    """Connecting the same user replaces the old connection."""
    notifier = WebSocketNotifier()
    ws1 = _make_mock_websocket()
    ws2 = _make_mock_websocket()

    await notifier.connect(ws1, "user-1")
    await notifier.connect(ws2, "user-1")

    assert notifier.active_connections == 1
    # Old connection should have been closed
    ws1.close.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_removes_connection():
    """disconnect() removes and closes the connection."""
    notifier = WebSocketNotifier()
    ws = _make_mock_websocket()

    await notifier.connect(ws, "user-1")
    assert notifier.active_connections == 1

    await notifier.disconnect("user-1")
    assert notifier.active_connections == 0
    ws.close.assert_called()


@pytest.mark.asyncio
async def test_disconnect_nonexistent_user_is_noop():
    """disconnect() for unknown user does nothing."""
    notifier = WebSocketNotifier()
    # Should not raise
    await notifier.disconnect("nonexistent-user")
    assert notifier.active_connections == 0


@pytest.mark.asyncio
async def test_notify_grade_sends_json():
    """notify_grade() sends the grade report as JSON."""
    notifier = WebSocketNotifier()
    ws = _make_mock_websocket()
    report = _make_grade_report()

    await notifier.connect(ws, "user-1")
    await notifier.notify_grade("user-1", report)

    ws.send_json.assert_called_once()
    payload = ws.send_json.call_args[0][0]
    assert payload["type"] == "grade_notification"
    assert payload["data"]["score"] == 17
    assert payload["data"]["letter_grade"] == "A"
    assert payload["data"]["detection_rate"] == 1.0
    assert payload["data"]["matched_count"] == 1
    assert payload["data"]["missed_count"] == 0


@pytest.mark.asyncio
async def test_notify_grade_no_connection_is_noop():
    """notify_grade() for unconnected user does nothing."""
    notifier = WebSocketNotifier()
    report = _make_grade_report()

    # Should not raise
    await notifier.notify_grade("no-such-user", report)


@pytest.mark.asyncio
async def test_notify_grade_dropped_connection_removed_silently():
    """Dropped connections are removed silently on send failure."""
    notifier = WebSocketNotifier()
    ws = _make_mock_websocket(send_raises=True)
    report = _make_grade_report()

    await notifier.connect(ws, "user-1")
    assert notifier.active_connections == 1

    # Should not raise, and should remove the dead connection
    await notifier.notify_grade("user-1", report)
    assert notifier.active_connections == 0


@pytest.mark.asyncio
async def test_disconnect_handles_close_error_silently():
    """disconnect() handles errors when closing the websocket."""
    notifier = WebSocketNotifier()
    ws = _make_mock_websocket()
    ws.close.side_effect = RuntimeError("Already closed")

    await notifier.connect(ws, "user-1")
    # Should not raise
    await notifier.disconnect("user-1")
    assert notifier.active_connections == 0


@pytest.mark.asyncio
async def test_multiple_users():
    """Multiple users can be connected simultaneously."""
    notifier = WebSocketNotifier()
    ws1 = _make_mock_websocket()
    ws2 = _make_mock_websocket()

    await notifier.connect(ws1, "user-1")
    await notifier.connect(ws2, "user-2")

    assert notifier.active_connections == 2

    report = _make_grade_report()
    await notifier.notify_grade("user-1", report)

    ws1.send_json.assert_called_once()
    ws2.send_json.assert_not_called()
