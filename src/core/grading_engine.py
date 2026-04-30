"""Grading Engine for Evil Mentor.

Compares ArmorClaw scan findings against the injection manifest to produce
scores, letter grades, and LLM-generated personalized feedback.
"""

import logging
from datetime import datetime, timezone

from src.models.domain import (
    DifficultyLevel,
    FalsePositive,
    GradeReport,
    InjectionManifest,
    InjectionRecord,
    LetterGrade,
    MatchedVuln,
    MissedVuln,
    ScanFinding,
    ScoreBreakdown,
    TrainingSession,
)
from src.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class GradingEngine:
    """Auto-grading and scoring for training sessions.

    Compares ArmorClaw scan findings against the injection manifest,
    calculates scores with bonuses and penalties, assigns letter grades,
    and generates LLM-powered personalized feedback.
    """

    LINE_TOLERANCE = 5  # findings within ±5 lines count as a match

    SCORING = {
        "found": 10,              # +10 per correctly identified vuln
        "missed_penalty": -5,     # -5 per missed vuln
        "type_bonus": 2,          # +2 for correct type identification
        "false_positive_penalty": -3,
    }

    GRADE_THRESHOLDS = {
        "A": 0.90,
        "B": 0.70,
        "C": 0.50,
        "D": 0.30,
    }  # Below 0.30 → "F"

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm_service = llm_service

    async def grade_session(
        self,
        session: TrainingSession,
        scan_results: list[ScanFinding],
        injection_manifest: InjectionManifest,
    ) -> GradeReport:
        """Compare scan findings against manifest and produce a grade report.

        Full grading pipeline:
        1. Match findings to injections (file path + line proximity)
        2. Calculate score with bonuses and penalties
        3. Assign letter grade based on detection rate
        4. Generate personalized LLM feedback

        Args:
            session: The training session being graded.
            scan_results: Findings from the ArmorClaw scan.
            injection_manifest: The manifest of injected vulnerabilities.

        Returns:
            A complete ``GradeReport`` with score, grade, and feedback.
        """
        # Step 1: Match findings to injections
        matched, missed, false_positives = self._match_findings(
            scan_results, injection_manifest.injections
        )

        # Step 2: Calculate session duration
        now = datetime.now(timezone.utc)
        injected_at = session.injected_at
        # Handle naive datetimes by assuming UTC
        if injected_at.tzinfo is None:
            injected_at = injected_at.replace(tzinfo=timezone.utc)
        session_duration = (now - injected_at).total_seconds()

        # Step 3: Calculate score
        score_breakdown = self._calculate_score(
            matched, missed, false_positives, session_duration
        )

        # Step 4: Assign letter grade
        letter_grade = self._assign_letter_grade(score_breakdown.detection_rate)

        # Step 5: Generate feedback
        feedback = await self._generate_feedback(
            matched, missed, session.difficulty
        )

        return GradeReport(
            session_id=session.id,
            score_breakdown=score_breakdown,
            letter_grade=letter_grade,
            matched=matched,
            missed=missed,
            false_positives=false_positives,
            feedback=feedback,
            difficulty=session.difficulty,
            time_elapsed_seconds=session_duration,
        )

    def _match_findings(
        self,
        findings: list[ScanFinding],
        injections: list[InjectionRecord],
    ) -> tuple[list[MatchedVuln], list[MissedVuln], list[FalsePositive]]:
        """Match scan findings to injections using file path + line proximity.

        A finding matches an injection when:
        - The file paths are equal
        - ``|finding.line_number - injection.line_number| <= LINE_TOLERANCE``

        Each injection can be matched at most once (first matching finding wins).
        Each finding can match at most once. Unmatched injections become missed,
        unmatched findings become false positives.

        Args:
            findings: Scan findings from ArmorClaw.
            injections: Injection records from the manifest.

        Returns:
            Tuple of (matched, missed, false_positives).
        """
        matched: list[MatchedVuln] = []
        matched_injection_ids: set = set()
        matched_finding_indices: set[int] = set()

        # Try to match each injection to a finding
        for injection in injections:
            for idx, finding in enumerate(findings):
                if idx in matched_finding_indices:
                    continue
                if (
                    finding.file_path == injection.file_path
                    and abs(finding.line_number - injection.line_number)
                    <= self.LINE_TOLERANCE
                ):
                    # Check if the finding type matches the vulnerability type
                    type_match = (
                        finding.finding_type == injection.vuln_type.value
                    )
                    matched.append(
                        MatchedVuln(
                            injection=injection,
                            finding=finding,
                            type_match=type_match,
                        )
                    )
                    matched_injection_ids.add(injection.id)
                    matched_finding_indices.add(idx)
                    break

        # Build missed list — injections that were not matched
        missed: list[MissedVuln] = []
        for injection in injections:
            if injection.id not in matched_injection_ids:
                missed.append(
                    MissedVuln(
                        injection=injection,
                        hint=(
                            f"Look for {injection.vuln_type.value} issues near "
                            f"line {injection.line_number} in {injection.file_path}"
                        ),
                    )
                )

        # Build false positives list
        false_positives: list[FalsePositive] = [
            FalsePositive(finding=finding)
            for idx, finding in enumerate(findings)
            if idx not in matched_finding_indices
        ]

        return matched, missed, false_positives

    def _calculate_score(
        self,
        matched: list[MatchedVuln],
        missed: list[MissedVuln],
        false_positives: list[FalsePositive],
        session_duration_seconds: float,
    ) -> ScoreBreakdown:
        """Calculate total score with speed bonus and penalties.

        Scoring formula:
        - +10 per correctly identified vulnerability
        - +2 bonus per correct type identification
        - -5 per missed vulnerability
        - -3 per false positive
        - Speed bonus: max(0, 300 - duration_in_minutes) capped at 60

        Args:
            matched: Successfully matched vulnerabilities.
            missed: Missed vulnerabilities.
            false_positives: False positive findings.
            session_duration_seconds: Time elapsed in seconds.

        Returns:
            A ``ScoreBreakdown`` with all components and total.
        """
        found_points = len(matched) * self.SCORING["found"]

        type_bonus_points = sum(
            self.SCORING["type_bonus"] for m in matched if m.type_match
        )

        missed_penalty = len(missed) * abs(self.SCORING["missed_penalty"])

        false_positive_penalty = len(false_positives) * abs(
            self.SCORING["false_positive_penalty"]
        )

        # Speed bonus: reward faster sessions
        # max(0, 300 - minutes) capped at 60
        duration_minutes = session_duration_seconds / 60.0
        speed_bonus = max(0, min(60, int(300 - duration_minutes)))

        total_score = (
            found_points
            + type_bonus_points
            + speed_bonus
            - missed_penalty
            - false_positive_penalty
        )

        # Detection rate: fraction of injections found
        total_injections = len(matched) + len(missed)
        detection_rate = (
            len(matched) / total_injections if total_injections > 0 else 0.0
        )

        return ScoreBreakdown(
            found_points=found_points,
            type_bonus_points=type_bonus_points,
            missed_penalty=missed_penalty,
            false_positive_penalty=false_positive_penalty,
            speed_bonus=speed_bonus,
            total_score=total_score,
            detection_rate=detection_rate,
        )

    def _assign_letter_grade(self, detection_rate: float) -> LetterGrade:
        """Assign A/B/C/D/F based on detection rate thresholds.

        - A: detection_rate >= 0.90
        - B: detection_rate >= 0.70
        - C: detection_rate >= 0.50
        - D: detection_rate >= 0.30
        - F: detection_rate < 0.30

        Args:
            detection_rate: Fraction of injections detected (0.0 to 1.0).

        Returns:
            The corresponding ``LetterGrade``.
        """
        if detection_rate >= self.GRADE_THRESHOLDS["A"]:
            return LetterGrade.A
        if detection_rate >= self.GRADE_THRESHOLDS["B"]:
            return LetterGrade.B
        if detection_rate >= self.GRADE_THRESHOLDS["C"]:
            return LetterGrade.C
        if detection_rate >= self.GRADE_THRESHOLDS["D"]:
            return LetterGrade.D
        return LetterGrade.F

    async def _generate_feedback(
        self,
        matched: list[MatchedVuln],
        missed: list[MissedVuln],
        difficulty: DifficultyLevel,
    ) -> str:
        """Use LLM to generate personalized improvement feedback.

        Builds a prompt summarizing what the developer found and missed,
        then asks Gemini for actionable improvement advice.

        Args:
            matched: Successfully matched vulnerabilities.
            missed: Missed vulnerabilities.
            difficulty: The session's difficulty level.

        Returns:
            Personalized feedback string, or a fallback message if the
            LLM is unavailable.
        """
        if self._llm_service is None:
            return self._fallback_feedback(matched, missed, difficulty)

        # Build the prompt
        found_summary = "\n".join(
            f"- Found {m.injection.vuln_type.value} in {m.injection.file_path} "
            f"(line {m.injection.line_number})"
            f"{' — type correctly identified' if m.type_match else ''}"
            for m in matched
        )

        missed_summary = "\n".join(
            f"- Missed {m.injection.vuln_type.value} in "
            f"{m.injection.file_path} (line {m.injection.line_number})"
            for m in missed
        )

        prompt = (
            f"A developer just completed a security training session at "
            f"{difficulty.value} difficulty.\n\n"
            f"Vulnerabilities found ({len(matched)}):\n"
            f"{found_summary or '(none)'}\n\n"
            f"Vulnerabilities missed ({len(missed)}):\n"
            f"{missed_summary or '(none)'}\n\n"
            f"Please provide concise, actionable feedback (3-5 sentences) "
            f"to help the developer improve their security detection skills. "
            f"Focus on the types of vulnerabilities they missed and suggest "
            f"specific techniques or patterns to look for."
        )

        system_instruction = (
            "You are a security training mentor. Provide encouraging but "
            "honest feedback to help developers improve their ability to "
            "detect security vulnerabilities in code. Be specific and "
            "actionable."
        )

        result = self._llm_service.generate_content(
            prompt=prompt,
            system_instruction=system_instruction,
        )

        if result is None:
            logger.warning("LLM feedback generation failed, using fallback")
            return self._fallback_feedback(matched, missed, difficulty)

        return result

    def _fallback_feedback(
        self,
        matched: list[MatchedVuln],
        missed: list[MissedVuln],
        difficulty: DifficultyLevel,
    ) -> str:
        """Generate basic feedback without LLM.

        Used when the LLM service is unavailable or returns None.
        """
        total = len(matched) + len(missed)
        if total == 0:
            return "No vulnerabilities were injected in this session."

        rate = len(matched) / total
        parts = [
            f"You found {len(matched)} out of {total} vulnerabilities "
            f"at {difficulty.value} difficulty ({rate:.0%} detection rate)."
        ]

        if missed:
            missed_types = set(m.injection.vuln_type.value for m in missed)
            parts.append(
                f"Focus on improving detection of: {', '.join(sorted(missed_types))}."
            )

        if rate >= 0.9:
            parts.append("Excellent work! Keep it up.")
        elif rate >= 0.7:
            parts.append("Good job! A bit more practice and you'll master this.")
        elif rate >= 0.5:
            parts.append(
                "Decent effort. Review the missed vulnerability types "
                "and practice scanning for those patterns."
            )
        else:
            parts.append(
                "Keep practicing! Try reviewing common vulnerability patterns "
                "and scanning techniques for the types you missed."
            )

        return " ".join(parts)
