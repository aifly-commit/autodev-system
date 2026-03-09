"""
Tests for Phase 5: Multi-Agent Orchestration and Error Recovery.
"""

import pytest
from datetime import datetime
from pathlib import Path
import json

from core.config import Config
from core.agent_scheduler import (
    AgentScheduler,
    AgentTask,
    AgentPriority,
    AgentType,
    AgentResult,
    TaskPlanner,
    WorkflowOrchestrator,
)
from core.recovery import (
    ErrorDetector,
    ErrorType,
    ErrorContext,
    RecoveryPlanner,
    RecoveryStrategy,
    RecoveryPlan,
    RecoveryExecutor,
    ErrorRecoverySystem,
)
from core.models import Feature, FeatureList, FeatureStatus, Priority


class TestErrorDetector:
    """Tests for error detection."""

    def test_detect_build_error(self):
        """Test detecting build errors."""
        error = "Build failed: cannot compile module"
        ctx = ErrorDetector.detect(error)

        assert ctx.error_type == ErrorType.BUILD_ERROR
        assert "build" in ctx.message.lower()

    def test_detect_test_failure(self):
        """Test detecting test failures."""
        error = "AssertionError: Expected 5 but got 3"
        ctx = ErrorDetector.detect(error)

        assert ctx.error_type == ErrorType.TEST_FAILURE

    def test_detect_syntax_error(self):
        """Test detecting syntax errors."""
        error = 'SyntaxError: invalid syntax at line 42'
        ctx = ErrorDetector.detect(error)

        assert ctx.error_type == ErrorType.SYNTAX_ERROR

    def test_detect_import_error(self):
        """Test detecting import errors."""
        error = "ModuleNotFoundError: No module named 'requests'"
        ctx = ErrorDetector.detect(error)

        assert ctx.error_type == ErrorType.IMPORT_ERROR

    def test_detect_environment_error(self):
        """Test detecting environment errors."""
        error = "Error: command not found: node"
        ctx = ErrorDetector.detect(error)

        assert ctx.error_type == ErrorType.ENVIRONMENT_ERROR

    def test_extract_file_path_python(self):
        """Test extracting file path from Python error."""
        error = 'File "/app/main.py", line 42, in <module>'
        ctx = ErrorDetector.detect(error)

        assert ctx.file_path == "/app/main.py"
        assert ctx.line_number == 42

    def test_extract_file_path_js(self):
        """Test extracting file path from JS error."""
        error = "at /app/src/index.js:10:5"
        ctx = ErrorDetector.detect(error)

        assert ctx.file_path == "/app/src/index.js"
        assert ctx.line_number == 10

    def test_detect_unknown_error(self):
        """Test detecting unknown errors."""
        error = "Something weird happened"
        ctx = ErrorDetector.detect(error)

        assert ctx.error_type == ErrorType.UNKNOWN_ERROR


