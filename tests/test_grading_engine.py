"""Unit tests for GradingEngine."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.grading_engine import GradingEngine
from src.models.domain import (
    DifficultyLevel,
    FalsePositive,
    InjectionManifest,
    InjectionRecord,
    LetterGrade,
    MatchedVuln,
    MissedVuln,
    ScanFinding,
    SessionStatus,
    TrainingSession,
    VulnerabilityType,
)


# --- Helpers ---


def _make_session(
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM,
    injected_at: datetime | None = None,
) -> TrainingSession:
    return TrainingSession(
        id=uuid4(),
        user_id=uuid4(),
        intent_id="intent-123",
        repo_path="/tmp/repo",
        branch_name="evil-mentor/session-test",
        difficulty=difficulty,
        status=SessionStatus.SCANNED,
        injected_at=injected_at or datetime.now(timezone.utc) - timedelta(minutes=30),
    )


def _make_injection(
    file_path: str = "src/app.py",
    line_number: int = 10,
    vuln_type: VulnerabilityType = VulnerabilityType.SQL_INJECTION,
    session_id=None,
) -> InjectionRecord:
    return InjectionRecord(
        id=uuid4(),
        session_id=session_id or uuid4(),
        vuln_type=vuln_type,
        difficulty=DifficultyLevel.MEDIUM,
        file_path=file_path,
        line_number=line_number,
        original_code="original = code()",
        injected_code="injected = code()",
        description="Test injection",
    )


def _make_finding(
    file_path: str = "src/app.py",
    line_number: int = 10,
    finding_type: str = "SQL_INJECTION",
    severity: str = "HIGH",
) -> ScanFinding:
    return ScanFinding(
        finding_type=finding_type,
        severity=severity,
        file_path=file_path,
        line_number=line_number,
    )


def _make_manifest(injections: list[InjectionRecord]) -> InjectionManifest:
    sid = injections[0].session_id if injections else uuid4()
    return InjectionManifest(session_id=sid, injections=injections)


@pytest.fixture
def engine():
    """Create a GradingEngine with no LLM service (uses fallback feedback)."""
    return GradingEngine(llm_service=None)


@pytest.fixture
def engine_with_llm():
    """Create a GradingEngine with a mocked LLM service."""
    mock_llm = MagicMock()
    mock_llm.generate_content.return_value = "Great job! Keep practicing."
    return GradingEngine(llm_service=mock_llm), mock_llm


# --- Tests for _match_findings ---


class TestMatchFindings:
    """Tests for the finding-to-injection matching algorithm."""

    def test_exact_match(self, engine):
        inj = _make_injection(file_path="src/app.py", line_number=10)
        finding = _make_finding(file_path="src/app.py", line_number=10)

        matched, missed, fps = engine._match_findings([finding], [inj])

        assert len(matched) == 1
        assert len(missed) == 0
        assert len(fps) == 0
        assert matched[0].injection.id == inj.id

    def test_match_within_tolerance(self, engine):
        inj = _make_injection(file_path="src/app.py", line_number=10)
        finding = _make_finding(file_path="src/app.py", line_number=15)

        matched, missed, fps = engine._match_findings([finding], [inj])

        assert len(matched) == 1
        assert len(missed) == 0

    def test_match_at_negative_tolerance_boundary(self, engine):
        inj = _make_injection(file_path="src/app.py", line_number=15)
        finding = _make_finding(file_path="src/app.py", line_number=10)

        matched, missed, fps = engine._match_findings([finding], [inj])

        assert len(matched) == 1

    def test_no_match_beyond_tolerance(self, engine):
        inj = _make_injection(file_path="src/app.py", line_number=10)
        finding = _make_finding(file_path="src/app.py", line_number=16)

        matched, missed, fps = engine._match_findings([finding], [inj])

        assert len(matched) == 0
        assert len(missed) == 1
        assert len(fps) == 1

    def test_no_match_different_file(self, engine):
        inj = _make_injection(file_path="src/app.py", line_number=10)
        finding = _make_finding(file_path="src/other.py", line_number=10)

        matched, missed, fps = engine._match_findings([finding], [inj])

        assert len(matched) == 0
        assert len(missed) == 1
        assert len(fps) == 1

    def test_type_match_flag_true(self, engine):
        inj = _make_injection(vuln_type=VulnerabilityType.SQL_INJECTION)
        finding = _make_finding(finding_type="SQL_INJECTION")

        matched, _, _ = engine._match_findings([finding], [inj])

        assert matched[0].type_match is True

    def test_type_match_flag_false(self, engine):
        inj = _make_injection(vuln_type=VulnerabilityType.SQL_INJECTION)
        finding = _make_finding(finding_type="XSS")

        matched, _, _ = engine._match_findings([finding], [inj])

        assert matched[0].type_match is False

    def test_empty_findings_all_missed(self, engine):
        inj1 = _make_injection(line_number=10)
        inj2 = _make_injection(line_number=20)

        matched, missed, fps = engine._match_findings([], [inj1, inj2])

        assert len(matched) == 0
        assert len(missed) == 2
        assert len(fps) == 0

    def test_empty_injections_all_false_positives(self, engine):
        f1 = _make_finding(line_number=10)
        f2 = _make_finding(line_number=20)

        matched, missed, fps = engine._match_findings([f1, f2], [])

        assert len(matched) == 0
        assert len(missed) == 0
        assert len(fps) == 2

    def test_both_empty(self, engine):
        matched, missed, fps = engine._match_findings([], [])

        assert len(matched) == 0
        assert len(missed) == 0
        assert len(fps) == 0

    def test_one_finding_matches_one_injection_only(self, engine):
        """A single finding should not match multiple injections."""
        inj1 = _make_injection(file_path="src/app.py", line_number=10)
        inj2 = _make_injection(file_path="src/app.py", line_number=12)
        finding = _make_finding(file_path="src/app.py", line_number=11)

        matched, missed, fps = engine._match_findings([finding], [inj1, inj2])

        # The finding matches inj1 first (iterated first), inj2 is missed
        assert len(matched) == 1
        assert len(missed) == 1
        assert len(fps) == 0

    def test_missed_vuln_has_hint(self, engine):
        inj = _make_injection(
            file_path="src/app.py",
            line_number=42,
            vuln_type=VulnerabilityType.XSS,
        )

        _, missed, _ = engine._match_findings([], [inj])

        assert len(missed) == 1
        assert "XSS" in missed[0].hint
        assert "42" in missed[0].hint
        assert "src/app.py" in missed[0].hint


# --- Tests for _calculate_score ---


class TestCalculateScore:
    """Tests for score calculation."""

    def test_all_found_no_penalties(self, engine):
        matched = [
            MatchedVuln(
                injection=_make_injection(),
                finding=_make_finding(),
                type_match=True,
            )
        ]
        score = engine._calculate_score(matched, [], [], 1800.0)

        assert score.found_points == 10
        assert score.type_bonus_points == 2
        assert score.missed_penalty == 0
        assert score.false_positive_penalty == 0
        assert score.detection_rate == 1.0

    def test_missed_penalty(self, engine):
        missed = [MissedVuln(injection=_make_injection(), hint="hint")]
        score = engine._calculate_score([], missed, [], 1800.0)

        assert score.found_points == 0
        assert score.missed_penalty == 5
        assert score.detection_rate == 0.0

    def test_false_positive_penalty(self, engine):
        fps = [FalsePositive(finding=_make_finding())]
        score = engine._calculate_score([], [], fps, 1800.0)

        assert score.false_positive_penalty == 3

    def test_type_bonus_only_for_type_match(self, engine):
        m1 = MatchedVuln(
            injection=_make_injection(), finding=_make_finding(), type_match=True
        )
        m2 = MatchedVuln(
            injection=_make_injection(), finding=_make_finding(), type_match=False
        )
        score = engine._calculate_score([m1, m2], [], [], 1800.0)

        assert score.found_points == 20
        assert score.type_bonus_points == 2  # only m1

    def test_speed_bonus_fast_session(self, engine):
        # 10 minutes = 600 seconds → speed_bonus = min(60, 300 - 10) = 60
        score = engine._calculate_score([], [], [], 600.0)
        assert score.speed_bonus == 60

    def test_speed_bonus_slow_session(self, engine):
        # 400 minutes = 24000 seconds → speed_bonus = max(0, 300 - 400) = 0
        score = engine._calculate_score([], [], [], 24000.0)
        assert score.speed_bonus == 0

    def test_total_score_formula(self, engine):
        matched = [
            MatchedVuln(
                injection=_make_injection(), finding=_make_finding(), type_match=True
            ),
            MatchedVuln(
                injection=_make_injection(), finding=_make_finding(), type_match=False
            ),
        ]
        missed = [MissedVuln(injection=_make_injection(), hint="h")]
        fps = [FalsePositive(finding=_make_finding())]

        # 10 min session → speed_bonus = min(60, 300 - 10) = 60
        score = engine._calculate_score(matched, missed, fps, 600.0)

        expected = (2 * 10) + 2 + 60 - (1 * 5) - (1 * 3)
        assert score.total_score == expected

    def test_detection_rate_with_no_injections(self, engine):
        score = engine._calculate_score([], [], [], 1800.0)
        assert score.detection_rate == 0.0

    def test_detection_rate_partial(self, engine):
        matched = [
            MatchedVuln(
                injection=_make_injection(), finding=_make_finding(), type_match=True
            )
        ]
        missed = [
            MissedVuln(injection=_make_injection(), hint="h"),
            MissedVuln(injection=_make_injection(), hint="h"),
        ]
        score = engine._calculate_score(matched, missed, [], 1800.0)

        # 1 found out of 3 total
        assert abs(score.detection_rate - 1 / 3) < 0.001


# --- Tests for _assign_letter_grade ---


class TestAssignLetterGrade:
    """Tests for letter grade assignment."""

    def test_grade_a_at_threshold(self, engine):
        assert engine._assign_letter_grade(0.90) == LetterGrade.A

    def test_grade_a_above_threshold(self, engine):
        assert engine._assign_letter_grade(1.0) == LetterGrade.A

    def test_grade_b_at_threshold(self, engine):
        assert engine._assign_letter_grade(0.70) == LetterGrade.B

    def test_grade_b_just_below_a(self, engine):
        assert engine._assign_letter_grade(0.89) == LetterGrade.B

    def test_grade_c_at_threshold(self, engine):
        assert engine._assign_letter_grade(0.50) == LetterGrade.C

    def test_grade_d_at_threshold(self, engine):
        assert engine._assign_letter_grade(0.30) == LetterGrade.D

    def test_grade_f_below_d(self, engine):
        assert engine._assign_letter_grade(0.29) == LetterGrade.F

    def test_grade_f_at_zero(self, engine):
        assert engine._assign_letter_grade(0.0) == LetterGrade.F


# --- Tests for _generate_feedback ---


class TestGenerateFeedback:
    """Tests for feedback generation."""

    @pytest.mark.asyncio
    async def test_fallback_when_no_llm(self, engine):
        matched = [
            MatchedVuln(
                injection=_make_injection(), finding=_make_finding(), type_match=True
            )
        ]
        missed = [
            MissedVuln(
                injection=_make_injection(vuln_type=VulnerabilityType.XSS),
                hint="hint",
            )
        ]

        feedback = await engine._generate_feedback(
            matched, missed, DifficultyLevel.MEDIUM
        )

        assert "1 out of 2" in feedback
        assert "XSS" in feedback

    @pytest.mark.asyncio
    async def test_llm_feedback_used_when_available(self, engine_with_llm):
        eng, mock_llm = engine_with_llm

        feedback = await eng._generate_feedback([], [], DifficultyLevel.EASY)

        mock_llm.generate_content.assert_called_once()
        assert feedback == "Great job! Keep practicing."

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self, engine_with_llm):
        eng, mock_llm = engine_with_llm
        mock_llm.generate_content.return_value = None

        feedback = await eng._generate_feedback([], [], DifficultyLevel.EASY)

        assert isinstance(feedback, str)
        assert len(feedback) > 0

    @pytest.mark.asyncio
    async def test_fallback_no_injections(self, engine):
        feedback = await engine._generate_feedback([], [], DifficultyLevel.EASY)
        assert "No vulnerabilities" in feedback

    @pytest.mark.asyncio
    async def test_fallback_excellent_rate(self, engine):
        matched = [
            MatchedVuln(
                injection=_make_injection(), finding=_make_finding(), type_match=True
            )
            for _ in range(10)
        ]
        feedback = await engine._generate_feedback(
            matched, [], DifficultyLevel.HARD
        )
        assert "Excellent" in feedback


# --- Tests for grade_session ---


class TestGradeSession:
    """Tests for the full grading pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_all_found(self, engine):
        session = _make_session()
        sid = session.id
        inj = _make_injection(
            file_path="src/app.py",
            line_number=10,
            vuln_type=VulnerabilityType.SQL_INJECTION,
            session_id=sid,
        )
        manifest = _make_manifest([inj])
        finding = _make_finding(
            file_path="src/app.py",
            line_number=10,
            finding_type="SQL_INJECTION",
        )

        report = await engine.grade_session(session, [finding], manifest)

        assert report.session_id == session.id
        assert report.letter_grade == LetterGrade.A
        assert len(report.matched) == 1
        assert len(report.missed) == 0
        assert report.score_breakdown.detection_rate == 1.0
        assert isinstance(report.feedback, str)

    @pytest.mark.asyncio
    async def test_full_pipeline_none_found(self, engine):
        session = _make_session()
        sid = session.id
        inj = _make_injection(session_id=sid)
        manifest = _make_manifest([inj])

        report = await engine.grade_session(session, [], manifest)

        assert report.letter_grade == LetterGrade.F
        assert len(report.matched) == 0
        assert len(report.missed) == 1
        assert report.score_breakdown.detection_rate == 0.0

    @pytest.mark.asyncio
    async def test_report_includes_difficulty(self, engine):
        session = _make_session(difficulty=DifficultyLevel.HARD)
        manifest = _make_manifest([])

        report = await engine.grade_session(session, [], manifest)

        assert report.difficulty == DifficultyLevel.HARD

    @pytest.mark.asyncio
    async def test_report_time_elapsed_positive(self, engine):
        session = _make_session(
            injected_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        manifest = _make_manifest([])

        report = await engine.grade_session(session, [], manifest)

        assert report.time_elapsed_seconds > 0
