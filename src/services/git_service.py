"""Git Service for Evil Mentor.

Manages git branch creation, commits, and cleanup for training sessions.
All injections happen on isolated training branches — never on protected branches.
"""

import logging
from pathlib import Path

import git

from src.config import Settings

logger = logging.getLogger(__name__)


class GitService:
    """Git operations for training branch isolation."""

    BRANCH_PREFIX = "evil-mentor/session-"

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings()
        self._blocked_branches: set[str] = self._settings.blocked_branch_set

    def is_protected_branch(self, branch_name: str) -> bool:
        """Check if a branch name matches a blocked pattern.

        Returns True if the lowercased branch name is in the blocked set.
        The default blocked set is {"main", "master", "production"}.
        """
        return branch_name.strip().lower() in self._blocked_branches

    async def create_training_branch(
        self,
        repo_path: str,
        session_id: str,
        source_branch: str = "HEAD",
    ) -> str:
        """Create evil-mentor/session-{session_id} branch from source.

        Args:
            repo_path: Path to the git repository.
            session_id: Unique session identifier.
            source_branch: Branch or ref to branch from (default "HEAD").

        Returns:
            The name of the created training branch.

        Raises:
            ValueError: If the source branch is protected.
            git.InvalidGitRepositoryError: If repo_path is not a valid git repo.
        """
        branch_name = f"{self.BRANCH_PREFIX}{session_id}"

        if self.is_protected_branch(source_branch):
            logger.warning(
                "Attempted to use protected branch '%s' as source", source_branch
            )

        repo = git.Repo(repo_path)

        # Resolve the source ref
        if source_branch == "HEAD":
            source_commit = repo.head.commit
        else:
            source_commit = repo.commit(source_branch)

        # Create the new branch from the source commit
        repo.create_head(branch_name, commit=source_commit)
        logger.info(
            "Created training branch '%s' from '%s' in %s",
            branch_name,
            source_branch,
            repo_path,
        )

        return branch_name

    async def commit_injections(
        self,
        repo_path: str,
        branch_name: str,
        session_id: str,
        injection_count: int,
    ) -> str:
        """Commit all injection changes with session metadata.

        Args:
            repo_path: Path to the git repository.
            branch_name: The training branch to commit on.
            session_id: Unique session identifier.
            injection_count: Number of injections applied.

        Returns:
            The commit SHA hex string.

        Raises:
            ValueError: If trying to commit to a protected branch.
            git.InvalidGitRepositoryError: If repo_path is not a valid git repo.
        """
        if self.is_protected_branch(branch_name):
            raise ValueError(
                f"Cannot commit to protected branch '{branch_name}'. "
                "Production branches are protected."
            )

        repo = git.Repo(repo_path)

        # Checkout the training branch
        repo.heads[branch_name].checkout()

        # Stage all changes
        repo.git.add(A=True)

        # Build commit message with session metadata
        commit_message = (
            f"[Evil Mentor] Session {session_id}: "
            f"injected {injection_count} vulnerabilities"
        )

        commit = repo.index.commit(commit_message)
        logger.info(
            "Committed injections on branch '%s': %s", branch_name, commit.hexsha
        )

        return commit.hexsha

    async def delete_training_branch(
        self,
        repo_path: str,
        branch_name: str,
    ) -> bool:
        """Delete the training branch after session ends.

        Args:
            repo_path: Path to the git repository.
            branch_name: The training branch to delete.

        Returns:
            True if the branch was deleted successfully, False otherwise.
        """
        try:
            repo = git.Repo(repo_path)

            # Don't delete if we're currently on that branch
            if repo.active_branch.name == branch_name:
                # Switch to the default branch first
                default_branch = self._find_default_branch(repo)
                if default_branch:
                    default_branch.checkout()
                else:
                    logger.error(
                        "Cannot delete branch '%s': no default branch to switch to",
                        branch_name,
                    )
                    return False

            repo.delete_head(branch_name, force=True)
            logger.info("Deleted training branch '%s' in %s", branch_name, repo_path)
            return True

        except Exception:
            logger.exception("Failed to delete branch '%s'", branch_name)
            return False

    @staticmethod
    def _find_default_branch(repo: git.Repo) -> git.Head | None:
        """Find a default branch to switch to when deleting the current branch."""
        for name in ("main", "master"):
            for head in repo.heads:
                if head.name == name:
                    return head
        # Fall back to the first available branch
        for head in repo.heads:
            return head
        return None