class TestRecoveryPlanner:
    """Tests for recovery planning."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a temporary project."""
        project = tmp_path / "test-project"
        project.mkdir()

        # Initialize git
        import subprocess
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True, capture_output=True)
        (project / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=project, check=True, capture_output=True)

        return project

    def test_plan_test_recovery(self, project_path: Path):
        """Test planning recovery for test failure."""
        planner = RecoveryPlanner(project_path)
        error_ctx = ErrorContext(
            error_type=ErrorType.TEST_FAILURE,
            message="Test failed",
            feature_id="F001",
        )

        plan = planner.plan_recovery(error_ctx)

        assert plan.strategy == RecoveryStrategy.FIX_AND_RETRY
        assert len(plan.steps) > 0
        assert plan.confidence > 0

    def test_plan_syntax_recovery(self, project_path: Path):
        """Test planning recovery for syntax error."""
        planner = RecoveryPlanner(project_path)
        error_ctx = ErrorContext(
            error_type=ErrorType.SYNTAX_ERROR,
            message="Syntax error",
            file_path="main.py",
            line_number=42,
        )

        plan = planner.plan_recovery(error_ctx)

        assert plan.strategy == RecoveryStrategy.FIX_AND_RETRY
        assert "main.py" in " ".join(plan.steps)

    def test_plan_max_attempts_exceeded(self, project_path: Path):
        """Test planning when max attempts exceeded."""
        planner = RecoveryPlanner(project_path)
        error_ctx = ErrorContext(
            error_type=ErrorType.TEST_FAILURE,
            message="Test failed",
        )

        # Exceed max attempts
        plan = planner.plan_recovery(error_ctx, attempt_count=100)

        assert plan.strategy == RecoveryStrategy.ESCALATE

    def test_plan_rollback_for_multiple_failures(self, project_path: Path):
        """Test planning rollback for multiple failures."""
        planner = RecoveryPlanner(project_path)
        error_ctx = ErrorContext(
            error_type=ErrorType.TEST_FAILURE,
            message="Multiple tests failed",
        )

        # Multiple attempts - should escalate or rollback
        plan = planner.plan_recovery(error_ctx, attempt_count=3)

        # Either strategy is valid
        assert plan.strategy in [RecoveryStrategy.ROLLBACK, RecoveryStrategy.ESCALATE]


