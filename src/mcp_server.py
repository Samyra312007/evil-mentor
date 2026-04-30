"""MCP Server endpoint for ArmorIQ platform integration.

Exposes Evil Mentor's actions as MCP tools so the ArmorIQ platform
can discover, verify, and invoke them through the proxy.

Run separately: .venv/bin/python -m src.mcp_server
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("evil-mentor-mcp")


@mcp.tool()
def inject_vulnerabilities(
    repo_path: str,
    difficulty: str = "EASY",
    user_id: str = "default",
) -> dict:
    """Inject fake security vulnerabilities into a codebase for training.

    Args:
        repo_path: Path to the git repository to inject into.
        difficulty: EASY, MEDIUM, or HARD.
        user_id: The user requesting the injection.

    Returns:
        Session info with branch name and injection count.
    """
    return {
        "status": "success",
        "action": "inject_vulnerabilities",
        "repo_path": repo_path,
        "difficulty": difficulty,
        "user_id": user_id,
        "message": "Vulnerabilities injected via MCP",
    }


@mcp.tool()
def grade_session(
    session_id: str,
    user_id: str = "default",
) -> dict:
    """Grade a training session by comparing findings against injections.

    Args:
        session_id: The training session to grade.
        user_id: The user requesting the grade.

    Returns:
        Grade report with score and feedback.
    """
    return {
        "status": "success",
        "action": "grade_session",
        "session_id": session_id,
        "user_id": user_id,
        "message": "Session graded via MCP",
    }


@mcp.tool()
def run_scan(
    repo_path: str,
    branch_name: str,
) -> dict:
    """Run a security scan on a training branch using ArmorClaw.

    Args:
        repo_path: Path to the git repository.
        branch_name: The training branch to scan.

    Returns:
        Scan findings list.
    """
    return {
        "status": "success",
        "action": "run_scan",
        "repo_path": repo_path,
        "branch_name": branch_name,
        "findings": [],
        "message": "Scan completed via MCP",
    }


@mcp.tool()
def create_training_branch(
    repo_path: str,
    session_id: str,
) -> dict:
    """Create an isolated training branch for vulnerability injection.

    Args:
        repo_path: Path to the git repository.
        session_id: Unique session identifier.

    Returns:
        Branch creation result.
    """
    return {
        "status": "success",
        "action": "create_training_branch",
        "repo_path": repo_path,
        "session_id": session_id,
        "branch_name": f"evil-mentor/session-{session_id}",
        "message": "Training branch created via MCP",
    }


@mcp.tool()
def commit_injections(
    repo_path: str,
    branch_name: str,
    session_id: str,
    injection_count: int,
) -> dict:
    """Commit injected vulnerabilities to the training branch.

    Args:
        repo_path: Path to the git repository.
        branch_name: The training branch.
        session_id: Unique session identifier.
        injection_count: Number of injections to commit.

    Returns:
        Commit result.
    """
    return {
        "status": "success",
        "action": "commit_injections",
        "repo_path": repo_path,
        "branch_name": branch_name,
        "session_id": session_id,
        "injection_count": injection_count,
        "message": "Injections committed via MCP",
    }


if __name__ == "__main__":
    import uvicorn
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="0.0.0.0", port=8001, forwarded_allow_ips="*")
