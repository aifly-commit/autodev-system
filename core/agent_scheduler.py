"""
Multi-agent scheduler for AutoDev.

Implements the multi-agent architecture where specialized agents
collaborate on different aspects of software development.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union

from core.config import Config
from core.models import Feature, FeatureList, ProgressEntry, SessionContext
from core.session_manager import SessionManager
from core.progress_manager import ProgressManager
from core.tools.git_ops import GitOperations

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Types of specialized agents."""
    INITIALIZER = "initializer"
    CODER = "coder"
    TESTER = "tester"
    REVIEWER = "reviewer"
    DEBUGGER = "debugger"
    DOCUMENTER = "documenter"


class AgentPriority(int, Enum):
    """Priority levels for agent scheduling."""
    CRITICAL = 0  # Must run immediately
    HIGH = 1      # Run as soon as possible
    NORMAL = 2    # Standard priority
    LOW = 3        # Run when nothing else pending


@dataclass
class AgentTask:
    """A task to be executed by an agent."""
    id: str
    agent_type: AgentType
    feature_id: Optional[str]
    description: str
    priority: AgentPriority = AgentPriority.NORMAL
    dependencies: List[str] = field(default_factory=list)
    max_retries: int = 3
    retry_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class AgentResult:
    """Result from an agent execution."""
    task_id: str
    agent_type: AgentType
    success: bool
    output: str
    artifacts_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    tests_passed: int = 0
    tests_failed: int = 0
    next_steps: List[str] = field(default_factory=list)
    error: Optional[str] = None
    requires_retry: bool = False


