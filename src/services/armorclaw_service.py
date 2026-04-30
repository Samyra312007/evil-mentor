"""ArmorIQ SDK wrapper for policy-gated agent actions.

Provides the ``ArmorClawService`` class that encapsulates the full
``capture_plan()`` → ``get_intent_token()`` → ``invoke()`` lifecycle
required by the ArmorIQ platform.  Every Evil Mentor action (injection,
scan trigger, grading) is routed through this service so that a complete
cryptographic audit trail is recorded on the ArmorIQ backend.
"""

import logging
from typing import Any

from armoriq_sdk.client import ArmorIQClient
from armoriq_sdk.exceptions import (
    ConfigurationException,
    IntentMismatchException,
    InvalidTokenException,
    MCPInvocationException,
    TokenExpiredException,
)
from armoriq_sdk.models import IntentToken, MCPInvocationResult, PlanCapture

logger = logging.getLogger(__name__)


class ArmorClawService:
    """ArmorIQ SDK wrapper for policy-gated actions.

    Wraps the ArmorIQ SDK v0.2.6 client and exposes high-level helpers
    that Evil Mentor components use to gate every mutating action behind
    a signed intent token.

    Args:
        api_key: ArmorIQ API key (``ak_live_…`` or ``ak_test_…``).
        user_id: ArmorIQ user identifier.
        agent_id: ArmorIQ agent identifier.
    """

    # Default LLM identifier used when capturing plans.
    DEFAULT_LLM = "gemini-2.0-flash"

    def __init__(self, api_key: str, user_id: str, agent_id: str) -> None:
        self.client = ArmorIQClient(
            api_key=api_key,
            user_id=user_id,
            agent_id=agent_id,
        )
        logger.info(
            "ArmorClawService initialized for user=%s, agent=%s",
            user_id,
            agent_id,
        )

    # ------------------------------------------------------------------
    # High-level convenience method
    # ------------------------------------------------------------------

    async def gate_action(
        self,
        action_name: str,
        mcp_name: str,
        plan_steps: list[dict[str, Any]],
        params: dict[str, Any] | None = None,
    ) -> MCPInvocationResult:
        """Execute the full policy-gated lifecycle for a single action.

        1. ``capture_plan()`` — register the plan with ArmorIQ.
        2. ``get_intent_token()`` — obtain a signed intent token.
        3. ``invoke()`` — execute the action through the ArmorIQ proxy.

        Args:
            action_name: The action/tool name to invoke (e.g. ``"inject_vulnerabilities"``).
            mcp_name: The MCP server identifier (e.g. ``"evil-mentor-mcp"``).
            plan_steps: List of step dicts, each with ``"action"``, ``"mcp"``,
                and optionally ``"params"``.
            params: Parameters to pass to the invoked action.

        Returns:
            ``MCPInvocationResult`` from the ArmorIQ proxy.

        Raises:
            InvalidTokenException: If the token cannot be issued.
            TokenExpiredException: If the token has expired before invocation.
            IntentMismatchException: If the action is not in the original plan.
            MCPInvocationException: If the MCP invocation fails.
        """
        logger.info(
            "Gating action: action=%s, mcp=%s, steps=%d",
            action_name,
            mcp_name,
            len(plan_steps),
        )

        try:
            # Step 1 + 2: capture plan and get token
            prompt = f"Evil Mentor action: {action_name}"
            intent_token = await self.capture_and_get_token(plan_steps, prompt)

            # Step 3: invoke through proxy
            result = await self.invoke_action(
                mcp_name=mcp_name,
                action_name=action_name,
                intent_token=intent_token,
                params=params or {},
            )

            logger.info(
                "Action gated successfully: action=%s, status=%s",
                action_name,
                result.status,
            )
            return result

        except (
            InvalidTokenException,
            TokenExpiredException,
            IntentMismatchException,
            MCPInvocationException,
        ):
            # Re-raise SDK exceptions so callers can handle them.
            raise
        except Exception as exc:
            logger.error(
                "Unexpected error during gated action %s: %s",
                action_name,
                exc,
                exc_info=True,
            )
            raise MCPInvocationException(
                f"Unexpected error during action '{action_name}': {exc}",
                mcp=mcp_name,
                action=action_name,
            ) from exc

    # ------------------------------------------------------------------
    # Plan capture + token acquisition
    # ------------------------------------------------------------------

    async def capture_and_get_token(
        self,
        plan_steps: list[dict[str, Any]],
        prompt: str,
    ) -> IntentToken:
        """Capture a plan and obtain a signed intent token.

        Builds the plan structure expected by the ArmorIQ SDK, calls
        ``capture_plan()`` to register it, then calls ``get_intent_token()``
        to receive a cryptographically signed token.

        Args:
            plan_steps: List of step dicts (``action``, ``mcp``, optional ``params``).
            prompt: Human-readable description of the intent.

        Returns:
            A signed ``IntentToken`` ready for use with ``invoke()``.

        Raises:
            InvalidTokenException: If token issuance fails.
        """
        plan = {
            "goal": prompt,
            "steps": plan_steps,
        }

        logger.debug("Capturing plan with %d steps: %s", len(plan_steps), prompt)

        # capture_plan is synchronous in the SDK
        plan_capture: PlanCapture = self.client.capture_plan(
            llm=self.DEFAULT_LLM,
            prompt=prompt,
            plan=plan,
        )

        logger.debug("Plan captured, requesting intent token…")

        intent_token: IntentToken = self.client.get_intent_token(plan_capture)

        logger.info(
            "Intent token acquired: id=%s, expires_in=%.1fs",
            intent_token.token_id,
            intent_token.time_until_expiry,
        )
        return intent_token

    # ------------------------------------------------------------------
    # Action invocation
    # ------------------------------------------------------------------

    async def invoke_action(
        self,
        mcp_name: str,
        action_name: str,
        intent_token: IntentToken,
        params: dict[str, Any] | None = None,
    ) -> MCPInvocationResult:
        """Invoke an MCP action through the ArmorIQ proxy.

        The proxy verifies the intent token cryptographically before
        forwarding the request to the target MCP server.

        Args:
            mcp_name: MCP server identifier.
            action_name: Action/tool name to invoke.
            intent_token: Signed intent token from ``capture_and_get_token()``.
            params: Parameters to pass to the action.

        Returns:
            ``MCPInvocationResult`` with the action outcome.

        Raises:
            TokenExpiredException: If the token has expired.
            IntentMismatchException: If the action is not in the plan.
            MCPInvocationException: If the invocation fails.
        """
        logger.info(
            "Invoking action: mcp=%s, action=%s, token=%s",
            mcp_name,
            action_name,
            intent_token.token_id,
        )

        # invoke() is synchronous in the SDK
        result: MCPInvocationResult = self.client.invoke(
            mcp=mcp_name,
            action=action_name,
            intent_token=intent_token,
            params=params or {},
        )

        logger.info(
            "Invocation complete: mcp=%s, action=%s, status=%s, verified=%s",
            result.mcp,
            result.action,
            result.status,
            result.verified,
        )
        return result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying ArmorIQ HTTP client."""
        self.client.close()
        logger.info("ArmorClawService closed")
