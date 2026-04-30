"""Message Handler for Evil Mentor.

Entry point for all chat commands. Receives routed messages from the
OpenClaw Gateway and dispatches to the appropriate handler method.

Supported commands:
- ``/train``       — start a new training session
- ``/grade``       — grade the most recent training session
- ``/stats``       — show user statistics
- ``/leaderboard`` — show top-ranked developers
- ``/optout``      — toggle opt-out status
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from src.config import Settings
from src.core.grading_engine import GradingEngine
from src.core.injection_generator import InjectionGenerator
from src.core.vulnerability_engine import VulnerabilityEngine
from src.database.repositories import (
    GradeRepository,
    InjectionRepository,
    ScanResultRepository,
    SessionRepository,
    UserRepository,
)
from src.models.domain import (
    ChatResponse,
    DifficultyLevel,
    GradeRecord,
    InjectionManifest,
    ScanFinding,
    SessionStatus,
    TrainingSession,
    User,
    UserContext,
    UserStats,
)
from src.services.armorclaw_service import ArmorClawService
from src.services.git_service import GitService
from src.services.leaderboard_service import LeaderboardService
from src.services.rate_limiter import RateLimiter
from src.utils.training_hours import get_training_window_message, is_within_training_hours

logger = logging.getLogger(__name__)

# Known commands (without the leading slash) for dispatch.
_KNOWN_COMMANDS: set[str] = {"train", "grade", "stats", "leaderboard", "optout"}


class MessageHandler:
    """Routes slash commands to the appropriate handler.

    Acts as the orchestration layer between chat commands and the
    underlying engines / services.  Every public ``handle_*`` method
    returns a :class:`ChatResponse`.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        vulnerability_engine: VulnerabilityEngine,
        injection_generator: InjectionGenerator,
        grading_engine: GradingEngine,
        git_service: GitService,
        armorclaw_service: ArmorClawService,
        rate_limiter: RateLimiter,
        leaderboard_service: LeaderboardService,
        user_repo: UserRepository,
        session_repo: SessionRepository,
        injection_repo: InjectionRepository,
        scan_result_repo: ScanResultRepository,
        grade_repo: GradeRepository,
    ) -> None:
        self._settings = settings
        self._vuln_engine = vulnerability_engine
        self._injection_gen = injection_generator
        self._grading_engine = grading_engine
        self._git = git_service
        self._armorclaw = armorclaw_service
        self._rate_limiter = rate_limiter
        self._leaderboard = leaderboard_service
        self._user_repo = user_repo
        self._session_repo = session_repo
        self._injection_repo = injection_repo
        self._scan_result_repo = scan_result_repo
        self._grade_repo = grade_repo

    # ------------------------------------------------------------------
    # Top-level dispatcher
    # ------------------------------------------------------------------

    async def handle(
        self,
        command: str,
        args: list[str],
        user_context: UserContext,
    ) -> ChatResponse:
        """Dispatch a slash command to its handler.

        Args:
            command: The command string (e.g. ``"train"``, ``"/train"``).
                Leading slashes are stripped automatically.
            args: Positional arguments following the command.
            user_context: Caller identity from the chat platform.

        Returns:
            A :class:`ChatResponse` with the result text.
        """
        # Normalise: strip leading "/" if present, lowercase.
        cmd = command.lstrip("/").strip().lower()

        if cmd == "train":
            return await self.handle_train(args, user_context)
        elif cmd == "grade":
            return await self.handle_grade(user_context)
        elif cmd == "stats":
            return await self.handle_stats(user_context)
        elif cmd == "leaderboard":
            return await self.handle_leaderboard()
        elif cmd == "optout":
            return await self.handle_optout(user_context)
        else:
            return await self.handle_unknown(command)

    # ------------------------------------------------------------------
    # /train
    # ------------------------------------------------------------------

    async def handle_train(
        self,
        args: list[str],
        user_context: UserContext,
    ) -> ChatResponse:
        """Start a new training session.

        Orchestration flow:
        1. Resolve or create the user record.
        2. Check opt-out status (Req 14.4).
        3. Check rate limit (Req 5.7, 14.2).
        4. Check training hours (Req 5.6).
        5. ArmorIQ policy gate (Req 5.2, 5.3).
        6. Create training branch (Req 4.1).
        7. Generate vulnerabilities via LLM (Req 2.1).
        8. Apply injections (Req 3.1).
        9. Validate manifest safe prefix (Req 12.1, 12.2).
        10. Commit changes (Req 4.2).
        11. Store session + injections in DB (Req 9.4, 9.5).
        12. Return success response.

        Args:
            args: ``[repo_path]`` and optionally ``[difficulty]``.
            user_context: Caller identity.
        """
        # --- Parse arguments ---
        if not args:
            return ChatResponse(
                text=(
                    "Usage: /train <repo_path> [difficulty]\n"
                    "Difficulty levels: EASY, MEDIUM, HARD (default: MEDIUM)"
                )
            )

        repo_path = args[0]
        difficulty = DifficultyLevel.MEDIUM
        if len(args) >= 2:
            try:
                difficulty = DifficultyLevel(args[1].upper())
            except ValueError:
                return ChatResponse(
                    text=(
                        f"Invalid difficulty '{args[1]}'. "
                        "Choose from: EASY, MEDIUM, HARD."
                    )
                )

        # --- 1. Resolve user ---
        user = await self._get_or_create_user(user_context)

        # --- 2. Opt-out check (Req 14.4) ---
        if user.opt_out:
            return ChatResponse(
                text=(
                    "You have opted out of training. "
                    "Send /optout to re-enable training."
                )
            )

        # --- 3. Rate limit check (Req 5.7, 14.2) ---
        rate_result = await self._rate_limiter.check_and_increment(
            str(user.id), self._settings.MAX_INJECTIONS_PER_DAY
        )
        if not rate_result.allowed:
            return ChatResponse(
                text=(
                    f"Daily limit of {rate_result.max_per_day} sessions reached. "
                    f"Resets at {rate_result.resets_at.strftime('%Y-%m-%d %H:%M UTC')}."
                )
            )

        # --- 4. Training hours check (Req 5.6) ---
        current_hour = datetime.now(timezone.utc).hour
        if not is_within_training_hours(
            current_hour,
            self._settings.TRAINING_START_HOUR,
            self._settings.TRAINING_END_HOUR,
        ):
            return ChatResponse(
                text=get_training_window_message(
                    self._settings.TRAINING_START_HOUR,
                    self._settings.TRAINING_END_HOUR,
                )
            )

        # --- 5. ArmorIQ policy gate (Req 5.2, 5.3) ---
        session_id = uuid4()
        intent_token = None

        if not self._settings.SKIP_ARMORIQ:
            plan_steps = [
                {
                    "action": "create_training_branch",
                    "mcp": "evil-mentor-mcp",
                },
                {
                    "action": "inject_vulnerabilities",
                    "mcp": "evil-mentor-mcp",
                },
                {
                    "action": "commit_injections",
                    "mcp": "evil-mentor-mcp",
                },
            ]

            try:
                intent_token = await self._armorclaw.capture_and_get_token(
                    plan_steps=plan_steps,
                    prompt=f"Evil Mentor training session {session_id} for user {user.username}",
                )
            except Exception as exc:
                logger.error("ArmorIQ policy gate failed: %s", exc, exc_info=True)
                return ChatResponse(
                    text="Policy verification failed. Please try again."
                )
        else:
            logger.info("ArmorIQ policy gate skipped (SKIP_ARMORIQ=true)")

        # --- 6. Create training branch (Req 4.1) ---
        try:
            branch_name = await self._git.create_training_branch(
                repo_path=repo_path,
                session_id=str(session_id),
            )
        except Exception as exc:
            logger.error("Failed to create training branch: %s", exc, exc_info=True)
            return ChatResponse(
                text="Failed to create training branch. Check repo access."
            )

        # --- 7. Generate vulnerabilities (Req 2.1) ---
        try:
            # Read source files from the repo (simplified: use repo_path)
            from src.models.domain import SourceFile
            import os

            source_files = []
            for root, _dirs, files in os.walk(repo_path):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, repo_path)
                    ext = os.path.splitext(fname)[1].lower()
                    lang_map = {
                        ".py": "python", ".js": "javascript", ".ts": "typescript",
                        ".java": "java", ".go": "go", ".rs": "rust",
                        ".rb": "ruby", ".php": "php", ".c": "c", ".cpp": "cpp",
                        ".cs": "csharp", ".swift": "swift", ".kt": "kotlin",
                        ".scala": "scala", ".sh": "shell",
                    }
                    lang = lang_map.get(ext)
                    if lang:
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()
                            source_files.append(
                                SourceFile(path=rel_path, content=content, language=lang)
                            )
                        except OSError:
                            continue

            candidates = await self._vuln_engine.generate_vulnerabilities(
                source_files=source_files,
                difficulty=difficulty,
                count=5,
            )
        except Exception as exc:
            logger.error("Vulnerability generation failed: %s", exc, exc_info=True)
            # Clean up the branch
            await self._git.delete_training_branch(repo_path, branch_name)
            return ChatResponse(
                text="Vulnerability generation failed. Please retry."
            )

        if not candidates:
            await self._git.delete_training_branch(repo_path, branch_name)
            return ChatResponse(
                text="No suitable vulnerabilities could be generated for this codebase. "
                     "Try a different repository or difficulty level."
            )

        # --- 8. Apply injections (Req 3.1) ---
        try:
            manifest = await self._injection_gen.apply_injections(
                candidates=candidates,
                repo_path=repo_path,
                branch_name=branch_name,
                session_id=str(session_id),
            )
        except Exception as exc:
            logger.error("Injection failed: %s", exc, exc_info=True)
            await self._git.delete_training_branch(repo_path, branch_name)
            return ChatResponse(
                text="Failed to apply injections. Session aborted."
            )

        # --- 9. Validate manifest (Req 12.1, 12.2) ---
        if not self._injection_gen.validate_manifest(manifest):
            await self._git.delete_training_branch(repo_path, branch_name)
            return ChatResponse(
                text="Safety check failed — injection aborted and reverted."
            )

        # --- 10. Commit changes (Req 4.2) ---
        try:
            await self._git.commit_injections(
                repo_path=repo_path,
                branch_name=branch_name,
                session_id=str(session_id),
                injection_count=manifest.count,
            )
        except Exception as exc:
            logger.error("Commit failed: %s", exc, exc_info=True)
            await self._git.delete_training_branch(repo_path, branch_name)
            return ChatResponse(
                text="Failed to commit injections. Session aborted."
            )

        # --- 11. Store session + injections (Req 9.4, 9.5) ---
        try:
            session = TrainingSession(
                id=session_id,
                user_id=user.id,
                intent_id=intent_token.token_id if intent_token else "demo-mode",
                repo_path=repo_path,
                branch_name=branch_name,
                difficulty=difficulty,
                status=SessionStatus.INJECTED,
            )
            await self._session_repo.create(session)
            await self._injection_repo.create_many(manifest.injections)
        except Exception as exc:
            logger.error("Failed to store session data: %s", exc, exc_info=True)
            # Session is committed on the branch but DB failed — log and continue
            return ChatResponse(
                text=(
                    f"Training session started on branch `{branch_name}` "
                    f"with {manifest.count} injected vulnerabilities "
                    f"at {difficulty.value} difficulty.\n\n"
                    "⚠️ Warning: session metadata could not be saved to the database."
                )
            )

        # --- 12. Success response ---
        return ChatResponse(
            text=(
                f"🎯 Training session started!\n\n"
                f"• Branch: `{branch_name}`\n"
                f"• Vulnerabilities injected: {manifest.count}\n"
                f"• Difficulty: {difficulty.value}\n"
                f"• Session ID: {session_id}\n\n"
                f"Use ArmorClaw to scan the branch, then run /grade to see your results."
            )
        )

    # ------------------------------------------------------------------
    # /grade
    # ------------------------------------------------------------------

    async def handle_grade(self, user_context: UserContext) -> ChatResponse:
        """Grade the most recent training session.

        Orchestration flow:
        1. Resolve user.
        2. Get latest session.
        3. ArmorIQ policy gate.
        4. Run ArmorClaw scan (via ArmorIQ invoke).
        5. Compare findings vs manifest.
        6. Calculate score & generate feedback.
        7. Store grade record.
        8. Update leaderboard.
        9. Return report.
        """
        # --- 1. Resolve user ---
        user = await self._get_or_create_user(user_context)

        # --- 2. Get latest session ---
        session = await self._session_repo.get_latest_for_user(user.id)
        if session is None:
            return ChatResponse(
                text="No training session found. Start one with /train <repo_path>."
            )

        # --- 3. ArmorIQ policy gate ---
        intent_token = None

        if not self._settings.SKIP_ARMORIQ:
            plan_steps = [
                {"action": "run_scan", "mcp": "armorclaw-mcp"},
                {"action": "grade_session", "mcp": "evil-mentor-mcp"},
            ]

            try:
                intent_token = await self._armorclaw.capture_and_get_token(
                    plan_steps=plan_steps,
                    prompt=f"Evil Mentor grading session {session.id} for user {user.username}",
                )
            except Exception as exc:
                logger.error("ArmorIQ policy gate failed for grading: %s", exc, exc_info=True)
                return ChatResponse(
                    text="Policy verification failed. Please try again."
                )
        else:
            logger.info("ArmorIQ policy gate skipped for grading (SKIP_ARMORIQ=true)")

        # --- 4. Run ArmorClaw scan ---
        scan_findings: list[ScanFinding] = []

        if not self._settings.SKIP_ARMORIQ and intent_token is not None:
            try:
                scan_result = await self._armorclaw.invoke_action(
                    mcp_name="armorclaw-mcp",
                    action_name="run_scan",
                    intent_token=intent_token,
                    params={
                        "repo_path": session.repo_path,
                        "branch_name": session.branch_name,
                    },
                )

                raw_findings = scan_result.result if hasattr(scan_result, "result") else []
                if isinstance(raw_findings, list):
                    for f in raw_findings:
                        if isinstance(f, dict):
                            try:
                                scan_findings.append(ScanFinding(**f))
                            except Exception:
                                logger.warning("Skipping malformed scan finding: %s", f)
            except Exception as exc:
                logger.error("ArmorClaw scan failed: %s", exc, exc_info=True)
                return ChatResponse(
                    text="Security scan failed. Check ArmorClaw installation."
                )
        else:
            logger.info("ArmorClaw scan skipped (SKIP_ARMORIQ=true) — grading with empty scan results")

        # Store scan results
        try:
            await self._scan_result_repo.create(
                id=str(uuid4()),
                session_id=session.id,
                total_findings=len(scan_findings),
                raw_output=[f.model_dump() for f in scan_findings],
                created_at=datetime.now(timezone.utc),
            )
            session.scanned_at = datetime.now(timezone.utc)
            session.status = SessionStatus.SCANNED
            await self._session_repo.update(session)
        except Exception as exc:
            logger.warning("Failed to store scan results: %s", exc)

        # --- 5-6. Grade session ---
        injection_records = await self._injection_repo.get_by_session(session.id)
        manifest = InjectionManifest(
            session_id=session.id,
            injections=injection_records,
        )

        try:
            grade_report = await self._grading_engine.grade_session(
                session=session,
                scan_results=scan_findings,
                injection_manifest=manifest,
            )
        except Exception as exc:
            logger.error("Grading failed: %s", exc, exc_info=True)
            return ChatResponse(text="Grading failed. Please try again.")

        # --- 7. Store grade record ---
        try:
            grade_record = GradeRecord(
                session_id=session.id,
                score=grade_report.score_breakdown.total_score,
                letter_grade=grade_report.letter_grade,
                speed_bonus=grade_report.score_breakdown.speed_bonus,
                missed_penalty=grade_report.score_breakdown.missed_penalty,
                fp_penalty=grade_report.score_breakdown.false_positive_penalty,
                feedback=grade_report.feedback,
            )
            await self._grade_repo.create(grade_record)

            session.graded_at = datetime.now(timezone.utc)
            session.status = SessionStatus.GRADED
            await self._session_repo.update(session)
        except Exception as exc:
            logger.warning("Failed to store grade record: %s", exc)

        # --- 8. Update leaderboard ---
        try:
            missed_types = [m.injection.vuln_type.value for m in grade_report.missed]
            await self._leaderboard.update_after_grading(
                user_id=user.id,
                session_score=grade_report.score_breakdown.total_score,
                vuln_types_missed=missed_types,
            )
        except Exception as exc:
            logger.warning("Failed to update leaderboard: %s", exc)

        # --- 9. Return report ---
        return self._format_grade_report(grade_report)

    # ------------------------------------------------------------------
    # /stats
    # ------------------------------------------------------------------

    async def handle_stats(self, user_context: UserContext) -> ChatResponse:
        """Retrieve and format user statistics.

        Returns total score, sessions completed, average score, best
        score, and weakest vulnerability area (Req 1.4).
        """
        user = await self._get_or_create_user(user_context)
        stats = await self._leaderboard.get_user_stats(user.id)
        return self._format_user_stats(stats)

    # ------------------------------------------------------------------
    # /leaderboard
    # ------------------------------------------------------------------

    async def handle_leaderboard(self) -> ChatResponse:
        """Retrieve and format the top-ranked developers (Req 1.5)."""
        entries = await self._leaderboard.get_leaderboard(limit=10)

        if not entries:
            return ChatResponse(text="No leaderboard data yet. Start training with /train!")

        lines = ["🏆 **Leaderboard — Top Developers**\n"]
        for entry in entries:
            medal = ""
            if entry.rank == 1:
                medal = "🥇 "
            elif entry.rank == 2:
                medal = "🥈 "
            elif entry.rank == 3:
                medal = "🥉 "

            display = entry.display_name or entry.username
            lines.append(
                f"{medal}**#{entry.rank}** {display} — "
                f"{entry.total_score} pts "
                f"({entry.sessions_completed} sessions, "
                f"avg {entry.avg_score:.1f})"
            )

        return ChatResponse(text="\n".join(lines))

    # ------------------------------------------------------------------
    # /optout
    # ------------------------------------------------------------------

    async def handle_optout(self, user_context: UserContext) -> ChatResponse:
        """Toggle opt-out status for a user (Req 1.6, 14.3)."""
        user = await self._get_or_create_user(user_context)

        user.opt_out = not user.opt_out
        await self._user_repo.update(user)

        if user.opt_out:
            return ChatResponse(
                text=(
                    "You have opted out of Evil Mentor training. "
                    "You will no longer receive training sessions.\n"
                    "Send /optout again to re-enable training."
                )
            )
        else:
            return ChatResponse(
                text=(
                    "Welcome back! You have opted back in to Evil Mentor training. "
                    "Use /train to start a new session."
                )
            )

    # ------------------------------------------------------------------
    # Unknown command
    # ------------------------------------------------------------------

    async def handle_unknown(self, command: str) -> ChatResponse:
        """Return help message listing all available commands (Req 1.7)."""
        return ChatResponse(
            text=(
                f"Unknown command: {command}\n\n"
                "Available commands:\n"
                "• /train <repo_path> [difficulty] — Start a new training session with injected vulnerabilities\n"
                "• /grade — Grade your most recent training session using ArmorClaw scan results\n"
                "• /stats — View your training statistics (score, sessions, average, best, weakest area)\n"
                "• /leaderboard — View the top-ranked developers by cumulative score\n"
                "• /optout — Toggle your opt-out status for training sessions"
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_create_user(self, ctx: UserContext) -> User:
        """Look up an existing user by platform identity, or create one."""
        user = await self._user_repo.get_by_platform_id(
            ctx.platform_id, ctx.platform_type
        )
        if user is not None:
            return user

        user = User(
            platform_id=ctx.platform_id,
            platform_type=ctx.platform_type,
            username=ctx.username,
            display_name=ctx.display_name,
        )
        return await self._user_repo.create(user)

    @staticmethod
    def _format_user_stats(stats: UserStats) -> ChatResponse:
        """Format a UserStats object into a chat-friendly message."""
        weakest = stats.weakest_area.value if stats.weakest_area else "N/A"

        if stats.sessions_completed == 0:
            return ChatResponse(
                text=(
                    "📊 **Your Stats**\n\n"
                    "No training sessions completed yet. "
                    "Start with /train to begin!"
                )
            )

        return ChatResponse(
            text=(
                f"📊 **Your Stats**\n\n"
                f"• Total Score: {stats.total_score}\n"
                f"• Sessions Completed: {stats.sessions_completed}\n"
                f"• Average Score: {stats.avg_score:.1f}\n"
                f"• Best Score: {stats.best_score}\n"
                f"• Weakest Area: {weakest}\n"
                f"• Rank: #{stats.rank}"
            )
        )

    @staticmethod
    def _format_grade_report(report) -> ChatResponse:
        """Format a GradeReport into a chat-friendly message."""
        sb = report.score_breakdown
        found_count = len(report.matched)
        missed_count = len(report.missed)
        fp_count = len(report.false_positives)
        total_injected = found_count + missed_count

        lines = [
            f"📝 **Grade Report — Session {report.session_id}**\n",
            f"• Letter Grade: **{report.letter_grade.value}**",
            f"• Total Score: {sb.total_score}",
            f"• Detection Rate: {sb.detection_rate:.0%} ({found_count}/{total_injected})",
            f"• Difficulty: {report.difficulty.value}",
            f"• Time Elapsed: {report.time_elapsed_seconds / 60:.1f} minutes\n",
            "**Score Breakdown:**",
            f"  Found: +{sb.found_points}",
            f"  Type Bonus: +{sb.type_bonus_points}",
            f"  Speed Bonus: +{sb.speed_bonus}",
            f"  Missed Penalty: -{sb.missed_penalty}",
            f"  False Positive Penalty: -{sb.false_positive_penalty}\n",
        ]

        if report.missed:
            lines.append("**Missed Vulnerabilities:**")
            for m in report.missed:
                lines.append(f"  • {m.injection.vuln_type.value} in {m.injection.file_path} — {m.hint}")
            lines.append("")

        if report.feedback:
            lines.append(f"**Feedback:**\n{report.feedback}")

        return ChatResponse(text="\n".join(lines))
