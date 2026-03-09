"""
Main harness for AutoDev system.

This is the central controller that orchestrates:
- Project initialization
- Agent scheduling
- Session management
- Progress tracking
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.config import Config, get_config
from core.exceptions import (
    AutoDevError,
    ConfigurationError,
    EnvironmentNotHealthy,
    FeatureListError,
    MaxIterationsExceeded,
    ProjectNotFoundError,
)
from core.models import (
    Feature,
    FeatureList,
    FeatureStatus,
    ProgressEntry,
    SessionContext,
)

logger = logging.getLogger(__name__)


class AutoDevHarness:
    """
    Main controller for the AutoDev system.

    Based on Anthropic's long-running agent harness design:
    - Initializer agent sets up the environment
    - Coding agent makes incremental progress
    - Progress is tracked across sessions via artifacts
    """

    def __init__(
        self,
        project_path: str | Path,
        spec: Optional[str] = None,
        config: Optional[Config] = None,
    ):
        """
        Initialize the harness.

        Args:
            project_path: Path to the project directory
            spec: Optional project specification (required for first run)
            config: Optional configuration override
        """
        self.project_path = Path(project_path).resolve()
        self.spec = spec
        self.config = config or get_config()
        self.session_count = 0

        # Set up paths
        self.autodev_path = self.config.get_autodev_path(self.project_path)
        self.feature_list_path = self.config.get_feature_list_path(self.project_path)
        self.progress_path = self.config.get_progress_path(self.project_path)
        self.init_script_path = self.config.get_init_script_path(self.project_path)

        # Set up logging
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configure logging for the harness."""
        log_level = getattr(logging, self.config.logging.level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format=self.config.logging.format,
        )

    def is_initialized(self) -> bool:
        """Check if the project has been initialized by AutoDev."""
        return self.autodev_path.exists() and self.feature_list_path.exists()

    def initialize(self) -> None:
        """
        Initialize the project for AutoDev.

        This should only be called once per project.
        Creates the .autodev directory and initial artifacts.
        """
        logger.info(f"Initializing AutoDev for project at {self.project_path}")

        # Validate project path
        if not self.project_path.exists():
            raise ProjectNotFoundError(f"Project path does not exist: {self.project_path}")

        # Create .autodev directory
        self.autodev_path.mkdir(parents=True, exist_ok=True)

        # Create initial feature list if spec provided
        if self.spec:
            feature_list = self._generate_initial_feature_list()
            self._save_feature_list(feature_list)
            logger.info(f"Created feature list with {len(feature_list.features)} features")
        else:
            # Create empty feature list structure
            feature_list = FeatureList(
                project=self.project_path.name,
                spec="",
            )
            self._save_feature_list(feature_list)

        # Create initial progress file
        self._create_initial_progress_file()

        # Initialize git if not already
        self._ensure_git_initialized()

        logger.info("AutoDev initialization complete")

    def _generate_initial_feature_list(self) -> FeatureList:
        """
        Generate an initial feature list from the spec.

        Note: This creates a placeholder structure. The actual
        feature generation should be done by the Initializer Agent.
        """
        return FeatureList(
            project=self.project_path.name,
            spec=self.spec,
            features=[
                Feature(
                    id="F001",
                    category="core",
                    description="Project setup and structure (placeholder - to be expanded by Initializer Agent)",
                    acceptance_criteria=["Project structure is created"],
                    test_steps=["Verify project directory exists"],
                )
            ]
        )

    def _create_initial_progress_file(self) -> None:
        """Create the initial progress file."""
        initial_entry = ProgressEntry(
            session_id=self._generate_session_id(),
            agent_type="system",
            action="Project initialized",
            result="AutoDev environment set up successfully",
            next_steps=["Run Initializer Agent to generate feature list"],
        )
        self._append_progress(initial_entry)

    def _ensure_git_initialized(self) -> None:
        """Ensure git is initialized in the project."""
        git_dir = self.project_path / ".git"
        if not git_dir.exists():
            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=self.project_path,
                    check=True,
                    capture_output=True,
                )
                logger.info("Initialized git repository")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Could not initialize git: {e}")

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{timestamp}-{self.session_count:03d}"

    def _save_feature_list(self, feature_list: FeatureList) -> None:
        """Save feature list to JSON file."""
        self.autodev_path.mkdir(parents=True, exist_ok=True)
        with open(self.feature_list_path, "w", encoding="utf-8") as f:
            json.dump(feature_list.model_dump(mode="json"), f, indent=2, default=str)

    def load_feature_list(self) -> FeatureList:
        """Load feature list from JSON file."""
        if not self.feature_list_path.exists():
            raise FeatureListError(f"Feature list not found: {self.feature_list_path}")

        with open(self.feature_list_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return FeatureList(**data)

    def _append_progress(self, entry: ProgressEntry) -> None:
        """Append a progress entry to the progress file."""
        self.autodev_path.mkdir(parents=True, exist_ok=True)

        # Read existing content
        existing = ""
        if self.progress_path.exists():
            with open(self.progress_path, "r", encoding="utf-8") as f:
                existing = f.read()

        # Format new entry
        new_entry = self._format_progress_entry(entry)

        # Write combined content
        with open(self.progress_path, "w", encoding="utf-8") as f:
            if existing:
                f.write(existing.rstrip("\n"))
                f.write("\n\n")
            f.write(new_entry)

    def _format_progress_entry(self, entry: ProgressEntry) -> str:
        """Format a progress entry as markdown."""
        lines = [
            f"## Session: {entry.session_id}",
            f"**Timestamp**: {entry.timestamp.isoformat()}",
            f"**Agent**: {entry.agent_type}",
            "",
        ]

        if entry.feature_id:
            lines.append(f"**Feature**: {entry.feature_id}")
            lines.append("")

        lines.extend([
            f"### Action: {entry.action}",
            f"**Result**: {entry.result}",
            "",
        ])

        if entry.details:
            lines.extend([
                "### Details",
                entry.details,
                "",
            ])

        if entry.next_steps:
            lines.append("### Next Steps")
            for step in entry.next_steps:
                lines.append(f"- {step}")
            lines.append("")

        lines.append("---")
        return "\n".join(lines)

    def recover_context(self) -> SessionContext:
        """
        Recover context for a new session.

        This is called at the start of each coding agent session
        to understand the current state of the project.
        """
        logger.info("Recovering session context")

        # Load feature list
        feature_list = self.load_feature_list()
        next_feature = feature_list.get_next_feature()
        progress_summary = feature_list.get_progress_summary()

        # Get recent commits
        recent_commits = self._get_recent_commits()

        # Get last progress entry
        last_entry = self._get_last_progress_entry()

        # Get current branch
        current_branch = self._get_current_branch()

        # Check environment health
        environment_healthy = self._check_environment_health()

        context = SessionContext(
            working_directory=str(self.project_path),
            project_name=self.project_path.name,
            current_branch=current_branch,
            recent_commits=recent_commits,
            current_feature=next_feature,
            pending_features_count=len(feature_list.get_pending_features()),
            progress_summary=progress_summary,
            last_progress_entry=last_entry,
            known_issues=self._get_known_issues(),
            environment_healthy=environment_healthy,
        )

        logger.info(f"Context recovered: {progress_summary['passing']}/{progress_summary['total']} features passing")
        return context

    def _get_recent_commits(self, limit: int = 10) -> list[dict[str, str]]:
        """Get recent git commits."""
        try:
            result = subprocess.run(
                ["git", "log", f"-{limit}", "--pretty=format:%H|%s|%ai"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return []

            commits = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("|", 2)
                    if len(parts) >= 2:
                        commits.append({
                            "hash": parts[0][:8],
                            "message": parts[1],
                            "date": parts[2] if len(parts) > 2 else "",
                        })
            return commits
        except Exception as e:
            logger.warning(f"Could not get git commits: {e}")
            return []

    def _get_current_branch(self) -> str:
        """Get the current git branch."""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip() or "main"
        except Exception:
            pass
        return "main"

    def _get_last_progress_entry(self) -> Optional[ProgressEntry]:
        """Parse the last progress entry from the progress file."""
        if not self.progress_path.exists():
            return None

        # For now, return None - full parsing would require more complex logic
        # This is a placeholder that can be enhanced later
        return None

    def _get_known_issues(self) -> list[str]:
        """Get list of known issues from the project."""
        issues = []

        # Check for common issues
        if not (self.project_path / "package.json").exists() and \
           not (self.project_path / "requirements.txt").exists() and \
           not (self.project_path / "pyproject.toml").exists():
            issues.append("No dependency file found - project may not be set up")

        return issues

    def _check_environment_health(self) -> bool:
        """Check if the development environment is healthy."""
        # Basic checks
        if not self.project_path.exists():
            return False

        # If init.sh exists, try to verify it's valid
        if self.init_script_path.exists():
            # Don't run it, just check it's readable
            try:
                with open(self.init_script_path, "r") as f:
                    content = f.read()
                    if not content.strip():
                        return False
            except Exception:
                return False

        return True

    def mark_feature_passing(self, feature_id: str) -> None:
        """Mark a feature as passing."""
        feature_list = self.load_feature_list()

        for feature in feature_list.features:
            if feature.id == feature_id:
                feature.mark_passing()
                break
        else:
            raise FeatureListError(f"Feature not found: {feature_id}")

        feature_list.updated_at = datetime.now()
        self._save_feature_list(feature_list)
        logger.info(f"Marked feature {feature_id} as passing")

    def mark_feature_failed(self, feature_id: str, reason: Optional[str] = None) -> None:
        """Mark a feature as failed."""
        feature_list = self.load_feature_list()

        for feature in feature_list.features:
            if feature.id == feature_id:
                feature.mark_failed(reason)
                break
        else:
            raise FeatureListError(f"Feature not found: {feature_id}")

        feature_list.updated_at = datetime.now()
        self._save_feature_list(feature_list)
        logger.warning(f"Marked feature {feature_id} as failed: {reason}")

    def run(self, max_iterations: Optional[int] = None) -> None:
        """
        Run the AutoDev harness.

        This is the main entry point for autonomous development.
        """
        max_iter = max_iterations or self.config.execution.max_iterations

        # Check if initialized
        if not self.is_initialized():
            if not self.spec:
                raise ConfigurationError(
                    "Project not initialized and no spec provided. "
                    "Call initialize() with a spec first."
                )
            self.initialize()

        # Main loop
        while True:
            if self.session_count >= max_iter:
                raise MaxIterationsExceeded(
                    f"Reached maximum iterations ({max_iter})"
                )

            # Recover context
            context = self.recover_context()

            # Check if complete
            if context.progress_summary.get("completion_percentage", 0) >= 100:
                logger.info("All features complete!")
                break

            # Check environment health
            if not context.environment_healthy:
                logger.warning("Environment not healthy, attempting recovery")
                # In a full implementation, this would trigger recovery

            # Run coding agent session
            # Note: In a full implementation, this would call the actual LLM
            logger.info(f"Starting coding session {self.session_count + 1}")
            self._run_coding_session(context)

            self.session_count += 1

    def _run_coding_session(self, context: SessionContext) -> dict:
        """
        Run a single coding agent session.

        This calls the actual LLM with tools.
        """
        from core.agents.coder import CoderAgent

        logger.info(f"Context summary:\n{context.to_prompt_context()}")

        # Create and run coder agent
        agent = CoderAgent(
            project_path=self.project_path,
            config=self.config,
            session_context=context,
        )

        result = agent.execute()

        # Record session in progress file
        feature_id = context.current_feature.id if context.current_feature else None
        entry = ProgressEntry(
            session_id=self._generate_session_id(),
            agent_type="coder",
            feature_id=feature_id,
            action="Coding session completed",
            result="Success" if result.get("success") else f"Failed: {result.get('error', 'Unknown')}",
            next_steps=[],
        )
        self._append_progress(entry)

        return result

    def run_initializer(self) -> dict:
        """
        Run the initializer agent.

        This sets up the project and generates the feature list.
        """
        from core.agents.initializer import InitializerAgent

        if not self.spec:
            raise ConfigurationError("Specification required for initialization")

        logger.info(f"Running initializer agent for {self.project_path}")

        agent = InitializerAgent(
            spec=self.spec,
            project_path=self.project_path,
            config=self.config,
        )

        result = agent.execute()

        if result.get("success"):
            logger.info("Initializer agent completed successfully")
        else:
            logger.error(f"Initializer agent failed: {result.get('error')}")

        return result


def create_harness(
    project_path: str | Path,
    spec: Optional[str] = None,
    config_path: Optional[str | Path] = None,
) -> AutoDevHarness:
    """
    Factory function to create an AutoDev harness.

    Args:
        project_path: Path to the project directory
        spec: Optional project specification
        config_path: Optional path to config file

    Returns:
        Configured AutoDevHarness instance
    """
    config = get_config(config_path) if config_path else get_config()
    return AutoDevHarness(project_path, spec, config)
