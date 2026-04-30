"""Unit tests for GitService."""

import os
import asyncio
import tempfile

import git
import pytest

from src.services.git_service import GitService


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with an initial commit."""
    repo = git.Repo.init(tmp_path)
    # Configure git user for commits
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()

    # Create an initial file and commit so HEAD exists
    readme = tmp_path / "README.md"
    readme.write_text("# Test Repo")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    return tmp_path, repo


@pytest.fixture
def git_service():
    """Create a GitService instance with default settings."""
    return GitService()


class TestIsProtectedBranch:
    """Tests for is_protected_branch."""

    def test_main_is_protected(self, git_service):
        assert git_service.is_protected_branch("main") is True

    def test_master_is_protected(self, git_service):
        assert git_service.is_protected_branch("master") is True

    def test_production_is_protected(self, git_service):
        assert git_service.is_protected_branch("production") is True

    def test_case_insensitive_main(self, git_service):
        assert git_service.is_protected_branch("MAIN") is True

    def test_case_insensitive_master(self, git_service):
        assert git_service.is_protected_branch("Master") is True

    def test_case_insensitive_production(self, git_service):
        assert git_service.is_protected_branch("PRODUCTION") is True

    def test_feature_branch_not_protected(self, git_service):
        assert git_service.is_protected_branch("feature/my-feature") is False

    def test_training_branch_not_protected(self, git_service):
        assert git_service.is_protected_branch("evil-mentor/session-abc") is False

    def test_empty_string_not_protected(self, git_service):
        assert git_service.is_protected_branch("") is False

    def test_whitespace_trimmed(self, git_service):
        assert git_service.is_protected_branch("  main  ") is True


class TestCreateTrainingBranch:
    """Tests for create_training_branch."""

    @pytest.mark.asyncio
    async def test_creates_branch_with_correct_name(self, git_repo, git_service):
        repo_path, repo = git_repo
        session_id = "test-session-123"

        branch_name = await git_service.create_training_branch(
            str(repo_path), session_id
        )

        assert branch_name == f"evil-mentor/session-{session_id}"
        assert branch_name in [h.name for h in repo.heads]

    @pytest.mark.asyncio
    async def test_creates_branch_from_head(self, git_repo, git_service):
        repo_path, repo = git_repo
        head_commit = repo.head.commit

        branch_name = await git_service.create_training_branch(
            str(repo_path), "sess-1"
        )

        branch = repo.heads[branch_name]
        assert branch.commit == head_commit

    @pytest.mark.asyncio
    async def test_creates_branch_from_named_source(self, git_repo, git_service):
        repo_path, repo = git_repo
        # The default branch created by git init
        default_branch = repo.active_branch.name

        branch_name = await git_service.create_training_branch(
            str(repo_path), "sess-2", source_branch=default_branch
        )

        assert branch_name in [h.name for h in repo.heads]


class TestCommitInjections:
    """Tests for commit_injections."""

    @pytest.mark.asyncio
    async def test_commits_with_session_metadata(self, git_repo, git_service):
        repo_path, repo = git_repo
        session_id = "abc-123"

        # Create training branch and add a file
        branch_name = await git_service.create_training_branch(
            str(repo_path), session_id
        )
        repo.heads[branch_name].checkout()

        # Create a modified file
        vuln_file = repo_path / "vuln.py"
        vuln_file.write_text("# EVIL_MENTOR_INJECTED\npassword = 'EVIL_MENTOR_FAKE_SECRET_123'")

        sha = await git_service.commit_injections(
            str(repo_path), branch_name, session_id, injection_count=3
        )

        assert sha is not None
        commit = repo.commit(sha)
        assert session_id in commit.message
        assert "3" in commit.message

    @pytest.mark.asyncio
    async def test_rejects_commit_to_protected_branch(self, git_repo, git_service):
        repo_path, repo = git_repo

        with pytest.raises(ValueError, match="protected"):
            await git_service.commit_injections(
                str(repo_path), "main", "session-1", 1
            )

    @pytest.mark.asyncio
    async def test_commit_message_format(self, git_repo, git_service):
        repo_path, repo = git_repo
        session_id = "xyz-789"

        branch_name = await git_service.create_training_branch(
            str(repo_path), session_id
        )
        repo.heads[branch_name].checkout()

        test_file = repo_path / "test.txt"
        test_file.write_text("modified content")

        sha = await git_service.commit_injections(
            str(repo_path), branch_name, session_id, injection_count=5
        )

        commit = repo.commit(sha)
        assert "Evil Mentor" in commit.message
        assert session_id in commit.message
        assert "5" in commit.message


class TestDeleteTrainingBranch:
    """Tests for delete_training_branch."""

    @pytest.mark.asyncio
    async def test_deletes_branch(self, git_repo, git_service):
        repo_path, repo = git_repo

        branch_name = await git_service.create_training_branch(
            str(repo_path), "del-test"
        )
        assert branch_name in [h.name for h in repo.heads]

        result = await git_service.delete_training_branch(str(repo_path), branch_name)

        assert result is True
        assert branch_name not in [h.name for h in repo.heads]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_branch_returns_false(self, git_repo, git_service):
        repo_path, repo = git_repo

        result = await git_service.delete_training_branch(
            str(repo_path), "nonexistent-branch"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_current_branch_switches_first(self, git_repo, git_service):
        repo_path, repo = git_repo

        branch_name = await git_service.create_training_branch(
            str(repo_path), "current-test"
        )
        # Checkout the training branch so it's the active one
        repo.heads[branch_name].checkout()

        result = await git_service.delete_training_branch(str(repo_path), branch_name)

        assert result is True
        assert branch_name not in [h.name for h in repo.heads]
