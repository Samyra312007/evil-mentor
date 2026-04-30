"""Evil Mentor domain models.

All Pydantic models and enums used across the application.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# --- Enums ---


class DifficultyLevel(str, Enum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class VulnerabilityType(str, Enum):
    SQL_INJECTION = "SQL_INJECTION"
    XSS = "XSS"
    HARDCODED_SECRET = "HARDCODED_SECRET"
    MISSING_INPUT_VALIDATION = "MISSING_INPUT_VALIDATION"
    INSECURE_DESERIALIZATION = "INSECURE_DESERIALIZATION"
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    COMMAND_INJECTION = "COMMAND_INJECTION"


class SessionStatus(str, Enum):
    INJECTED = "injected"
    SCANNED = "scanned"
    GRADED = "graded"


class PlatformType(str, Enum):
    TELEGRAM = "telegram"
    SLACK = "slack"
    DISCORD = "discord"


class LetterGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


# --- Core Domain Models ---


class UserContext(BaseModel):
    """Incoming user context from chat platform."""

    platform_id: str
    platform_type: PlatformType
    username: str
    display_name: str | None = None


class User(BaseModel):
    """Persisted user record."""

    id: UUID = Field(default_factory=uuid4)
    platform_id: str
    platform_type: PlatformType
    username: str
    display_name: str | None = None
    is_active: bool = True
    opt_out: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SourceFile(BaseModel):
    """A source code file to analyze."""

    path: str
    content: str
    language: str


class CandidateVulnerability(BaseModel):
    """A generated vulnerability candidate from the LLM."""

    vuln_type: VulnerabilityType
    file_path: str
    line_number: int
    original_code: str
    injected_code: str
    explanation: str


class InjectionRecord(BaseModel):
    """A single applied injection."""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    vuln_type: VulnerabilityType
    difficulty: DifficultyLevel
    file_path: str
    line_number: int
    original_code: str
    injected_code: str
    description: str
    detected: bool = False
    detection_time_ms: int | None = None


class InjectionManifest(BaseModel):
    """Complete record of all injections in a session."""

    session_id: UUID
    injections: list[InjectionRecord]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def count(self) -> int:
        return len(self.injections)

    def has_valid_prefixes(self) -> bool:
        """Check that all HARDCODED_SECRET injections use the Safe_Prefix."""
        for inj in self.injections:
            if inj.vuln_type == VulnerabilityType.HARDCODED_SECRET:
                if "EVIL_MENTOR_FAKE_" not in inj.injected_code:
                    return False
        return True


class TrainingSession(BaseModel):
    """A single training session record."""

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    intent_id: str
    repo_path: str
    branch_name: str
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    status: SessionStatus = SessionStatus.INJECTED
    injected_at: datetime = Field(default_factory=datetime.utcnow)
    scanned_at: datetime | None = None
    graded_at: datetime | None = None


class ScanFinding(BaseModel):
    """A single finding from an ArmorClaw scan."""

    finding_type: str
    severity: str
    file_path: str
    line_number: int


class MatchedVuln(BaseModel):
    """An injection that was correctly detected."""

    injection: InjectionRecord
    finding: ScanFinding
    type_match: bool  # True if finding_type matches vuln_type


class MissedVuln(BaseModel):
    """An injection that was not detected."""

    injection: InjectionRecord
    hint: str


class FalsePositive(BaseModel):
    """A scan finding that doesn't match any injection."""

    finding: ScanFinding


class ScoreBreakdown(BaseModel):
    """Detailed score calculation."""

    found_points: int
    type_bonus_points: int
    missed_penalty: int
    false_positive_penalty: int
    speed_bonus: int
    total_score: int
    detection_rate: float  # 0.0 to 1.0


class GradeReport(BaseModel):
    """Complete grading report for a session."""

    session_id: UUID
    score_breakdown: ScoreBreakdown
    letter_grade: LetterGrade
    matched: list[MatchedVuln]
    missed: list[MissedVuln]
    false_positives: list[FalsePositive]
    feedback: str
    difficulty: DifficultyLevel
    time_elapsed_seconds: float


class GradeRecord(BaseModel):
    """Persisted grade record."""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    score: int
    letter_grade: LetterGrade
    speed_bonus: int
    missed_penalty: int
    fp_penalty: int
    feedback: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LeaderboardEntry(BaseModel):
    """A single row in the leaderboard."""

    user_id: UUID
    username: str
    display_name: str | None
    total_score: int
    sessions_completed: int
    avg_score: float
    best_score: int
    weakest_area: VulnerabilityType | None
    rank: int


class UserStats(BaseModel):
    """Cumulative statistics for a single user."""

    user_id: UUID
    total_score: int
    sessions_completed: int
    avg_score: float
    best_score: int
    weakest_area: VulnerabilityType | None
    rank: int


class WeeklyStats(BaseModel):
    """Aggregated weekly team statistics."""

    total_sessions: int
    avg_score: float
    top_performer: str | None


class RateLimitResult(BaseModel):
    """Result of a rate limit check."""

    allowed: bool
    current_count: int
    max_per_day: int
    resets_at: datetime


class ChatResponse(BaseModel):
    """Response sent back to the chat platform."""

    text: str
    attachments: list[dict] | None = None