class AgentScheduler:
    """
    Scheduler for multi-agent orchestration.

    Manages task queues, agent execution, and coordination
    between specialized agents.
    """

    def __init__(
        self,
        project_path: Path,
        config: Optional[Config] = None,
    ):
        self.project_path = Path(project_path).resolve()
        self.config = config or Config()

        # Managers
        self.session_manager = SessionManager(project_path, config)
        self.progress_manager = ProgressManager(
            self.project_path / ".autodev" / "progress.md",
            config
        )
        self.git_ops = GitOperations(project_path, config)

        # Task queue
        self._task_queue: List[AgentTask] = []
        self._completed_tasks: List[AgentTask] = []
        self._running_task: Optional[AgentTask] = None

        # Agent registry
        self._agents: Dict[AgentType, Type] = {}
        self._agent_instances: Dict[AgentType, Any] = {}

        # Callbacks
        self._on_task_complete: Optional[Callable] = None
        self._on_task_failed: Optional[Callable] = None

    def register_agent(self, agent_type: AgentType, agent_class: Type) -> None:
        """Register an agent class for a specific type."""
        self._agents[agent_type] = agent_class
        logger.info(f"Registered agent: {agent_type.value}")

    def get_agent(self, agent_type: AgentType) -> Any:
        """Get or create an agent instance."""
        if agent_type not in self._agent_instances:
            if agent_type in self._agents:
                agent_class = self._agents[agent_type]
                self._agent_instances[agent_type] = agent_class(
                    project_path=self.project_path,
                    config=self.config,
                )
            else:
                raise ValueError(f"No agent registered for type: {agent_type}")

        return self._agent_instances[agent_type]

    def add_task(self, task: AgentTask) -> None:
        """Add a task to the queue."""
        self._task_queue.append(task)
        self._sort_queue()
        logger.info(f"Added task {task.id} ({task.agent_type.value}) to queue")

    def add_tasks(self, tasks: List[AgentTask]) -> None:
        """Add multiple tasks to the queue."""
        for task in tasks:
            self._task_queue.append(task)
        self._sort_queue()
        logger.info(f"Added {len(tasks)} tasks to queue")

    def _sort_queue(self) -> None:
        """Sort the task queue by priority."""
        self._task_queue.sort(key=lambda t: t.priority.value)

    def get_next_task(self) -> Optional[AgentTask]:
        """Get the next task to execute."""
        # Filter out tasks with unmet dependencies
        completed_ids = {t.id for t in self._completed_tasks}

        for task in self._task_queue:
            if task.status != "pending":
                continue

            # Check dependencies
            deps_met = all(
                dep_id in completed_ids
                for dep_id in task.dependencies
            )

            if deps_met:
                return task

        return None

    def get_queue_status(self) -> Dict[str, Any]:
        """Get the current queue status."""
        pending = [t for t in self._task_queue if t.status == "pending"]
        running = self._running_task
        completed_count = len(self._completed_tasks)

        return {
            "pending": len(pending),
            "running": running.id if running else None,
            "completed": completed_count,
            "total": len(self._task_queue) + completed_count,
            "queue": [
                {
                    "id": t.id,
                    "type": t.agent_type.value,
                    "priority": t.priority.name,
                    "status": t.status,
                }
                for t in pending[:10]
            ],
        }

    async def execute_task(self, task: AgentTask) -> AgentResult:
        """
        Execute a single task with the appropriate agent.

        Args:
            task: Task to execute.

        Returns:
            AgentResult with execution outcome.
        """
        logger.info(f"Executing task {task.id} with {task.agent_type.value} agent")

        task.status = "running"
        task.started_at = datetime.now()
        self._running_task = task

        try:
            # Get the agent
            agent = self.get_agent(task.agent_type)

            # Start session
            session_id = self.session_manager.start_session(task.agent_type.value)

            # Execute agent
            result = await agent.execute(task=task)

            # End session
            self.session_manager.end_session(
                action=task.description,
                result=result.output if result else "Completed",
                feature_id=task.feature_id,
                next_steps=result.next_steps if result else [],
            )

            # Update task
            task.status = "completed"
            task.completed_at = datetime.now()
            task.result = result.model_dump() if hasattr(result, 'model_dump') else result.__dict__ if result else {}

            # Move to completed
            if task in self._task_queue:
                self._task_queue.remove(task)
            self._completed_tasks.append(task)

            # Callback
            if self._on_task_complete:
                self._on_task_complete(task, result)

            logger.info(f"Task {task.id} completed successfully")
            return result

        except Exception as e:
            logger.error(f"Task {task.id} failed: {e}")

            task.status = "failed"
            task.error = str(e)
            task.retry_count += 1

            result = AgentResult(
                task_id=task.id,
                agent_type=task.agent_type,
                success=False,
                output="",
                error=str(e),
                requires_retry=task.retry_count < task.max_retries,
            )

            # Callback
            if self._on_task_failed:
                self._on_task_failed(task, result)

            # Re-queue if retries available
            if result.requires_retry:
                task.status = "pending"
                logger.info(f"Re-queueing task {task.id} (retry {task.retry_count}/{task.max_retries})")
            else:
                if task in self._task_queue:
                    self._task_queue.remove(task)
                self._completed_tasks.append(task)

            return result

        finally:
            self._running_task = None

    async def run_all(self, max_iterations: int = 100) -> Dict[str, Any]:
        """
        Run all tasks in the queue until complete or max iterations.

        Args:
            max_iterations: Maximum number of task executions.

        Returns:
            Summary of execution results.
        """
        logger.info(f"Starting multi-agent execution (max {max_iterations} iterations)")

        results = []
        iteration = 0

        while iteration < max_iterations:
            task = self.get_next_task()

            if not task:
                logger.info("No more pending tasks")
                break

            result = await self.execute_task(task)
            results.append(result)

            iteration += 1

            # Check if we should stop
            if result.requires_retry and task.retry_count >= task.max_retries:
                logger.warning(f"Task {task.id} exceeded max retries")

        summary = {
            "iterations": iteration,
            "tasks_completed": sum(1 for r in results if r.success),
            "tasks_failed": sum(1 for r in results if not r.success),
            "total_tasks": len(self._completed_tasks),
            "remaining_in_queue": len([t for t in self._task_queue if t.status == "pending"]),
        }

        logger.info(f"Execution complete: {summary}")
        return summary

    def on_task_complete(self, callback: Callable) -> None:
        """Set callback for task completion."""
        self._on_task_complete = callback

    def on_task_failed(self, callback: Callable) -> None:
        """Set callback for task failure."""
        self._on_task_failed = callback


