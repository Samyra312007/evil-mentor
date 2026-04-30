"""MCP-compatible endpoint for ArmorIQ platform registration.

Implements the minimal JSON-RPC over HTTP interface that the ArmorIQ
platform expects when registering an MCP server. This allows the
platform to discover our tools and route invoke() calls to us.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

mcp_router = APIRouter()

# Our MCP server identity
MCP_SERVER_NAME = "evil-mentor-mcp"
MCP_SERVER_VERSION = "1.0.0"

# Tools that this MCP exposes to ArmorIQ
MCP_TOOLS = [
    {
        "name": "inject_vulnerabilities",
        "description": "Inject fake security vulnerabilities into a codebase for training",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Path to the git repository"},
                "difficulty": {"type": "string", "enum": ["EASY", "MEDIUM", "HARD"]},
                "user_id": {"type": "string"},
            },
            "required": ["repo_path"],
        },
    },
    {
        "name": "grade_session",
        "description": "Grade a training session by comparing findings against injections",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "run_scan",
        "description": "Run ArmorClaw security scan on a training branch",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string"},
                "branch_name": {"type": "string"},
            },
            "required": ["repo_path", "branch_name"],
        },
    },
    {
        "name": "create_training_branch",
        "description": "Create an isolated git branch for vulnerability injection training",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["repo_path", "session_id"],
        },
    },
    {
        "name": "commit_injections",
        "description": "Commit injected vulnerabilities to the training branch",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string"},
                "branch_name": {"type": "string"},
                "session_id": {"type": "string"},
                "injection_count": {"type": "integer"},
            },
            "required": ["repo_path", "branch_name", "session_id"],
        },
    },
]


def _make_jsonrpc_response(id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _make_jsonrpc_error(id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


@mcp_router.post("/mcp")
async def mcp_jsonrpc(request: Request) -> JSONResponse:
    """Handle JSON-RPC requests from the ArmorIQ platform.

    Supports the MCP protocol methods:
    - initialize: Server capability handshake
    - tools/list: Return available tools
    - tools/call: Execute a tool
    - ping: Health check
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            _make_jsonrpc_error(None, -32700, "Parse error"),
            status_code=200,
        )

    method = body.get("method", "")
    req_id = body.get("id")
    params = body.get("params", {})

    logger.info("MCP request: method=%s, id=%s", method, req_id)

    if method == "initialize":
        return JSONResponse(_make_jsonrpc_response(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": MCP_SERVER_NAME,
                "version": MCP_SERVER_VERSION,
            },
        }))

    elif method == "notifications/initialized":
        # Client acknowledges initialization — no response needed for notifications
        return JSONResponse(_make_jsonrpc_response(req_id, {}))

    elif method == "ping":
        return JSONResponse(_make_jsonrpc_response(req_id, {}))

    elif method == "tools/list":
        return JSONResponse(_make_jsonrpc_response(req_id, {
            "tools": MCP_TOOLS,
        }))

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        logger.info("MCP tools/call: tool=%s, args=%s", tool_name, arguments)

        # For now, return a success acknowledgment
        # The actual execution happens through the ArmorIQ SDK invoke() flow
        result_text = f"Tool '{tool_name}' acknowledged by Evil Mentor MCP"

        return JSONResponse(_make_jsonrpc_response(req_id, {
            "content": [{"type": "text", "text": result_text}],
            "isError": False,
        }))

    else:
        return JSONResponse(
            _make_jsonrpc_error(req_id, -32601, f"Method not found: {method}"),
            status_code=200,
        )


@mcp_router.get("/mcp")
async def mcp_sse_endpoint(request: Request):
    """SSE endpoint for MCP session initialization.

    The ArmorIQ platform may connect via GET to establish an SSE stream.
    We respond with the session endpoint for JSON-RPC communication.
    """
    from starlette.responses import StreamingResponse
    import asyncio

    async def event_stream():
        # Send the endpoint event telling the client where to POST
        endpoint_url = str(request.url).replace("/mcp", "/mcp")
        yield f"event: endpoint\ndata: {endpoint_url}\n\n"

        # Keep connection alive
        try:
            while True:
                await asyncio.sleep(30)
                yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
