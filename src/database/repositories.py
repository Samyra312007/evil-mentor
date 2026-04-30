"""Repository classes for database CRUD operations.

Each repository handles serialization between Pydantic domain models
and SQLite rows (TEXT UUIDs, INTEGER booleans, TEXT datetimes).
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

import aiosqlite

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid_to_str(value: UUID) -> str:
    return str(value)


def _str_to_uuid(value: str) -> UUID:
    return UUID(value)


def _dt_to_str(value: datetime) -> str:
    return value.isoformat()


def _str_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _bool_to_int(value: bool) -> int:
    return 1 if value else 0


def _int_to_bool(value: int) -> bool:
    return bool(value)


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------

class UserRepository:
    """CRUD operations for the users table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def create(self, user: User) -> User:
        """Insert a new user."""
        await self._conn.execute(
            """INSERT INTO users
               (id, platform_id, platform_type, username, display_name,
                is_active, opt_out, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _uuid_to_str(user.id),
                user.platform_id,
                user.platform_type.value,
                user.username,
                user.display_name,
                _bool_to_int(user.is_active),
                _bool_to_int(user.opt_out),
                _dt_to_str(user.created_at),
                _dt_to_str(user.updated_at),
            ),
        )
        await self._conn.commit()
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Fetch a user by primary key."""
        cursor = await self._conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (_uuid_to_str(user_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

    async def get_by_platform_id(self, platform_id: str, platform_type: PlatformType) -> User | None:
        """Fetch a user by platform identity."""
        cursor = await self._conn.execute(
            "SELECT * FROM users WHERE platform_id = ? AND platform_type = ?",
            (platform_id, platform_type.value),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

    async def update(self, user: User) -> User:
        """Update an existing user."""
        user.updated_at = datetime.utcnow()
        await self._conn.execute(
            """UPDATE users
               SET platform_id = ?, platform_type = ?, username = ?,
                   display_name = ?, is_active = ?, opt_out = ?,
                   created_at = ?, updated_at = ?
               WHERE id = ?""",
            (
                user.platform_id,
                user.platform_type.value,
                user.username,
                user.display_name,
                _bool_to_int(user.is_active),
                _bool_to_int(user.opt_out),
                _dt_to_str(user.created_at),
                _dt_to_str(user.updated_at),
                _uuid_to_str(user.id),
            ),
        )
        await self._conn.commit()
        return user

    async def delete(self, user_id: UUID) -> bool:
        """Delete a user by ID. Returns True if a row was deleted."""
        cursor = await self._conn.execute(
            "DELETE FROM users WHERE id = ?",
            (_uuid_to_str(user_id),),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def list_all(self) -> list[User]:
        """Return all users."""
        cursor = await self._conn.execute("SELECT * FROM users")
        rows = await cursor.fetchall()
        return [self._row_to_user(r) for r in rows]

    # -- internal --

    @staticmethod
    def _row_to_user(row: aiosqlite.Row) -> User:
        return User(
            id=_str_to_uuid(row["id"]),
            platform_id=row["platform_id"],
            platform_type=PlatformType(row["platform_type"]),
            username=row["username"],
            display_name=row["display_name"],
            is_active=_int_to_bool(row["is_active"]),
            opt_out=_int_to_bool(row["opt_out"]),
            created_at=_str_to_dt(row["created_at"]),
            updated_at=_str_to_dt(row["updated_at"]),
        )


# ---------------------------------------------------------------------------
# SessionRepository
# ---------------------------------------------------------------------------

class SessionRepository:
    """CRUD operations for the training_sessions table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def create(self, session: TrainingSession) -> TrainingSession:
        """Insert a new training session."""
        await self._conn.execute(
            """INSERT INTO training_sessions
               (id, user_id, intent_id, repo_path, branch_name,
                difficulty, status, injected_at, scanned_at, graded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _uuid_to_str(session.id),
                _uuid_to_str(session.user_id),
                session.intent_id,
                session.repo_path,
                session.branch_name,
                session.difficulty.value,
                session.status.value,
                _dt_to_str(session.injected_at),
                _dt_to_str(session.scanned_at) if session.scanned_at else None,
                _dt_to_str(session.graded_at) if session.graded_at else None,
            ),
        )
        await self._conn.commit()
        return session

    async def get_by_id(self, session_id: UUID) -> TrainingSession | None:
        """Fetch a session by primary key."""
        cursor = await self._conn.execute(
            "SELECT * FROM training_sessions WHERE id = ?",
            (_uuid_to_str(session_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    async def get_latest_for_user(self, user_id: UUID) -> TrainingSession | None:
        """Fetch the most recent session for a user."""
        cursor = await self._conn.execute(
            """SELECT * FROM training_sessions
               WHERE user_id = ?
               ORDER BY injected_at DESC
               LIMIT 1""",
            (_uuid_to_str(user_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    async def list_for_user(
        self, user_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[TrainingSession]:
        """Return paginated sessions for a user, newest first."""
        cursor = await self._conn.execute(
            """SELECT * FROM training_sessions
               WHERE user_id = ?
               ORDER BY injected_at DESC
               LIMIT ? OFFSET ?""",
            (_uuid_to_str(user_id), limit, offset),
        )
        rows = await cursor.fetchall()
        return [self._row_to_session(r) for r in rows]

    async def update(self, session: TrainingSession) -> TrainingSession:
        """Update an existing session."""
        await self._conn.execute(
            """UPDATE training_sessions
               SET user_id = ?, intent_id = ?, repo_path = ?,
                   branch_name = ?, difficulty = ?, status = ?,
                   injected_at = ?, scanned_at = ?, graded_at = ?
               WHERE id = ?""",
            (
                _uuid_to_str(session.user_id),
                session.intent_id,
                session.repo_path,
                session.branch_name,
                session.difficulty.value,
                session.status.value,
                _dt_to_str(session.injected_at),
                _dt_to_str(session.scanned_at) if session.scanned_at else None,
                _dt_to_str(session.graded_at) if session.graded_at else None,
                _uuid_to_str(session.id),
            ),
        )
        await self._conn.commit()
        return session

    async def delete(self, session_id: UUID) -> bool:
        """Delete a session by ID."""
        cursor = await self._conn.execute(
            "DELETE FROM training_sessions WHERE id = ?",
            (_uuid_to_str(session_id),),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # -- internal --

    @staticmethod
    def _row_to_session(row: aiosqlite.Row) -> TrainingSession:
        return TrainingSession(
            id=_str_to_uuid(row["id"]),
            user_id=_str_to_uuid(row["user_id"]),
            intent_id=row["intent_id"],
            repo_path=row["repo_path"],
            branch_name=row["branch_name"],
            difficulty=DifficultyLevel(row["difficulty"]),
            status=SessionStatus(row["status"]),
            injected_at=_str_to_dt(row["injected_at"]),
            scanned_at=_str_to_dt(row["scanned_at"]) if row["scanned_at"] else None,
            graded_at=_str_to_dt(row["graded_at"]) if row["graded_at"] else None,
        )


# ---------------------------------------------------------------------------
# InjectionRepository
# ---------------------------------------------------------------------------

class InjectionRepository:
    """CRUD operations for the injections table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def create(self, record: InjectionRecord) -> InjectionRecord:
        """Insert a new injection record."""
        await self._conn.execute(
            """INSERT INTO injections
               (id, session_id, vuln_type, difficulty, file_path,
                line_number, original_code, injected_code, description,
                detected, detection_time_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _uuid_to_str(record.id),
                _uuid_to_str(record.session_id),
                record.vuln_type.value,
                record.difficulty.value,
                record.file_path,
                record.line_number,
                record.original_code,
                record.injected_code,
                record.description,
                _bool_to_int(record.detected),
                record.detection_time_ms,
            ),
        )
        await self._conn.commit()
        return record

    async def create_many(self, records: list[InjectionRecord]) -> list[InjectionRecord]:
        """Insert multiple injection records in a single transaction."""
        await self._conn.executemany(
            """INSERT INTO injections
               (id, session_id, vuln_type, difficulty, file_path,
                line_number, original_code, injected_code, description,
                detected, detection_time_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    _uuid_to_str(r.id),
                    _uuid_to_str(r.session_id),
                    r.vuln_type.value,
                    r.difficulty.value,
                    r.file_path,
                    r.line_number,
                    r.original_code,
                    r.injected_code,
                    r.description,
                    _bool_to_int(r.detected),
                    r.detection_time_ms,
                )
                for r in records
            ],
        )
        await self._conn.commit()
        return records

    async def get_by_id(self, injection_id: UUID) -> InjectionRecord | None:
        """Fetch an injection by primary key."""
        cursor = await self._conn.execute(
            "SELECT * FROM injections WHERE id = ?",
            (_uuid_to_str(injection_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_injection(row)

    async def get_by_session(self, session_id: UUID) -> list[InjectionRecord]:
        """Fetch all injections for a session."""
        cursor = await self._conn.execute(
            "SELECT * FROM injections WHERE session_id = ?",
            (_uuid_to_str(session_id),),
        )
        rows = await cursor.fetchall()
        return [self._row_to_injection(r) for r in rows]

    async def update(self, record: InjectionRecord) -> InjectionRecord:
        """Update an existing injection record."""
        await self._conn.execute(
            """UPDATE injections
               SET session_id = ?, vuln_type = ?, difficulty = ?,
                   file_path = ?, line_number = ?, original_code = ?,
                   injected_code = ?, description = ?, detected = ?,
                   detection_time_ms = ?
               WHERE id = ?""",
            (
                _uuid_to_str(record.session_id),
                record.vuln_type.value,
                record.difficulty.value,
                record.file_path,
                record.line_number,
                record.original_code,
                record.injected_code,
                record.description,
                _bool_to_int(record.detected),
                record.detection_time_ms,
                _uuid_to_str(record.id),
            ),
        )
        await self._conn.commit()
        return record

    async def delete(self, injection_id: UUID) -> bool:
        """Delete an injection by ID."""
        cursor = await self._conn.execute(
            "DELETE FROM injections WHERE id = ?",
            (_uuid_to_str(injection_id),),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # -- internal --

    @staticmethod
    def _row_to_injection(row: aiosqlite.Row) -> InjectionRecord:
        return InjectionRecord(
            id=_str_to_uuid(row["id"]),
            session_id=_str_to_uuid(row["session_id"]),
            vuln_type=VulnerabilityType(row["vuln_type"]),
            difficulty=DifficultyLevel(row["difficulty"]),
            file_path=row["file_path"],
            line_number=row["line_number"],
            original_code=row["original_code"],
            injected_code=row["injected_code"],
            description=row["description"],
            detected=_int_to_bool(row["detected"]),
            detection_time_ms=row["detection_time_ms"],
        )


# ---------------------------------------------------------------------------
# ScanResultRepository
# ---------------------------------------------------------------------------

class ScanResultRepository:
    """CRUD operations for the scan_results table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def create(
        self,
        *,
        id: str,
        session_id: UUID,
        total_findings: int,
        raw_output: list[dict],
        created_at: datetime,
    ) -> dict:
        """Insert a new scan result."""
        await self._conn.execute(
            """INSERT INTO scan_results
               (id, session_id, total_findings, raw_output, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                id,
                _uuid_to_str(session_id),
                total_findings,
                json.dumps(raw_output),
                _dt_to_str(created_at),
            ),
        )
        await self._conn.commit()
        return {
            "id": id,
            "session_id": session_id,
            "total_findings": total_findings,
            "raw_output": raw_output,
            "created_at": created_at,
        }

    async def get_by_session(self, session_id: UUID) -> dict | None:
        """Fetch scan results for a session."""
        cursor = await self._conn.execute(
            "SELECT * FROM scan_results WHERE session_id = ?",
            (_uuid_to_str(session_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "session_id": _str_to_uuid(row["session_id"]),
            "total_findings": row["total_findings"],
            "raw_output": json.loads(row["raw_output"]),
            "created_at": _str_to_dt(row["created_at"]),
        }

    async def delete(self, scan_id: str) -> bool:
        """Delete a scan result by ID."""
        cursor = await self._conn.execute(
            "DELETE FROM scan_results WHERE id = ?",
            (scan_id,),
        )
        await self._conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# GradeRepository
# ---------------------------------------------------------------------------

class GradeRepository:
    """CRUD operations for the grades table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def create(self, record: GradeRecord) -> GradeRecord:
        """Insert a new grade record."""
        await self._conn.execute(
            """INSERT INTO grades
               (id, session_id, score, letter_grade, speed_bonus,
                missed_penalty, fp_penalty, feedback, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _uuid_to_str(record.id),
                _uuid_to_str(record.session_id),
                record.score,
                record.letter_grade.value,
                record.speed_bonus,
                record.missed_penalty,
                record.fp_penalty,
                record.feedback,
                _dt_to_str(record.created_at),
            ),
        )
        await self._conn.commit()
        return record

    async def get_by_id(self, grade_id: UUID) -> GradeRecord | None:
        """Fetch a grade by primary key."""
        cursor = await self._conn.execute(
            "SELECT * FROM grades WHERE id = ?",
            (_uuid_to_str(grade_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_grade(row)

    async def get_by_session(self, session_id: UUID) -> GradeRecord | None:
        """Fetch the grade for a session."""
        cursor = await self._conn.execute(
            "SELECT * FROM grades WHERE session_id = ?",
            (_uuid_to_str(session_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_grade(row)

    async def update(self, record: GradeRecord) -> GradeRecord:
        """Update an existing grade record."""
        await self._conn.execute(
            """UPDATE grades
               SET session_id = ?, score = ?, letter_grade = ?,
                   speed_bonus = ?, missed_penalty = ?, fp_penalty = ?,
                   feedback = ?, created_at = ?
               WHERE id = ?""",
            (
                _uuid_to_str(record.session_id),
                record.score,
                record.letter_grade.value,
                record.speed_bonus,
                record.missed_penalty,
                record.fp_penalty,
                record.feedback,
                _dt_to_str(record.created_at),
                _uuid_to_str(record.id),
            ),
        )
        await self._conn.commit()
        return record

    async def delete(self, grade_id: UUID) -> bool:
        """Delete a grade by ID."""
        cursor = await self._conn.execute(
            "DELETE FROM grades WHERE id = ?",
            (_uuid_to_str(grade_id),),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # -- internal --

    @staticmethod
    def _row_to_grade(row: aiosqlite.Row) -> GradeRecord:
        return GradeRecord(
            id=_str_to_uuid(row["id"]),
            session_id=_str_to_uuid(row["session_id"]),
            score=row["score"],
            letter_grade=LetterGrade(row["letter_grade"]),
            speed_bonus=row["speed_bonus"],
            missed_penalty=row["missed_penalty"],
            fp_penalty=row["fp_penalty"],
            feedback=row["feedback"],
            created_at=_str_to_dt(row["created_at"]),
        )


# ---------------------------------------------------------------------------
# LeaderboardRepository
# ---------------------------------------------------------------------------

class LeaderboardRepository:
    """CRUD operations for the leaderboard table."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._conn = connection

    async def upsert(self, entry: LeaderboardEntry) -> LeaderboardEntry:
        """Insert or update a leaderboard entry."""
        await self._conn.execute(
            """INSERT INTO leaderboard
               (user_id, username, display_name, total_score,
                sessions_completed, avg_score, best_score, weakest_area, rank)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   username = excluded.username,
                   display_name = excluded.display_name,
                   total_score = excluded.total_score,
                   sessions_completed = excluded.sessions_completed,
                   avg_score = excluded.avg_score,
                   best_score = excluded.best_score,
                   weakest_area = excluded.weakest_area,
                   rank = excluded.rank""",
            (
                _uuid_to_str(entry.user_id),
                entry.username,
                entry.display_name,
                entry.total_score,
                entry.sessions_completed,
                entry.avg_score,
                entry.best_score,
                entry.weakest_area.value if entry.weakest_area else None,
                entry.rank,
            ),
        )
        await self._conn.commit()
        return entry

    async def get_by_user(self, user_id: UUID) -> LeaderboardEntry | None:
        """Fetch a leaderboard entry for a user."""
        cursor = await self._conn.execute(
            "SELECT * FROM leaderboard WHERE user_id = ?",
            (_uuid_to_str(user_id),),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    async def get_top(self, limit: int = 50) -> list[LeaderboardEntry]:
        """Fetch the top-ranked entries."""
        cursor = await self._conn.execute(
            "SELECT * FROM leaderboard ORDER BY total_score DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_entry(r) for r in rows]

    async def recalculate_ranks(self) -> None:
        """Recalculate rank for all entries based on total_score descending."""
        cursor = await self._conn.execute(
            "SELECT user_id FROM leaderboard ORDER BY total_score DESC"
        )
        rows = await cursor.fetchall()
        for rank, row in enumerate(rows, start=1):
            await self._conn.execute(
                "UPDATE leaderboard SET rank = ? WHERE user_id = ?",
                (rank, row["user_id"]),
            )
        await self._conn.commit()

    async def delete(self, user_id: UUID) -> bool:
        """Delete a leaderboard entry."""
        cursor = await self._conn.execute(
            "DELETE FROM leaderboard WHERE user_id = ?",
            (_uuid_to_str(user_id),),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # -- internal --

    @staticmethod
    def _row_to_entry(row: aiosqlite.Row) -> LeaderboardEntry:
        return LeaderboardEntry(
            user_id=_str_to_uuid(row["user_id"]),
            username=row["username"],
            display_name=row["display_name"],
            total_score=row["total_score"],
            sessions_completed=row["sessions_completed"],
            avg_score=row["avg_score"],
            best_score=row["best_score"],
            weakest_area=VulnerabilityType(row["weakest_area"]) if row["weakest_area"] else None,
            rank=row["rank"],
        )