class TaskPlanner:
    """
    Plans tasks based on feature list and current state.

    Determines which agents should work on what tasks
    and in what order.
    """

    def __init__(
        self,
        project_path: Path,
        config: Optional[Config] = None,
    ):
        self.project_path = Path(project_path)
        self.config = config or Config()
        self.session_manager = SessionManager(project_path, config)

    def plan_next_tasks(
        self,
        feature_list: FeatureList,
        context: SessionContext,
    ) -> List[AgentTask]:
        """
        Plan the next set of tasks based on current state.

        Args:
            feature_list: Current feature list.
            context: Session context.

        Returns:
            List of tasks to execute.
        """
        tasks = []

        # Check if there are broken features that need debugging
        broken_features = self._detect_broken_features(feature_list)
        for feature in broken_features:
            tasks.append(AgentTask(
                id=f"debug-{feature.id}",
                agent_type=AgentType.DEBUGGER,
                feature_id=feature.id,
                description=f"Debug failing feature: {feature.description}",
                priority=AgentPriority.CRITICAL,
            ))

        # If there are broken features, fix them first
        if broken_features:
            return tasks

        # Get next pending feature
        next_feature = feature_list.get_next_feature()
        if next_feature:
            # Add coding task
            tasks.append(AgentTask(
                id=f"implement-{next_feature.id}",
                agent_type=AgentType.CODER,
                feature_id=next_feature.id,
                description=f"Implement: {next_feature.description}",
                priority=AgentPriority.HIGH,
            ))

            # Add testing task (depends on implementation)
            tasks.append(AgentTask(
                id=f"test-{next_feature.id}",
                agent_type=AgentType.TESTER,
                feature_id=next_feature.id,
                description=f"Test: {next_feature.description}",
                priority=AgentPriority.NORMAL,
                dependencies=[f"implement-{next_feature.id}"],
            ))

            # Add documentation task (optional, low priority)
            tasks.append(AgentTask(
                id=f"document-{next_feature.id}",
                agent_type=AgentType.DOCUMENTER,
                feature_id=next_feature.id,
                description=f"Document: {next_feature.description}",
                priority=AgentPriority.LOW,
                dependencies=[f"test-{next_feature.id}"],
            ))

        return tasks

    def _detect_broken_features(self, feature_list: FeatureList) -> List[Feature]:
        """Detect features that are in a broken state."""
        from core.models import FeatureStatus

        broken = []

        for feature in feature_list.features:
            # Features that failed
            if feature.status == FeatureStatus.FAILED:
                broken.append(feature)
                continue

            # Features marked as passing but tests are failing
            # (This would require running tests to detect)

        return broken

    def plan_recovery_tasks(
        self,
        error_context: Dict[str, Any],
    ) -> List[AgentTask]:
        """
        Plan recovery tasks based on error context.

        Args:
            error_context: Context about the error that occurred.

        Returns:
            List of recovery tasks.
        """
        tasks = []

        error_type = error_context.get("error_type", "unknown")

        if error_type == "test_failure":
            # Create debugger task
            tasks.append(AgentTask(
                id=f"recover-test-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                agent_type=AgentType.DEBUGGER,
                feature_id=error_context.get("feature_id"),
                description="Fix failing tests",
                priority=AgentPriority.CRITICAL,
            ))

        elif error_type == "build_failure":
            tasks.append(AgentTask(
                id=f"recover-build-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                agent_type=AgentType.DEBUGGER,
                feature_id=None,
                description="Fix build errors",
                priority=AgentPriority.CRITICAL,
            ))

        elif error_type == "environment_failure":
            tasks.append(AgentTask(
                id=f"recover-env-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                agent_type=AgentType.INITIALIZER,
                feature_id=None,
                description="Fix environment setup",
                priority=AgentPriority.CRITICAL,
            ))

        return tasks


