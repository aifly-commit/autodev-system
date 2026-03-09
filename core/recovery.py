"""
Error recovery system for AutoDev.

Implements automatic detection and recovery from various failure states.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from core.config import Config
from core.exceptions import (
    AutoDevError,
    EnvironmentNotHealthy,
    FeatureListError,
    GitError,
    LLMError,
    SessionError,
    TestError,
)
from core.models import Feature, FeatureList, FeatureStatus, ProgressEntry
from core.tools.git_ops import GitOperations
from core.progress_manager import ProgressManager

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """Types of errors that can occur."""
    BUILD_ERROR = "build_error"
    TEST_FAILURE = "test_failure"
    LINT_ERROR = "lint_error"
    TYPE_ERROR = "type_error"
    IMPORT_ERROR = "import_error"
    SYNTAX_ERROR = "syntax_error"
    RUNTIME_ERROR = "runtime_error"
    ENVIRONMENT_ERROR = "environment_error"
    DEPENDENCY_ERROR = "dependency_error"
    GIT_ERROR = "git_error"
    LLM_ERROR = "llm_error"
    UNKNOWN_ERROR = "unknown_error"


class RecoveryStrategy(str, Enum):
    """Strategies for error recovery."""
    RETRY = "retry"                    # Simply retry the operation
    ROLLBACK = "rollback"              # Revert to last known good state
    FIX_AND_RETRY = "fix_and_retry"    # Attempt to fix the error, then retry
    SKIP = "skip"                      # Skip this task and move on
    ABORT = "abort"                    # Stop execution
    ESCALATE = "escalate"              # Request human intervention


@dataclass
class ErrorContext:
    """Context about an error that occurred."""
    error_type: ErrorType
    message: str
    feature_id: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    stack_trace: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    raw_error: Optional[Exception] = None


@dataclass
class RecoveryPlan:
    """A plan for recovering from an error."""
    strategy: RecoveryStrategy
    steps: List[str]
    estimated_effort: str  # "low", "medium", "high"
    confidence: float  # 0.0 to 1.0
    rollback_commit: Optional[str] = None
    alternative_approach: Optional[str] = None


class ErrorDetector:
    """
    Detects and classifies errors in the project.

    Analyzes error output to determine type and severity.
    """

    @staticmethod
    def detect(error_output: str, context: Optional[Dict[str, Any]] = None) -> ErrorContext:
        """
        Detect error type from output.

        Args:
            error_output: Error message or output.
            context: Additional context.

        Returns:
            ErrorContext with classified error.
        """
        context = context or {}
        error_lower = error_output.lower()

        # Detect error type based on patterns
        error_type = ErrorType.UNKNOWN_ERROR
        file_path = None
        line_number = None

        # Build errors
        if any(pattern in error_lower for pattern in ["build failed", "compilation error", "cannot compile"]):
            error_type = ErrorType.BUILD_ERROR

        # Test failures
        elif any(pattern in error_lower for pattern in ["test failed", "assertionerror", "expected", "actual"]):
            error_type = ErrorType.TEST_FAILURE

        # Lint errors
        elif any(pattern in error_lower for pattern in ["lint error", "eslint", "flake8", "pylint"]):
            error_type = ErrorType.LINT_ERROR

        # Type errors
        elif any(pattern in error_lower for pattern in ["typeerror", "type error", "type mismatch"]):
            error_type = ErrorType.TYPE_ERROR

        # Import errors
        elif any(pattern in error_lower for pattern in ["importerror", "modulenotfound", "cannot find module"]):
            error_type = ErrorType.IMPORT_ERROR

        # Syntax errors
        elif any(pattern in error_lower for pattern in ["syntaxerror", "syntax error", "unexpected token"]):
            error_type = ErrorType.SYNTAX_ERROR

        # Runtime errors
        elif any(pattern in error_lower for pattern in ["runtimeerror", "runtime error", "exception"]):
            error_type = ErrorType.RUNTIME_ERROR

        # Environment errors
        elif any(pattern in error_lower for pattern in ["environment", "not found", "command not found", "enoent"]):
            error_type = ErrorType.ENVIRONMENT_ERROR

        # Dependency errors
        elif any(pattern in error_lower for pattern in ["dependency", "package not found", "version conflict"]):
            error_type = ErrorType.DEPENDENCY_ERROR

        # Git errors
        elif any(pattern in error_lower for pattern in ["git:", "fatal:", "merge conflict"]):
            error_type = ErrorType.GIT_ERROR

        # Extract file path and line number
        import re

        # Python style: File "path/to/file.py", line 42
        py_match = re.search(r'File "([^"]+)", line (\d+)', error_output)
        if py_match:
            file_path = py_match.group(1)
            line_number = int(py_match.group(2))

        # JavaScript style: at path/to/file.js:42:10
        js_match = re.search(r'at\s+([^\s]+):(\d+):(\d+)', error_output)
        if js_match:
            file_path = js_match.group(1)
            line_number = int(js_match.group(2))

        # Generic style: file.py:42
        generic_match = re.search(r'([^\s:]+\.py):(\d+)', error_output)
        if generic_match and not file_path:
            file_path = generic_match.group(1)
            line_number = int(generic_match.group(2))

        return ErrorContext(
            error_type=error_type,
            message=error_output[:1000],  # Truncate long messages
            feature_id=context.get("feature_id"),
            file_path=file_path,
            line_number=line_number,
            stack_trace=error_output,
            context=context,
        )


class RecoveryPlanner:
    """
    Plans recovery strategies for errors.

    Determines the best approach to recover from failures.
    """

    def __init__(
        self,
        project_path: Path,
        config: Optional[Config] = None,
    ):
        self.project_path = Path(project_path)
        self.config = config or Config()
        self.git_ops = GitOperations(project_path, config)

    def plan_recovery(
        self,
        error_context: ErrorContext,
        attempt_count: int = 0,
    ) -> RecoveryPlan:
        """
        Create a recovery plan for an error.

        Args:
            error_context: Context about the error.
            attempt_count: Number of previous recovery attempts.

        Returns:
            RecoveryPlan with strategy and steps.
        """
        logger.info(f"Planning recovery for {error_context.error_type.value}")

        # Check if we've exceeded max attempts
        max_attempts = self.config.execution.retry_attempts
        if attempt_count >= max_attempts:
            return RecoveryPlan(
                strategy=RecoveryStrategy.ESCALATE,
                steps=["Exceeded maximum recovery attempts", "Manual intervention required"],
                estimated_effort="high",
                confidence=1.0,
            )

        # Get strategy based on error type
        strategies = {
            ErrorType.BUILD_ERROR: self._plan_build_recovery,
            ErrorType.TEST_FAILURE: self._plan_test_recovery,
            ErrorType.LINT_ERROR: self._plan_lint_recovery,
            ErrorType.TYPE_ERROR: self._plan_type_recovery,
            ErrorType.IMPORT_ERROR: self._plan_import_recovery,
            ErrorType.SYNTAX_ERROR: self._plan_syntax_recovery,
            ErrorType.RUNTIME_ERROR: self._plan_runtime_recovery,
            ErrorType.ENVIRONMENT_ERROR: self._plan_environment_recovery,
            ErrorType.DEPENDENCY_ERROR: self._plan_dependency_recovery,
            ErrorType.GIT_ERROR: self._plan_git_recovery,
            ErrorType.LLM_ERROR: self._plan_llm_recovery,
            ErrorType.UNKNOWN_ERROR: self._plan_unknown_recovery,
        }

        planner = strategies.get(error_context.error_type, self._plan_unknown_recovery)
        return planner(error_context, attempt_count)

    def _plan_build_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for build errors."""
        return RecoveryPlan(
            strategy=RecoveryStrategy.FIX_AND_RETRY,
            steps=[
                "Analyze build error output",
                "Identify missing or incorrect code",
                "Fix the identified issues",
                "Re-run build",
            ],
            estimated_effort="medium",
            confidence=0.7,
        )

    def _plan_test_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for test failures."""
        if attempts < 2:
            return RecoveryPlan(
                strategy=RecoveryStrategy.FIX_AND_RETRY,
                steps=[
                    "Analyze test failure message",
                    "Identify what the test expects vs what the code does",
                    "Fix the implementation or test",
                    "Re-run the test",
                ],
                estimated_effort="low",
                confidence=0.8,
            )
        else:
            # Multiple failures - might need rollback
            last_good_commit = self._find_last_good_commit()
            return RecoveryPlan(
                strategy=RecoveryStrategy.ROLLBACK,
                steps=[
                    f"Multiple test failures detected",
                    f"Rollback to last known good state: {last_good_commit or 'initial'}",
                    "Re-approach the feature with different strategy",
                ],
                estimated_effort="medium",
                confidence=0.6,
                rollback_commit=last_good_commit,
            )

    def _plan_lint_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for lint errors."""
        return RecoveryPlan(
            strategy=RecoveryStrategy.FIX_AND_RETRY,
            steps=[
                "Review lint errors",
                "Fix code style issues",
                "Re-run linter",
            ],
            estimated_effort="low",
            confidence=0.9,
        )

    def _plan_type_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for type errors."""
        return RecoveryPlan(
            strategy=RecoveryStrategy.FIX_AND_RETRY,
            steps=[
                "Analyze type error",
                "Fix type annotations or type mismatches",
                "Re-run type checker",
            ],
            estimated_effort="medium",
            confidence=0.7,
        )

    def _plan_import_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for import errors."""
        return RecoveryPlan(
            strategy=RecoveryStrategy.FIX_AND_RETRY,
            steps=[
                "Identify missing module or package",
                "Install missing dependency or fix import path",
                "Re-run the operation",
            ],
            estimated_effort="low",
            confidence=0.8,
        )

    def _plan_syntax_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for syntax errors."""
        return RecoveryPlan(
            strategy=RecoveryStrategy.FIX_AND_RETRY,
            steps=[
                f"Locate syntax error in {error.file_path or 'file'}",
                f"Fix syntax at line {error.line_number}" if error.line_number else "Fix syntax error",
                "Re-run the operation",
            ],
            estimated_effort="low",
            confidence=0.9,
        )

    def _plan_runtime_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for runtime errors."""
        if attempts < 2:
            return RecoveryPlan(
                strategy=RecoveryStrategy.FIX_AND_RETRY,
                steps=[
                    "Analyze runtime error and stack trace",
                    "Identify root cause",
                    "Fix the issue",
                    "Re-run with additional logging",
                ],
                estimated_effort="medium",
                confidence=0.6,
            )
        else:
            return RecoveryPlan(
                strategy=RecoveryStrategy.ROLLBACK,
                steps=[
                    "Multiple runtime errors detected",
                    "Rollback to stable state",
                    "Re-approach with different implementation",
                ],
                estimated_effort="high",
                confidence=0.5,
                rollback_commit=self._find_last_good_commit(),
            )

    def _plan_environment_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for environment errors."""
        return RecoveryPlan(
            strategy=RecoveryStrategy.FIX_AND_RETRY,
            steps=[
                "Check if required tools are installed",
                "Verify environment configuration",
                "Run init.sh to set up environment",
                "Retry the operation",
            ],
            estimated_effort="medium",
            confidence=0.7,
        )

    def _plan_dependency_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for dependency errors."""
        return RecoveryPlan(
            strategy=RecoveryStrategy.FIX_AND_RETRY,
            steps=[
                "Identify missing or conflicting dependencies",
                "Update dependency files",
                "Re-install dependencies",
                "Retry the operation",
            ],
            estimated_effort="medium",
            confidence=0.7,
        )

    def _plan_git_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for git errors."""
        error_lower = error.message.lower()

        if "merge conflict" in error_lower:
            return RecoveryPlan(
                strategy=RecoveryStrategy.FIX_AND_RETRY,
                steps=[
                    "Identify files with merge conflicts",
                    "Resolve conflicts appropriately",
                    "Complete the merge/rebase",
                ],
                estimated_effort="medium",
                confidence=0.6,
            )
        else:
            return RecoveryPlan(
                strategy=RecoveryStrategy.ROLLBACK,
                steps=[
                    "Reset to last known good state",
                    "Retry the operation",
                ],
                estimated_effort="low",
                confidence=0.8,
                rollback_commit=self._find_last_good_commit(),
            )

    def _plan_llm_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for LLM errors."""
        return RecoveryPlan(
            strategy=RecoveryStrategy.RETRY,
            steps=[
                "Wait briefly for rate limit reset" if "rate" in error.message.lower() else "Retry LLM call",
                "Use exponential backoff if needed",
            ],
            estimated_effort="low",
            confidence=0.5,
        )

    def _plan_unknown_recovery(self, error: ErrorContext, attempts: int) -> RecoveryPlan:
        """Plan recovery for unknown errors."""
        if attempts < 2:
            return RecoveryPlan(
                strategy=RecoveryStrategy.RETRY,
                steps=[
                    "Unknown error - attempt retry",
                    "Monitor for patterns",
                ],
                estimated_effort="low",
                confidence=0.3,
            )
        else:
            return RecoveryPlan(
                strategy=RecoveryStrategy.ESCALATE,
                steps=[
                    "Unknown error persists after retries",
                    "Manual investigation required",
                    "Document error for future handling",
                ],
                estimated_effort="high",
                confidence=1.0,
            )

    def _find_last_good_commit(self) -> Optional[str]:
        """Find the last commit where tests passed."""
        try:
            # Look for commits with passing test messages
            commits = self.git_ops.log(20)

            for commit in commits:
                message = commit.get("message", "").lower()
                if any(pattern in message for pattern in ["passing", "passed", "complete", "working"]):
                    return commit.get("hash")

            # Return the second-to-last commit as fallback
            if len(commits) >= 2:
                return commits[1].get("hash")

        except Exception as e:
            logger.warning(f"Could not find last good commit: {e}")

        return None


