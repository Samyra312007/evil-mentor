"""Injection Generator for Evil Mentor.

Applies generated vulnerabilities to source code files on the training branch.
Produces an InjectionManifest for later grading. Every injected secret must
contain the EVIL_MENTOR_FAKE_ prefix — if validation fails, the entire
injection is aborted and reverted.
"""

import logging
from pathlib import Path
from uuid import uuid4

import git

from src.models.domain import (
    CandidateVulnerability,
    DifficultyLevel,
    InjectionManifest,
    InjectionRecord,
    VulnerabilityType,
)

logger = logging.getLogger(__name__)


# Map file extensions to comment syntax for the traceability tag.
_COMMENT_SYNTAX: dict[str, str] = {
    ".py": "#",
    ".js": "//",
    ".ts": "//",
    ".jsx": "//",
    ".tsx": "//",
    ".java": "//",
    ".c": "//",
    ".cpp": "//",
    ".cs": "//",
    ".go": "//",
    ".rs": "//",
    ".rb": "#",
    ".php": "//",
    ".swift": "//",
    ".kt": "//",
    ".scala": "//",
    ".sh": "#",
    ".bash": "#",
    ".yaml": "#",
    ".yml": "#",
    ".toml": "#",
}

_DEFAULT_COMMENT_PREFIX = "#"