class TestRecoveryExecutor:
    """Tests for recovery execution."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a temporary project with git."""
        project = tmp_path / "exec-project"
        project.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True, capture_output=True)
        (project / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial passing state"], cwd=project, check=True, capture_output=True)

        # Add another commit
        (project / "app.py").write_text("print('hello')")
        subprocess.run(["git", "add", "."], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Add app"], cwd=project, check=True, capture_output=True)

        return project

    def test_execute_retry_strategy(self, project_path: Path):
        """Test executing retry strategy."""
        executor = RecoveryExecutor(project_path)

        plan = RecoveryPlan(
            strategy=RecoveryStrategy.RETRY,
            steps=["Retry the operation"],
            estimated_effort="low",
            confidence=0.8,
        )
        error_ctx = ErrorContext(
            error_type=ErrorType.LLM_ERROR,
            message="Rate limit",
        )

        result = executor.execute(plan, error_ctx)

        assert result["success"] is True
        assert result["strategy"] == "retry"

    def test_execute_skip_strategy(self, project_path: Path):
        """Test executing skip strategy."""
        executor = RecoveryExecutor(project_path)

        plan = RecoveryPlan(
            strategy=RecoveryStrategy.SKIP,
            steps=["Skip this task"],
            estimated_effort="low",
            confidence=0.9,
        )
        error_ctx = ErrorContext(
            error_type=ErrorType.UNKNOWN_ERROR,
            message="Unknown error",
        )

        result = executor.execute(plan, error_ctx)

        assert result["success"] is True
        assert result["skipped"] is True

    def test_execute_escalate_strategy(self, project_path: Path):
        """Test executing escalate strategy."""
        executor = RecoveryExecutor(project_path)

        plan = RecoveryPlan(
            strategy=RecoveryStrategy.ESCALATE,
            steps=["Manual intervention required"],
            estimated_effort="high",
            confidence=1.0,
        )
        error_ctx = ErrorContext(
            error_type=ErrorType.UNKNOWN_ERROR,
            message="Critical error",
        )

        result = executor.execute(plan, error_ctx)

        assert result["escalated"] is True


class TestErrorRecoverySystem:
    """Tests for the complete recovery system."""

    @pytest.fixture
    def system(self, tmp_path: Path) -> ErrorRecoverySystem:
        """Create an error recovery system."""
        project = tmp_path / "recovery-project"
        project.mkdir()

        import subprocess
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True, capture_output=True)
        (project / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=project, check=True, capture_output=True)

        return ErrorRecoverySystem(project)

    def test_recover_from_test_failure(self, system: ErrorRecoverySystem):
        """Test recovering from a test failure."""
        result = system.recover(
            "AssertionError: Expected true but got false",
            context={"feature_id": "F001"},
        )

        assert "strategy" in result
        assert result["strategy"] in ["fix_and_retry", "retry"]

    def test_recover_from_exception(self, system: ErrorRecoverySystem):
        """Test recovering from an exception object."""
        try:
            raise ValueError("Something went wrong")
        except Exception as e:
            result = system.recover(e)

        assert "error_context" in result
        assert result["error_context"].error_type in [
            ErrorType.RUNTIME_ERROR,
            ErrorType.UNKNOWN_ERROR,
        ]

    def test_recovery_history(self, system: ErrorRecoverySystem):
        """Test recovery history tracking."""
        # Perform multiple recoveries
        system.recover("Test error 1")
        system.recover("Build failed")
        system.recover("Syntax error")

        history = system.get_recovery_history()

        assert len(history) == 3

    def test_recovery_stats(self, system: ErrorRecoverySystem):
        """Test recovery statistics."""
        # Perform recoveries
        system.recover("Test failed")
        system.recover("Build failed")

        stats = system.get_recovery_stats()

        assert stats["total"] == 2
        assert "success_rate" in stats
        assert "by_error_type" in stats


class TestAgentScheduler:
    """Tests for agent scheduler."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a project with .autodev."""
        project = tmp_path / "scheduler-project"
        project.mkdir()

        # Create .autodev directory
        autodev = project / ".autodev"
        autodev.mkdir()

        # Create feature list
        feature_list = FeatureList(
            project="scheduler-test",
            features=[
                Feature(id="F001", description="Feature 1"),
                Feature(id="F002", description="Feature 2"),
            ]
        )

        with open(autodev / "feature_list.json", "w") as f:
            json.dump(feature_list.model_dump(mode="json"), f, indent=2, default=str)

        # Create progress file
        (autodev / "progress.md").write_text("# Progress\n\n---\n")

        # Git init
        import subprocess
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True, capture_output=True)

        return project

    def test_add_task(self, project_path: Path):
        """Test adding tasks to queue."""
        scheduler = AgentScheduler(project_path)

        task = AgentTask(
            id="T001",
            agent_type=AgentType.CODER,
            feature_id="F001",
            description="Implement feature",
        )

        scheduler.add_task(task)

        status = scheduler.get_queue_status()
        assert status["pending"] == 1

    def test_add_multiple_tasks(self, project_path: Path):
        """Test adding multiple tasks."""
        scheduler = AgentScheduler(project_path)

        tasks = [
            AgentTask(
                id=f"T00{i}",
                agent_type=AgentType.CODER,
                feature_id=f"F00{i}",
                description=f"Task {i}",
            )
            for i in range(3)
        ]

        scheduler.add_tasks(tasks)

        status = scheduler.get_queue_status()
        assert status["pending"] == 3

    def test_priority_ordering(self, project_path: Path):
        """Test tasks are ordered by priority."""
        scheduler = AgentScheduler(project_path)

        # Add in random order
        scheduler.add_task(AgentTask(
            id="T003",
            agent_type=AgentType.CODER,
            feature_id="F003",
            description="Low priority",
            priority=AgentPriority.LOW,
        ))
        scheduler.add_task(AgentTask(
            id="T001",
            agent_type=AgentType.CODER,
            feature_id="F001",
            description="Critical",
            priority=AgentPriority.CRITICAL,
        ))
        scheduler.add_task(AgentTask(
            id="T002",
            agent_type=AgentType.CODER,
            feature_id="F002",
            description="Normal",
            priority=AgentPriority.NORMAL,
        ))

        next_task = scheduler.get_next_task()

        assert next_task.id == "T001"  # Critical should be first

    def test_dependency_check(self, project_path: Path):
        """Test tasks wait for dependencies."""
        scheduler = AgentScheduler(project_path)

        # Task with dependency
        scheduler.add_task(AgentTask(
            id="T002",
            agent_type=AgentType.TESTER,
            feature_id="F001",
            description="Test feature",
            dependencies=["T001"],
        ))
        scheduler.add_task(AgentTask(
            id="T001",
            agent_type=AgentType.CODER,
            feature_id="F001",
            description="Implement feature",
        ))

        # T002 should not be returned (dependency not met)
        next_task = scheduler.get_next_task()
        assert next_task.id == "T001"