class RecoveryExecutor:
    """
    Executes recovery strategies.

    Carries out the planned recovery actions.
    """

    def __init__(
        self,
        project_path: Path,
        config: Optional[Config] = None,
    ):
        self.project_path = Path(project_path)
        self.config = config or Config()
        self.git_ops = GitOperations(project_path, config)
        self.planner = RecoveryPlanner(project_path, config)

    def execute(
        self,
        plan: RecoveryPlan,
        error_context: ErrorContext,
    ) -> Dict[str, Any]:
        """
        Execute a recovery plan.

        Args:
            plan: Recovery plan to execute.
            error_context: Original error context.

        Returns:
            Result of recovery execution.
        """
        logger.info(f"Executing recovery strategy: {plan.strategy.value}")

        result = {
            "strategy": plan.strategy.value,
            "success": False,
            "steps_completed": [],
            "error": None,
        }

        try:
            if plan.strategy == RecoveryStrategy.RETRY:
                result["success"] = True  # Caller should retry

            elif plan.strategy == RecoveryStrategy.ROLLBACK:
                result["success"] = self._execute_rollback(plan)

            elif plan.strategy == RecoveryStrategy.FIX_AND_RETRY:
                result["success"] = self._execute_fix_and_retry(plan, error_context)

            elif plan.strategy == RecoveryStrategy.SKIP:
                result["success"] = True
                result["skipped"] = True

            elif plan.strategy == RecoveryStrategy.ABORT:
                result["success"] = False
                result["aborted"] = True

            elif plan.strategy == RecoveryStrategy.ESCALATE:
                result["success"] = False
                result["escalated"] = True

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Recovery execution failed: {e}")

        return result

    def _execute_rollback(self, plan: RecoveryPlan) -> bool:
        """Execute rollback strategy."""
        if plan.rollback_commit:
            try:
                # Stash any current changes
                self.git_ops.stash("auto-stash-before-rollback")

                # Reset to the good commit
                subprocess.run(
                    ["git", "reset", "--hard", plan.rollback_commit],
                    cwd=self.project_path,
                    check=True,
                    capture_output=True,
                )

                logger.info(f"Rolled back to commit {plan.rollback_commit}")
                return True

            except Exception as e:
                logger.error(f"Rollback failed: {e}")
                return False
        else:
            logger.warning("No rollback commit specified")
            return False

    def _execute_fix_and_retry(
        self,
        plan: RecoveryPlan,
        error_context: ErrorContext,
    ) -> bool:
        """
        Execute fix and retry strategy.

        This returns True to signal that the caller should retry
        the original operation. The actual fixing is done by
        the agent that receives the error context.
        """
        # Log the fix plan for the agent to use
        fix_log = self.project_path / ".autodev" / "fix_plan.json"
        fix_log.parent.mkdir(parents=True, exist_ok=True)

        with open(fix_log, "w") as f:
            json.dump({
                "error_context": {
                    "type": error_context.error_type.value,
                    "message": error_context.message,
                    "file_path": error_context.file_path,
                    "line_number": error_context.line_number,
                },
                "recovery_steps": plan.steps,
                "timestamp": datetime.now().isoformat(),
            }, f, indent=2)

        logger.info(f"Created fix plan at {fix_log}")
        return True