class InjectionGenerator:
    """Safe code injection into source files."""

    INJECTION_TAG = "EVIL_MENTOR_INJECTED"
    SAFE_PREFIX = "EVIL_MENTOR_FAKE_"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def apply_injections(
        self,
        candidates: list[CandidateVulnerability],
        repo_path: str,
        branch_name: str,
        session_id: str | None = None,
    ) -> InjectionManifest:
        """Apply all candidate injections to files on the training branch.

        For each candidate the generator:
        1. Resolves the absolute file path inside *repo_path*.
        2. Injects the vulnerable code, preserving surrounding lines.
        3. Adds a traceability comment with the ``EVIL_MENTOR_INJECTED`` tag.
        4. Records the result as an :class:`InjectionRecord`.

        Files that cannot be modified are skipped with a logged warning
        (Requirement 3.3).

        Args:
            candidates: Vulnerability candidates produced by the
                :class:`VulnerabilityEngine`.
            repo_path: Filesystem path to the git repository root.
            branch_name: The training branch where injections are applied.
            session_id: Optional session identifier. A random UUID is used
                when not provided.

        Returns:
            An :class:`InjectionManifest` listing every successfully applied
            injection.
        """
        from uuid import UUID

        sid = UUID(session_id) if session_id else uuid4()

        # Checkout the training branch so file writes land on it.
        try:
            repo = git.Repo(repo_path)
            repo.heads[branch_name].checkout()
        except Exception:
            logger.warning(
                "Could not checkout branch '%s' in %s — "
                "injections will be applied to the current working tree",
                branch_name,
                repo_path,
            )

        records: list[InjectionRecord] = []

        for candidate in candidates:
            abs_path = str(Path(repo_path) / candidate.file_path)
            try:
                record = self._inject_into_file(abs_path, candidate, sid)
                records.append(record)
            except Exception:
                logger.warning(
                    "Failed to inject into %s — skipping file",
                    candidate.file_path,
                    exc_info=True,
                )

        manifest = InjectionManifest(session_id=sid, injections=records)
        return manifest

    def validate_manifest(self, manifest: InjectionManifest) -> bool:
        """Verify every secret in the manifest contains the Safe_Prefix.

        Returns ``True`` when the manifest is valid. Returns ``False`` (and
        logs an error) when any ``HARDCODED_SECRET`` injection is missing the
        ``EVIL_MENTOR_FAKE_`` prefix — the caller should abort and revert.
        """
        if not manifest.has_valid_prefixes():
            logger.error(
                "Manifest validation failed for session %s: "
                "one or more HARDCODED_SECRET injections lack the "
                "EVIL_MENTOR_FAKE_ prefix — aborting injection",
                manifest.session_id,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _inject_into_file(
        self,
        file_path: str,
        candidate: CandidateVulnerability,
        session_id,
    ) -> InjectionRecord:
        """Modify a single file with the injected vulnerability.

        The method reads the file, locates the target line, replaces the
        original code with the injected code (including a traceability
        comment), and writes the file back — preserving all surrounding
        lines (Requirement 3.2).

        Args:
            file_path: Absolute path to the source file.
            candidate: The vulnerability candidate to inject.
            session_id: The owning session UUID.

        Returns:
            An :class:`InjectionRecord` describing the applied injection.

        Raises:
            FileNotFoundError: If *file_path* does not exist.
            OSError: On any I/O failure.
        """
        record_id = uuid4()

        # Read the original file content.
        path = Path(file_path)
        original_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

        # Determine the comment prefix from the file extension.
        suffix = path.suffix.lower()
        comment_prefix = _COMMENT_SYNTAX.get(suffix, _DEFAULT_COMMENT_PREFIX)

        # Build the tagged injected code.
        tagged_code = self._add_traceability_comment(
            candidate.injected_code,
            str(record_id),
            comment_prefix=comment_prefix,
        )

        # Replace the target line(s).  The candidate's ``line_number`` is
        # 1-based.  We replace the original code lines with the injected
        # code while keeping everything else intact.
        target_idx = candidate.line_number - 1  # 0-based index

        # Figure out how many lines the original snippet spans so we can
        # replace exactly those lines.
        original_snippet_lines = candidate.original_code.splitlines(keepends=True)
        span = len(original_snippet_lines) if original_snippet_lines else 1

        # Ensure the tagged code ends with a newline so the rest of the
        # file is not mangled.
        if not tagged_code.endswith("\n"):
            tagged_code += "\n"

        new_lines = (
            original_lines[:target_idx]
            + [tagged_code]
            + original_lines[target_idx + span :]
        )

        new_content = "".join(new_lines)

        # Validate that the modified file still parses (Python files only).
        if suffix == ".py":
            try:
                compile(new_content, file_path, "exec")
            except SyntaxError:
                logger.warning(
                    "Injection at %s:%d would break syntax — skipping",
                    file_path,
                    candidate.line_number,
                )
                raise ValueError(
                    f"Injection at line {candidate.line_number} breaks syntax"
                )

        path.write_text(new_content, encoding="utf-8")

        return InjectionRecord(
            id=record_id,
            session_id=session_id,
            vuln_type=candidate.vuln_type,
            difficulty=DifficultyLevel.MEDIUM,  # default; caller can override
            file_path=candidate.file_path,
            line_number=candidate.line_number,
            original_code=candidate.original_code,
            injected_code=candidate.injected_code,
            description=candidate.explanation,
        )

    @staticmethod
    def _add_traceability_comment(
        injected_code: str,
        injection_id: str,
        *,
        comment_prefix: str = "#",
    ) -> str:
        """Add the ``EVIL_MENTOR_INJECTED`` tag as an inline comment.

        The tag is appended to the *last* line of the injected code so that
        multi-line injections remain syntactically valid while still being
        traceable (Requirement 3.4).

        Args:
            injected_code: The raw injected code snippet.
            injection_id: Unique identifier for this injection.
            comment_prefix: Language-appropriate comment token (e.g. ``#``,
                ``//``).

        Returns:
            The injected code with the traceability comment appended.
        """
        tag = (
            f"  {comment_prefix} {InjectionGenerator.INJECTION_TAG} "
            f"[{injection_id}]"
        )

        lines = injected_code.splitlines(keepends=True)
        if not lines:
            return tag

        # Strip trailing newline from the last line before appending the tag,
        # then re-add the newline.
        last = lines[-1].rstrip("\n\r")
        lines[-1] = last + tag + "\n"
        return "".join(lines)
