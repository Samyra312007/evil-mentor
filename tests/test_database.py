"""Tests for the SQLite database layer — connection, migrations, and repositories."""

import pytest
import pytest_asyncio
from datetime import datetime
from uuid import uuid4

from src.database.connection import Database
from src.database.migrations import run_migrations
from src.database.repositories import (
    UserRepository,
    SessionRepository,
    InjectionRepository,
    ScanResultRepository,
    GradeRepository,
    LeaderboardRepository,
)
from src.models.domain import (
    DifficultyLevel,
    GradeRecord,
    InjectionRecord,
    LeaderboardEntry,
    LetterGrade,
    PlatformType,
    SessionStatus,
    TrainingSession,
    User,
    VulnerabilityType,
)


@pytest_asyncio.fixture
async def db():
    """Create an in-memory SQLite database for each test."""
    database = Database("sqlite:///:memory:")
    conn = await database.connect()
    await run_migrations(conn)
    yield conn
    await database.close()


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_migrations_create_all_tables(db):
    """All six tables should exist after migrations."""
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    rows = await cursor.fetchall()
    table_names = {row["name"] for row in rows}
    expected = {"users", "training_sessions", "injections", "scan_results", "grades", "leaderboard"}
    assert expected.issubset(table_names)


@pytest.mark.asyncio
async def test_migrations_are_idempotent(db):
    """Running migrations twice should not raise."""
    await run_migrations(db)  # second run
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    rows = await cursor.fetchall()
    table_names = {row["name"] for row in rows}
    assert "users" in table_names


# ---------------------------------------------------------------------------
# UserRepository tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_crud(db):
    repo = UserRepository(db)
    user = User(
        platform_id="tg_123",
        platform_type=PlatformType.TELEGRAM,
        username="alice",
        display_name="Alice",
    )
    created = await repo.create(user)
    assert created.id == user.id

    fetched = await repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.username == "alice"
    assert fetched.platform_type == PlatformType.TELEGRAM
    assert fetched.is_active is True
    assert fetched.opt_out is False

    fetched.opt_out = True
    updated = await repo.update(fetched)
    assert updated.opt_out is True

    refetched = await repo.get_by_id(user.id)
    assert refetched.opt_out is True

    deleted = await repo.delete(user.id)
    assert deleted is True
    assert await repo.get_by_id(user.id) is None


@pytest.mark.asyncio
async def test_user_get_by_platform_id(db):
    repo = UserRepository(db)
    user = User(
        platform_id="slack_456",
        platform_type=PlatformType.SLACK,
        username="bob",
    )
    await repo.create(user)
    found = await repo.get_by_platform_id("slack_456", PlatformType.SLACK)
    assert found is not None
    assert found.username == "bob"

    not_found = await repo.get_by_platform_id("slack_456", PlatformType.TELEGRAM)
    assert not_found is None


# ---------------------------------------------------------------------------
# SessionRepository tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_crud(db):
    user_repo = UserRepository(db)
    user = User(platform_id="u1", platform_type=PlatformType.DISCORD, username="dev1")
    await user_repo.create(user)

    repo = SessionRepository(db)
    session = TrainingSession(
        user_id=user.id,
        intent_id="intent_abc",
        repo_path="/tmp/repo",
        branch_name="evil-mentor/session-1",
        difficulty=DifficultyLevel.HARD,
    )
    await repo.create(session)

    fetched = await repo.get_by_id(session.id)
    assert fetched is not None
    assert fetched.difficulty == DifficultyLevel.HARD
    assert fetched.status == SessionStatus.INJECTED

    fetched.status = SessionStatus.GRADED
    fetched.graded_at = datetime.utcnow()
    await repo.update(fetched)

    refetched = await repo.get_by_id(session.id)
    assert refetched.status == SessionStatus.GRADED
    assert refetched.graded_at is not None


@pytest.mark.asyncio
async def test_session_get_latest_for_user(db):
    user_repo = UserRepository(db)
    user = User(platform_id="u2", platform_type=PlatformType.TELEGRAM, username="dev2")
    await user_repo.create(user)

    repo = SessionRepository(db)
    s1 = TrainingSession(
        user_id=user.id, intent_id="i1", repo_path="/r",
        branch_name="b1", injected_at=datetime(2024, 1, 1),
    )
    s2 = TrainingSession(
        user_id=user.id, intent_id="i2", repo_path="/r",
        branch_name="b2", injected_at=datetime(2024, 6, 1),
    )
    await repo.create(s1)
    await repo.create(s2)

    latest = await repo.get_latest_for_user(user.id)
    assert latest is not None
    assert latest.id == s2.id


# ---------------------------------------------------------------------------
# InjectionRepository tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_injection_crud(db):
    # Set up user + session first
    user_repo = UserRepository(db)
    user = User(platform_id="u3", platform_type=PlatformType.SLACK, username="dev3")
    await user_repo.create(user)

    session_repo = SessionRepository(db)
    session = TrainingSession(
        user_id=user.id, intent_id="i3", repo_path="/r", branch_name="b3",
    )
    await session_repo.create(session)

    repo = InjectionRepository(db)
    inj = InjectionRecord(
        session_id=session.id,
        vuln_type=VulnerabilityType.SQL_INJECTION,
        difficulty=DifficultyLevel.EASY,
        file_path="app.py",
        line_number=42,
        original_code="cursor.execute(query)",
        injected_code="cursor.execute(f'SELECT * FROM users WHERE id={user_input}')",
        description="SQL injection via f-string",
    )
    await repo.create(inj)

    fetched = await repo.get_by_id(inj.id)
    assert fetched is not None
    assert fetched.vuln_type == VulnerabilityType.SQL_INJECTION
    assert fetched.detected is False

    fetched.detected = True
    fetched.detection_time_ms = 1500
    await repo.update(fetched)

    refetched = await repo.get_by_id(inj.id)
    assert refetched.detected is True
    assert refetched.detection_time_ms == 1500

    by_session = await repo.get_by_session(session.id)
    assert len(by_session) == 1