class ErrorRecoverySystem:
    """
    Complete error recovery system.

    Combines detection, planning, and execution for automatic recovery.
    """

    def __init__(
        self,
        project_path: Path,
        config: Optional[Config] = None,
    ):
        self.project_path = Path(project_path)
        self.config = config or Config()

        self.detector = ErrorDetector()
        self.planner = RecoveryPlanner(project_path, config)
        self.executor = RecoveryExecutor(project_path, config)

        # Recovery history
        self._recovery_history: List[Dict[str, Any]] = []

    def recover(
        self,
        error: Union[str, Exception],
        context: Optional[Dict[str, Any]] = None,
        attempt_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Attempt to recover from an error.

        Args:
            error: Error message or exception.
            context: Additional context.
            attempt_count: Number of previous attempts.

        Returns:
            Recovery result with next action.
        """
        # Convert exception to string
        if isinstance(error, Exception):
            error_message = str(error)
            raw_error = error
        else:
            error_message = error
            raw_error = None

        # Detect error type
        error_context = self.detector.detect(error_message, context)
        error_context.raw_error = raw_error

        # Plan recovery
        recovery_plan = self.planner.plan_recovery(error_context, attempt_count)

        # Execute recovery
        result = self.executor.execute(recovery_plan, error_context)

        # Record in history
        self._recovery_history.append({
            "timestamp": datetime.now().isoformat(),
            "error_type": error_context.error_type.value,
            "strategy": recovery_plan.strategy.value,
            "success": result["success"],
            "attempt": attempt_count + 1,
        })

        return {
            **result,
            "error_context": error_context,
            "plan": {
                "strategy": recovery_plan.strategy.value,
                "steps": recovery_plan.steps,
            },
        }

    def get_recovery_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent recovery history."""
        return self._recovery_history[-limit:]

    def get_recovery_stats(self) -> Dict[str, Any]:
        """Get statistics about recoveries."""
        if not self._recovery_history:
            return {"total": 0}

        successful = sum(1 for r in self._recovery_history if r["success"])
        by_type: Dict[str, int] = {}
        by_strategy: Dict[str, int] = {}

        for record in self._recovery_history:
            error_type = record["error_type"]
            by_type[error_type] = by_type.get(error_type, 0) + 1

            strategy = record["strategy"]
            by_strategy[strategy] = by_strategy.get(strategy, 0) + 1

        return {
            "total": len(self._recovery_history),
            "successful": successful,
            "success_rate": successful / len(self._recovery_history),
            "by_error_type": by_type,
            "by_strategy": by_strategy,
        }


# Import Union for type hint
from typing import Union