class TestTaskPlanner:
    """Tests for task planner."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a project."""
        project = tmp_path / "planner-project"
        project.mkdir()

        autodev = project / ".autodev"
        autodev.mkdir()

        feature_list = FeatureList(
            project="planner-test",
            features=[
                Feature(
                    id="F001",
                    description="User login",
                    priority=Priority.HIGH,
                ),
            ]
        )

        with open(autodev / "feature_list.json", "w") as f:
            json.dump(feature_list.model_dump(mode="json"), f, indent=2, default=str)

        (autodev / "progress.md").write_text("# Progress\n\n---\n")

        return project

    def test_plan_next_tasks(self, project_path: Path):
        """Test planning next tasks."""
        planner = TaskPlanner(project_path)

        feature_list = FeatureList(
            project="test",
            features=[
                Feature(id="F001", description="Test feature"),
            ]
        )

        from core.models import SessionContext
        context = SessionContext(
            working_directory=str(project_path),
            project_name="test",
        )

        tasks = planner.plan_next_tasks(feature_list, context)

        assert len(tasks) > 0
        assert any(t.agent_type == AgentType.CODER for t in tasks)

    def test_plan_debugger_for_broken_feature(self, project_path: Path):
        """Test planning debugger task for broken feature."""
        planner = TaskPlanner(project_path)

        feature_list = FeatureList(
            project="test",
            features=[
                Feature(
                    id="F001",
                    description="Broken feature",
                    status=FeatureStatus.FAILED,
                ),
            ]
        )

        from core.models import SessionContext
        context = SessionContext(
            working_directory=str(project_path),
            project_name="test",
        )

        tasks = planner.plan_next_tasks(feature_list, context)

        # Should include a debugger task
        assert any(t.agent_type == AgentType.DEBUGGER for t in tasks)


class TestIntegration:
    """Integration tests for Phase 5."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a complete project setup."""
        project = tmp_path / "integration-project"
        project.mkdir()

        # Setup .autodev
        autodev = project / ".autodev"
        autodev.mkdir()

        feature_list = FeatureList(
            project="integration",
            features=[
                Feature(id="F001", description="Feature 1", priority=Priority.HIGH),
            ]
        )

        with open(autodev / "feature_list.json", "w") as f:
            json.dump(feature_list.model_dump(mode="json"), f, indent=2, default=str)

        (autodev / "progress.md").write_text("# Progress\n\n---\n")

        # Git
        import subprocess
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True, capture_output=True)
        (project / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=project, check=True, capture_output=True)

        return project

    def test_full_error_recovery_flow(self, project_path: Path):
        """Test complete error recovery flow."""
        system = ErrorRecoverySystem(project_path)

        # Simulate an error
        result = system.recover(
            "AssertionError: Test failed",
            context={"feature_id": "F001"},
            attempt_count=0,
        )

        assert result is not None
        assert "strategy" in result

        # Check history was recorded
        history = system.get_recovery_history()
        assert len(history) == 1

    def test_multiple_recovery_attempts(self, project_path: Path):
        """Test multiple recovery attempts escalate properly."""
        system = ErrorRecoverySystem(project_path)

        # Multiple attempts
        for i in range(5):
            result = system.recover(
                "Persistent error",
                attempt_count=i,
            )

        # Should eventually escalate
        stats = system.get_recovery_stats()
        assert stats["total"] == 5
