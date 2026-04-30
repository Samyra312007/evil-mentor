"""Unit tests for the ArmorClawService.

All tests mock the ArmorIQ SDK client to avoid real network calls.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from armoriq_sdk.exceptions import (
    IntentMismatchException,
    InvalidTokenException,
    MCPInvocationException,
    TokenExpiredException,
)
from armoriq_sdk.models import IntentToken, MCPInvocationResult, PlanCapture

from src.services.armorclaw_service import ArmorClawService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_intent_token(*, expired: bool = False) -> IntentToken:
    """Build a minimal IntentToken for testing."""
    now = datetime.now().timestamp()
    return IntentToken(
        token_id="tok-test-123",
        plan_hash="abc123hash",
        signature="sig-placeholder",
        issued_at=now - 10,
        expires_at=now - 1 if expired else now + 60,
        composite_identity="composite-id",
        raw_token={
            "plan": {
                "goal": "test",
                "steps": [{"action": "do_thing", "mcp": "test-mcp"}],
            },
            "token": {},
        },
    )


def _make_plan_capture() -> PlanCapture:
    return PlanCapture(
        plan={"goal": "test", "steps": [{"action": "do_thing", "mcp": "test-mcp"}]},
        llm="gemini-2.0-flash",
        prompt="test prompt",
    )


def _make_invocation_result() -> MCPInvocationResult:
    return MCPInvocationResult(
        mcp="test-mcp",
        action="do_thing",
        result={"ok": True},
        status="success",
        verified=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client():
    """Return a mocked ArmorIQClient instance."""
    with patch("src.services.armorclaw_service.ArmorIQClient") as MockCls:
        client = MagicMock()
        MockCls.return_value = client
        yield client


@pytest.fixture
def service(mock_client):
    """Create an ArmorClawService with a mocked SDK client."""
    svc = ArmorClawService(
        api_key="ak_test_fakekey123",
        user_id="test-user",
        agent_id="test-agent",
    )
    return svc


# ---------------------------------------------------------------------------
# Tests — capture_and_get_token
# ---------------------------------------------------------------------------

class TestCaptureAndGetToken:

    @pytest.mark.asyncio
    async def test_captures_plan_and_returns_token(self, service, mock_client):
        mock_client.capture_plan.return_value = _make_plan_capture()
        mock_client.get_intent_token.return_value = _make_intent_token()

        token = await service.capture_and_get_token(
            plan_steps=[{"action": "do_thing", "mcp": "test-mcp"}],
            prompt="test prompt",
        )

        assert token.token_id == "tok-test-123"
        mock_client.capture_plan.assert_called_once()
        mock_client.get_intent_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_plan_structure_has_goal_and_steps(self, service, mock_client):
        mock_client.capture_plan.return_value = _make_plan_capture()
        mock_client.get_intent_token.return_value = _make_intent_token()

        steps = [{"action": "inject", "mcp": "evil-mentor-mcp", "params": {"x": 1}}]
        await service.capture_and_get_token(steps, "inject vulns")

        call_kwargs = mock_client.capture_plan.call_args
        plan_arg = call_kwargs.kwargs.get("plan") or call_kwargs[1].get("plan")
        assert "goal" in plan_arg
        assert "steps" in plan_arg
        assert plan_arg["steps"] == steps

    @pytest.mark.asyncio
    async def test_raises_on_token_failure(self, service, mock_client):
        mock_client.capture_plan.return_value = _make_plan_capture()
        mock_client.get_intent_token.side_effect = InvalidTokenException("nope")

        with pytest.raises(InvalidTokenException):
            await service.capture_and_get_token(
                [{"action": "a", "mcp": "m"}], "prompt"
            )


# ---------------------------------------------------------------------------
# Tests — invoke_action
# ---------------------------------------------------------------------------

class TestInvokeAction:

    @pytest.mark.asyncio
    async def test_invokes_successfully(self, service, mock_client):
        mock_client.invoke.return_value = _make_invocation_result()
        token = _make_intent_token()

        result = await service.invoke_action(
            mcp_name="test-mcp",
            action_name="do_thing",
            intent_token=token,
            params={"key": "value"},
        )

        assert result.status == "success"
        assert result.verified is True
        mock_client.invoke.assert_called_once_with(
            mcp="test-mcp",
            action="do_thing",
            intent_token=token,
            params={"key": "value"},
        )

    @pytest.mark.asyncio
    async def test_raises_token_expired(self, service, mock_client):
        mock_client.invoke.side_effect = TokenExpiredException(
            "expired", token_id="tok-1", expired_at=1.0
        )
        token = _make_intent_token()

        with pytest.raises(TokenExpiredException):
            await service.invoke_action("mcp", "action", token)

    @pytest.mark.asyncio
    async def test_raises_intent_mismatch(self, service, mock_client):
        mock_client.invoke.side_effect = IntentMismatchException(
            "mismatch", action="bad_action"
        )
        token = _make_intent_token()

        with pytest.raises(IntentMismatchException):
            await service.invoke_action("mcp", "bad_action", token)

    @pytest.mark.asyncio
    async def test_raises_mcp_invocation_error(self, service, mock_client):
        mock_client.invoke.side_effect = MCPInvocationException(
            "server down", mcp="mcp", action="act"
        )
        token = _make_intent_token()

        with pytest.raises(MCPInvocationException):
            await service.invoke_action("mcp", "act", token)


# ---------------------------------------------------------------------------
# Tests — gate_action (full lifecycle)
# ---------------------------------------------------------------------------

class TestGateAction:

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, service, mock_client):
        mock_client.capture_plan.return_value = _make_plan_capture()
        mock_client.get_intent_token.return_value = _make_intent_token()
        mock_client.invoke.return_value = _make_invocation_result()

        result = await service.gate_action(
            action_name="do_thing",
            mcp_name="test-mcp",
            plan_steps=[{"action": "do_thing", "mcp": "test-mcp"}],
            params={"p": 1},
        )

        assert result.status == "success"
        mock_client.capture_plan.assert_called_once()
        mock_client.get_intent_token.assert_called_once()
        mock_client.invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_propagates_token_expired(self, service, mock_client):
        mock_client.capture_plan.return_value = _make_plan_capture()
        mock_client.get_intent_token.return_value = _make_intent_token()
        mock_client.invoke.side_effect = TokenExpiredException(
            "expired", token_id="t", expired_at=0
        )

        with pytest.raises(TokenExpiredException):
            await service.gate_action(
                "act", "mcp", [{"action": "act", "mcp": "mcp"}]
            )

    @pytest.mark.asyncio
    async def test_wraps_unexpected_errors(self, service, mock_client):
        mock_client.capture_plan.return_value = _make_plan_capture()
        mock_client.get_intent_token.return_value = _make_intent_token()
        mock_client.invoke.side_effect = RuntimeError("boom")

        with pytest.raises(MCPInvocationException, match="boom"):
            await service.gate_action(
                "act", "mcp", [{"action": "act", "mcp": "mcp"}]
            )


# ---------------------------------------------------------------------------
# Tests — close
# ---------------------------------------------------------------------------

class TestClose:

    def test_closes_underlying_client(self, service, mock_client):
        service.close()
        mock_client.close.assert_called_once()
