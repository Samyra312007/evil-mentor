"""Unit tests for the Injection Generator."""

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import git
import pytest

from src.core.injection_generator import InjectionGenerator
from src.models.domain import (
    CandidateVulnerability,
    DifficultyLevel,
    InjectionManifest,
    InjectionRecord,
    VulnerabilityType,
)


@pytest.fixture
def generator():
    return InjectionGenerator()


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary git repo with a sample source file."""
    repo = git.Repo.init(tmp_path)

    # Create a sample Python file
    sample = tmp_path / "app.py"
    sample.write_text(
        "import os\n"
        "def get_config():\n"
        '    return os.getenv("CONFIG")\n'
        "def main():\n"
        '    print("hello")\n',
        encoding="utf-8",
    )

    repo.index.add(["app.py"])
    repo.index.commit("initial commit")

    # Create a training branch
    repo.create_head("evil-mentor/session-test")

    return tmp_path


def _make_candidate(
    file_path="app.py",
    line_number=3,
    original_code='    return os.getenv("CONFIG")\n',
    injected_code='    secret = "EVIL_MENTOR_FAKE_API_KEY_abc123"\n',
    vuln_type=VulnerabilityType.HARDCODED_SECRET,
    explanation="Hardcoded secret for training",
) -> CandidateVulnerability:
    return CandidateVulnerability(
        vuln_type=vuln_type,
        file_path=file_path,
        line_number=line_number,
        original_code=original_code,
        injected_code=injected_code,
        explanation=explanation,
    )


# --- Class constants ---


def test_injection_tag_constant(generator):
    assert generator.INJECTION_TAG == "EVIL_MENTOR_INJECTED"


def test_safe_prefix_constant(generator):
    assert generator.SAFE_PREFIX == "EVIL_MENTOR_FAKE_"


# --- _add_traceability_comment ---


def test_traceability_comment_contains_tag(generator):
    result = generator._add_traceability_comment("x = 1", "abc-123")
    assert "EVIL_MENTOR_INJECTED" in result
    assert "abc-123" in result


def test_traceability_comment_python_style(generator):
    result = generator._add_traceability_comment("x = 1", "id1", comment_prefix="#")
    assert "# EVIL_MENTOR_INJECTED" in result


def test_traceability_comment_js_style(generator):
    result = generator._add_traceability_comment(
        "let x = 1;", "id2", comment_prefix="//"
    )
    assert "// EVIL_MENTOR_INJECTED" in result


def test_traceability_comment_multiline(generator):
    code = "line1\nline2\nline3"
    result = generator._add_traceability_comment(code, "id3")
    lines = result.splitlines()
    # Tag should be on the last line only
    assert "EVIL_MENTOR_INJECTED" not in lines[0]
    assert "EVIL_MENTOR_INJECTED" not in lines[1]
    assert "EVIL_MENTOR_INJECTED" in lines[2]


def test_traceability_comment_empty_code(generator):
    result = generator._add_traceability_comment("", "id4")
    assert "EVIL_MENTOR_INJECTED" in result


# --- _inject_into_file ---


def test_inject_into_file_preserves_surrounding(generator, temp_repo):
    candidate = _make_candidate()
    abs_path = str(temp_repo / "app.py")
    session_id = uuid4()

    record = generator._inject_into_file(abs_path, candidate, session_id)

    content = Path(abs_path).read_text(encoding="utf-8")
    lines = content.splitlines()

    # Line 1 and 2 should be untouched
    assert lines[0] == "import os"
    assert lines[1] == "def get_config():"

    # The injected line should contain the tag
    assert "EVIL_MENTOR_INJECTED" in lines[2]
    assert "EVIL_MENTOR_FAKE_API_KEY_abc123" in lines[2]

    # Lines after the injection should be preserved
    assert lines[3] == "def main():"
    assert lines[4] == '    print("hello")'


def test_inject_into_file_returns_record(generator, temp_repo):
    candidate = _make_candidate()
    abs_path = str(temp_repo / "app.py")
    session_id = uuid4()

    record = generator._inject_into_file(abs_path, candidate, session_id)

    assert isinstance(record, InjectionRecord)
    assert record.session_id == session_id
    assert record.vuln_type == VulnerabilityType.HARDCODED_SECRET
    assert record.file_path == "app.py"
    assert record.line_number == 3
    assert record.original_code == candidate.original_code
    assert record.injected_code == candidate.injected_code
    assert record.description == candidate.explanation


def test_inject_into_file_nonexistent_raises(generator):
    candidate = _make_candidate(file_path="nonexistent.py")
    with pytest.raises(FileNotFoundError):
        generator._inject_into_file("/tmp/no_such_file.py", candidate, uuid4())


# --- apply_injections ---


@pytest.mark.asyncio
async def test_apply_injections_creates_manifest(generator, temp_repo):
    candidates = [_make_candidate()]
    manifest = await generator.apply_injections(
        candidates,
        str(temp_repo),
        "evil-mentor/session-test",
    )

    assert isinstance(manifest, InjectionManifest)
    assert manifest.count == 1
    assert manifest.injections[0].file_path == "app.py"


@pytest.mark.asyncio
async def test_apply_injections_skips_bad_files(generator, temp_repo):
    """Files that don't exist should be skipped, not crash."""
    candidates = [
        _make_candidate(file_path="nonexistent.py"),
        _make_candidate(),  # this one should succeed
    ]
    manifest = await generator.apply_injections(
        candidates,
        str(temp_repo),
        "evil-mentor/session-test",
    )

    # Only the valid file should be in the manifest
    assert manifest.count == 1
    assert manifest.injections[0].file_path == "app.py"