class WorkflowOrchestrator:
    """
    Orchestrates the complete development workflow.

    This is the main entry point that coordinates:
    - Task planning
    - Agent scheduling
    - Progress tracking
    - Error recovery
    """

    def __init__(
        self,
        project_path: Path,
        config: Optional[Config] = None,
    ):
        self.project_path = Path(project_path).resolve()
        self.config = config or Config()

        self.scheduler = AgentScheduler(project_path, config)
        self.planner = TaskPlanner(project_path, config)
        self.session_manager = SessionManager(project_path, config)

        # Set up callbacks
        self.scheduler.on_task_complete(self._on_task_complete)
        self.scheduler.on_task_failed(self._on_task_failed)

        # State
        self._is_running = False
        self._should_stop = False

    def _on_task_complete(self, task: AgentTask, result: AgentResult) -> None:
        """Handle task completion."""
        logger.info(f"Task {task.id} completed: {result.output[:100]}...")

        # Auto-commit if files were modified
        if result.files_modified and self.config.git.auto_commit:
            try:
                self.scheduler.git_ops.add()
                self.scheduler.git_ops.commit(f"Complete: {task.description}")
            except Exception as e:
                logger.warning(f"Could not auto-commit: {e}")

    def _on_task_failed(self, task: AgentTask, result: AgentResult) -> None:
        """Handle task failure."""
        logger.error(f"Task {task.id} failed: {result.error}")

        # If task can't be retried, plan recovery
        if not result.requires_retry:
            recovery_tasks = self.planner.plan_recovery_tasks({
                "error_type": "test_failure" if "test" in task.id.lower() else "unknown",
                "feature_id": task.feature_id,
                "error": result.error,
            })

            for recovery_task in recovery_tasks:
                self.scheduler.add_task(recovery_task)

    async def run(
        self,
        feature_list: Optional[FeatureList] = None,
        max_iterations: int = 100,
    ) -> Dict[str, Any]:
        """
        Run the development workflow.

        Args:
            feature_list: Feature list to work on (loaded from file if not provided).
            max_iterations: Maximum iterations.

        Returns:
            Workflow summary.
        """
        self._is_running = True
        self._should_stop = False

        try:
            # Load feature list if not provided
            if feature_list is None:
                feature_list = self._load_feature_list()

            # Get initial context
            context = self.session_manager.recover_context()

            # Plan initial tasks
            tasks = self.planner.plan_next_tasks(feature_list, context)
            self.scheduler.add_tasks(tasks)

            # Run until complete or stopped
            iteration = 0
            while iteration < max_iterations and not self._should_stop:
                # Check if queue is empty
                queue_status = self.scheduler.get_queue_status()

                if queue_status["pending"] == 0:
                    # Plan more tasks
                    context = self.session_manager.recover_context()
                    feature_list = self._load_feature_list()

                    # Check if all features complete
                    if feature_list.is_complete():
                        logger.info("All features complete!")
                        break

                    # Plan next tasks
                    tasks = self.planner.plan_next_tasks(feature_list, context)

                    if not tasks:
                        logger.info("No more tasks to plan")
                        break

                    self.scheduler.add_tasks(tasks)

                # Run next task
                task = self.scheduler.get_next_task()
                if task:
                    await self.scheduler.execute_task(task)

                iteration += 1

            return self._create_summary(feature_list, iteration)

        finally:
            self._is_running = False

    def stop(self) -> None:
        """Stop the workflow."""
        self._should_stop = True
        logger.info("Workflow stop requested")

    def _load_feature_list(self) -> FeatureList:
        """Load feature list from file."""
        import json

        feature_list_path = self.project_path / ".autodev" / "feature_list.json"

        if not feature_list_path.exists():
            raise FileNotFoundError(f"Feature list not found: {feature_list_path}")

        with open(feature_list_path, "r") as f:
            data = json.load(f)

        return FeatureList(**data)

    def _create_summary(
        self,
        feature_list: FeatureList,
        iterations: int,
    ) -> Dict[str, Any]:
        """Create a workflow summary."""
        progress = feature_list.get_progress_summary()
        queue_status = self.scheduler.get_queue_status()

        return {
            "iterations": iterations,
            "features": progress,
            "tasks_completed": queue_status["completed"],
            "tasks_remaining": queue_status["pending"],
            "success": progress.get("completion_percentage", 0) >= 100,
        }