@pytest.mark.asyncio
async def test_injection_create_many(db):
    user_repo = UserRepository(db)
    user = User(platform_id="u4", platform_type=PlatformType.TELEGRAM, username="dev4")
    await user_repo.create(user)

    session_repo = SessionRepository(db)
    session = TrainingSession(
        user_id=user.id, intent_id="i4", repo_path="/r", branch_name="b4",
    )
    await session_repo.create(session)

    repo = InjectionRepository(db)
    records = [
        InjectionRecord(
            session_id=session.id,
            vuln_type=VulnerabilityType.XSS,
            difficulty=DifficultyLevel.MEDIUM,
            file_path=f"file{i}.py",
            line_number=i * 10,
            original_code=f"orig{i}",
            injected_code=f"injected{i}",
            description=f"desc{i}",
        )
        for i in range(3)
    ]
    created = await repo.create_many(records)
    assert len(created) == 3

    by_session = await repo.get_by_session(session.id)
    assert len(by_session) == 3


# ---------------------------------------------------------------------------
# ScanResultRepository tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_result_crud(db):
    user_repo = UserRepository(db)
    user = User(platform_id="u5", platform_type=PlatformType.DISCORD, username="dev5")
    await user_repo.create(user)

    session_repo = SessionRepository(db)
    session = TrainingSession(
        user_id=user.id, intent_id="i5", repo_path="/r", branch_name="b5",
    )
    await session_repo.create(session)

    repo = ScanResultRepository(db)
    scan_id = str(uuid4())
    now = datetime.utcnow()
    raw = [{"finding_type": "SQL_INJECTION", "severity": "HIGH", "file_path": "app.py", "line_number": 42}]

    result = await repo.create(
        id=scan_id,
        session_id=session.id,
        total_findings=1,
        raw_output=raw,
        created_at=now,
    )
    assert result["total_findings"] == 1

    fetched = await repo.get_by_session(session.id)
    assert fetched is not None
    assert fetched["total_findings"] == 1
    assert len(fetched["raw_output"]) == 1
    assert fetched["raw_output"][0]["finding_type"] == "SQL_INJECTION"


# ---------------------------------------------------------------------------
# GradeRepository tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grade_crud(db):
    user_repo = UserRepository(db)
    user = User(platform_id="u6", platform_type=PlatformType.TELEGRAM, username="dev6")
    await user_repo.create(user)

    session_repo = SessionRepository(db)
    session = TrainingSession(
        user_id=user.id, intent_id="i6", repo_path="/r", branch_name="b6",
    )
    await session_repo.create(session)

    repo = GradeRepository(db)
    grade = GradeRecord(
        session_id=session.id,
        score=85,
        letter_grade=LetterGrade.B,
        speed_bonus=5,
        missed_penalty=10,
        fp_penalty=3,
        feedback="Good job, but watch for XSS.",
    )
    await repo.create(grade)

    fetched = await repo.get_by_id(grade.id)
    assert fetched is not None
    assert fetched.score == 85
    assert fetched.letter_grade == LetterGrade.B

    by_session = await repo.get_by_session(session.id)
    assert by_session is not None
    assert by_session.feedback == "Good job, but watch for XSS."


# ---------------------------------------------------------------------------
# LeaderboardRepository tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_leaderboard_upsert_and_ranking(db):
    user_repo = UserRepository(db)
    users = []
    for i, name in enumerate(["alice", "bob", "charlie"]):
        u = User(platform_id=f"p{i}", platform_type=PlatformType.TELEGRAM, username=name)
        await user_repo.create(u)
        users.append(u)

    repo = LeaderboardRepository(db)

    entries = [
        LeaderboardEntry(
            user_id=users[0].id, username="alice", display_name="Alice",
            total_score=300, sessions_completed=5, avg_score=60.0,
            best_score=80, weakest_area=VulnerabilityType.XSS, rank=0,
        ),
        LeaderboardEntry(
            user_id=users[1].id, username="bob", display_name="Bob",
            total_score=500, sessions_completed=8, avg_score=62.5,
            best_score=90, weakest_area=VulnerabilityType.SQL_INJECTION, rank=0,
        ),
        LeaderboardEntry(
            user_id=users[2].id, username="charlie", display_name=None,
            total_score=100, sessions_completed=2, avg_score=50.0,
            best_score=60, weakest_area=None, rank=0,
        ),
    ]
    for e in entries:
        await repo.upsert(e)

    await repo.recalculate_ranks()

    top = await repo.get_top(limit=10)
    assert len(top) == 3
    assert top[0].username == "bob"
    assert top[0].rank == 1
    assert top[1].username == "alice"
    assert top[1].rank == 2
    assert top[2].username == "charlie"
    assert top[2].rank == 3

    # Test upsert updates existing entry
    entries[2].total_score = 600
    await repo.upsert(entries[2])
    await repo.recalculate_ranks()

    top = await repo.get_top(limit=10)
    assert top[0].username == "charlie"
    assert top[0].total_score == 600