@pytest.mark.asyncio
async def test_apply_injections_multiple_candidates(generator, tmp_path):
    """Multiple injections into the same file at different lines."""
    # Create a fresh repo with multi.py from the start
    repo = git.Repo.init(tmp_path)
    sample = tmp_path / "multi.py"
    sample.write_text(
        "line1\nline2\nline3\nline4\nline5\n",
        encoding="utf-8",
    )
    repo.index.add(["multi.py"])
    repo.index.commit("initial commit")

    # Create training branch after the file exists
    repo.create_head("evil-mentor/session-multi")

    candidates = [
        _make_candidate(
            file_path="multi.py",
            line_number=2,
            original_code="line2\n",
            injected_code='secret = "EVIL_MENTOR_FAKE_KEY_1"\n',
        ),
    ]

    manifest = await generator.apply_injections(
        candidates,
        str(tmp_path),
        "evil-mentor/session-multi",
    )

    assert manifest.count == 1
    content = (tmp_path / "multi.py").read_text()
    assert "EVIL_MENTOR_FAKE_KEY_1" in content
    assert "EVIL_MENTOR_INJECTED" in content
    # Surrounding lines preserved
    assert "line1" in content
    assert "line3" in content


# --- validate_manifest ---


def test_validate_manifest_valid(generator):
    manifest = InjectionManifest(
        session_id=uuid4(),
        injections=[
            InjectionRecord(
                session_id=uuid4(),
                vuln_type=VulnerabilityType.HARDCODED_SECRET,
                difficulty=DifficultyLevel.MEDIUM,
                file_path="app.py",
                line_number=1,
                original_code="x = 1",
                injected_code='secret = "EVIL_MENTOR_FAKE_KEY_abc"',
                description="test",
            ),
        ],
    )
    assert generator.validate_manifest(manifest) is True


def test_validate_manifest_invalid_missing_prefix(generator):
    manifest = InjectionManifest(
        session_id=uuid4(),
        injections=[
            InjectionRecord(
                session_id=uuid4(),
                vuln_type=VulnerabilityType.HARDCODED_SECRET,
                difficulty=DifficultyLevel.MEDIUM,
                file_path="app.py",
                line_number=1,
                original_code="x = 1",
                injected_code='secret = "REAL_SECRET_KEY"',
                description="test",
            ),
        ],
    )
    assert generator.validate_manifest(manifest) is False


def test_validate_manifest_non_secret_types_pass(generator):
    """Non-HARDCODED_SECRET types don't need the prefix."""
    manifest = InjectionManifest(
        session_id=uuid4(),
        injections=[
            InjectionRecord(
                session_id=uuid4(),
                vuln_type=VulnerabilityType.SQL_INJECTION,
                difficulty=DifficultyLevel.MEDIUM,
                file_path="app.py",
                line_number=1,
                original_code="x = 1",
                injected_code="query = f\"SELECT * FROM users WHERE id={user_id}\"",
                description="test",
            ),
        ],
    )
    assert generator.validate_manifest(manifest) is True


def test_validate_manifest_empty(generator):
    """Empty manifest is valid."""
    manifest = InjectionManifest(session_id=uuid4(), injections=[])
    assert generator.validate_manifest(manifest) is True
