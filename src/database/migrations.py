"""Database schema migrations for SQLite.

Adapted from the PostgreSQL schema in the design document.
SQLite adaptations:
  - UUID columns → TEXT
  - JSONB columns → TEXT (store as JSON strings)
  - BOOLEAN columns → INTEGER (0/1)
  - TIMESTAMP columns → TEXT (ISO-8601 strings)
"""

import aiosqlite


SCHEMA_SQL = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    platform_id TEXT NOT NULL,
    platform_type TEXT NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    opt_out INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Training sessions table
CREATE TABLE IF NOT EXISTS training_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    intent_id TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    difficulty TEXT NOT NULL DEFAULT 'MEDIUM',
    status TEXT NOT NULL DEFAULT 'injected',
    injected_at TEXT NOT NULL,
    scanned_at TEXT,
    graded_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Injections table
CREATE TABLE IF NOT EXISTS injections (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    vuln_type TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    original_code TEXT NOT NULL,
    injected_code TEXT NOT NULL,
    description TEXT NOT NULL,
    detected INTEGER NOT NULL DEFAULT 0,
    detection_time_ms INTEGER,
    FOREIGN KEY (session_id) REFERENCES training_sessions(id)
);

-- Scan results table
CREATE TABLE IF NOT EXISTS scan_results (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    total_findings INTEGER NOT NULL DEFAULT 0,
    raw_output TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES training_sessions(id)
);

-- Grades table
CREATE TABLE IF NOT EXISTS grades (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    letter_grade TEXT NOT NULL,
    speed_bonus INTEGER NOT NULL DEFAULT 0,
    missed_penalty INTEGER NOT NULL DEFAULT 0,
    fp_penalty INTEGER NOT NULL DEFAULT 0,
    feedback TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES training_sessions(id)
);

-- Leaderboard table (denormalized rankings)
CREATE TABLE IF NOT EXISTS leaderboard (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT,
    total_score INTEGER NOT NULL DEFAULT 0,
    sessions_completed INTEGER NOT NULL DEFAULT 0,
    avg_score REAL NOT NULL DEFAULT 0.0,
    best_score INTEGER NOT NULL DEFAULT 0,
    weakest_area TEXT,
    rank INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_sessions_user ON training_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON training_sessions(status);
CREATE INDEX IF NOT EXISTS idx_injections_session ON injections(session_id);
CREATE INDEX IF NOT EXISTS idx_injections_detected ON injections(detected);
CREATE INDEX IF NOT EXISTS idx_grades_score ON grades(score);
"""


async def run_migrations(connection: aiosqlite.Connection) -> None:
    """Create all tables and indexes if they don't exist."""
    await connection.executescript(SCHEMA_SQL)
    await connection.commit()
