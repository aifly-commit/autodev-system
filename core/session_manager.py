"""
Session manager for AutoDev.

Handles session creation, context recovery, and state management.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import Config
from core.exceptions import SessionError
from core.models import Feature, FeatureList, ProgressEntry, SessionContext
from core.progress_manager import ProgressManager
from core.tools.git_ops import GitOperations

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manager for agent sessions.

    Handles:
    - Session creation and tracking
    - Context recovery between sessions
    - State persistence
    """

    def __init__(
        self,
        project_path: Path,
        config: Optional[Config] = None,
    ):
        self.project_path = Path(project_path).resolve()
        self.config = config or Config()

        # Set up paths
        self.autodev_path = self.project_path / self.config.project.autodev_dir
        self.feature_list_path = self.autodev_path / self.config.project.feature_list_file
        self.progress_path = self.autodev_path / self.config.project.progress_file
        self.session_state_path = self.autodev_path / "session_state.json"

        # Initialize managers
        self.progress_manager = ProgressManager(self.progress_path, config)
        self.git_ops = GitOperations(self.project_path, config)

        # Current session
        self.current_session_id: Optional[str] = None
        self.session_start_time: Optional[datetime] = None

    def is_initialized(self) -> bool:
        """Check if the project is initialized."""
        return self.autodev_path.exists() and self.feature_list_path.exists()

    def start_session(self, agent_type: str = "coder") -> str:
        """
        Start a new session.

        Args:
            agent_type: Type of agent (initializer, coder, tester).

        Returns:
            Session ID.
        """
        self.session_start_time = datetime.now()
        self.current_session_id = self._generate_session_id(agent_type)

        # Save session state
        self._save_session_state({
            "session_id": self.current_session_id,
            "agent_type": agent_type,
            "start_time": self.session_start_time.isoformat(),
            "project_path": str(self.project_path),
        })

        logger.info(f"Started session {self.current_session_id}")
        return self.current_session_id

    def end_session(
        self,
        action: str,
        result: str,
        details: Optional[str] = None,
        feature_id: Optional[str] = None,
        next_steps: Optional[List[str]] = None,
    ) -> None:
        """
        End the current session and log progress.

        Args:
            action: What was done.
            result: Result of the session.
            details: Additional details.
            feature_id: Feature that was worked on.
            next_steps: Suggested next steps.
        """
        if not self.current_session_id:
            logger.warning("No active session to end")
            return

        entry = ProgressEntry(
            timestamp=self.session_start_time or datetime.now(),
            session_id=self.current_session_id,
            agent_type=self._get_agent_type_from_session(),
            feature_id=feature_id,
            action=action,
            result=result,
            details=details,
            next_steps=next_steps or [],
        )

        self.progress_manager.append(entry)

        # Clear session state
        self._clear_session_state()

        logger.info(f"Ended session {self.current_session_id}")
        self.current_session_id = None
        self.session_start_time = None

    def recover_context(self) -> SessionContext:
        """
        Recover context for a new session.

        This is called at the start of each session to understand
        the current state of the project.
        """
        logger.info("Recovering session context")

        # Load feature list
        feature_list = self._load_feature_list()
        next_feature = feature_list.get_next_feature()
        progress_summary = feature_list.get_progress_summary()

        # Get recent commits
        recent_commits = []
        if self.git_ops.is_repo():
            recent_commits = self.git_ops.log(10)

        # Get last progress entry
        last_entry = self.progress_manager.get_last_entry()

        # Get current branch
        current_branch = "main"
        if self.git_ops.is_repo():
            current_branch = self.git_ops.current_branch()

        # Check environment health
        environment_healthy = self._check_environment_health()

        # Get known issues
        known_issues = self._detect_known_issues()

        context = SessionContext(
            working_directory=str(self.project_path),
            project_name=self.project_path.name,
            current_branch=current_branch,
            recent_commits=[
                {"hash": c["hash"], "message": c["message"]}
                for c in recent_commits
            ],
            current_feature=next_feature,
            pending_features_count=len(feature_list.get_pending_features()),
            progress_summary=progress_summary,
            last_progress_entry=last_entry,
            known_issues=known_issues,
            environment_healthy=environment_healthy,
        )

        logger.info(f"Context recovered: {progress_summary.get('passing', 0)}/{progress_summary.get('total', 0)} features passing")
        return context

    def _load_feature_list(self) -> FeatureList:
        """Load the feature list."""
        if not self.feature_list_path.exists():
            raise SessionError(f"Feature list not found: {self.feature_list_path}")

        with open(self.feature_list_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return FeatureList(**data)

    def _save_feature_list(self, feature_list: FeatureList) -> None:
        """Save the feature list."""
        self.autodev_path.mkdir(parents=True, exist_ok=True)
        with open(self.feature_list_path, "w", encoding="utf-8") as f:
            json.dump(feature_list.model_dump(mode="json"), f, indent=2, default=str)

    def _generate_session_id(self, agent_type: str) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        # Get session count
        state = self._load_session_state()
        count = state.get("session_count", 0) + 1
        return f"{timestamp}-{agent_type[:3]}-{count:03d}"

    def _get_agent_type_from_session(self) -> str:
        """Get agent type from current session."""
        if self.current_session_id:
            parts = self.current_session_id.split("-")
            if len(parts) >= 2:
                code = parts[1]
                if code == "ini":
                    return "initializer"
                elif code == "cod":
                    return "coder"
                elif code == "tes":
                    return "tester"
        return "unknown"

    def _save_session_state(self, state: Dict[str, Any]) -> None:
        """Save session state to file."""
        # Load existing state
        existing = self._load_session_state()

        # Update session count
        if "session_id" in state:
            existing["session_count"] = existing.get("session_count", 0) + 1

        # Merge state
        existing.update(state)

        self.autodev_path.mkdir(parents=True, exist_ok=True)
        with open(self.session_state_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

    def _load_session_state(self) -> Dict[str, Any]:
        """Load session state from file."""
        if not self.session_state_path.exists():
            return {}
        try:
            with open(self.session_state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _clear_session_state(self) -> None:
        """Clear current session from state."""
        state = self._load_session_state()
        state.pop("session_id", None)
        state.pop("agent_type", None)
        state.pop("start_time", None)

        with open(self.session_state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _check_environment_health(self) -> bool:
        """Check if the development environment is healthy."""
        # Basic checks
        if not self.project_path.exists():
            return False

        # Check for init script
        init_script = self.project_path / "init.sh"
        if init_script.exists():
            try:
                with open(init_script, "r") as f:
                    content = f.read()
                    if not content.strip():
                        logger.warning("init.sh is empty")
            except Exception as e:
                logger.warning(f"Could not read init.sh: {e}")

        return True

    def _detect_known_issues(self) -> List[str]:
        """Detect known issues in the project."""
        issues: List[str] = []

        # Check for missing dependency files
        has_deps = any([
            (self.project_path / "package.json").exists(),
            (self.project_path / "requirements.txt").exists(),
            (self.project_path / "pyproject.toml").exists(),
            (self.project_path / "Cargo.toml").exists(),
            (self.project_path / "go.mod").exists(),
        ])

        if not has_deps:
            issues.append("No dependency file found - project may not be set up")

        # Check for uncommitted changes
        if self.git_ops.is_repo() and self.git_ops.has_changes():
            issues.append("There are uncommitted changes")

        # Check for stashed changes
        if self.git_ops.is_repo():
            stashes = self.git_ops.stash_list()
            if stashes:
                issues.append(f"There are {len(stashes)} stashed changes")

        return issues

    def get_session_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent session history."""
        entries = self.progress_manager.parse_entries()
        recent = entries[-limit:] if entries else []

        return [
            {
                "session_id": e.session_id,
                "timestamp": e.timestamp.isoformat(),
                "agent_type": e.agent_type,
                "feature_id": e.feature_id,
                "action": e.action,
                "result": e.result[:100] + "..." if len(e.result) > 100 else e.result,
            }
            for e in recent
        ]

    def get_feature_history(self, feature_id: str) -> List[ProgressEntry]:
        """Get all progress entries for a specific feature."""
        return self.progress_manager.get_entries_for_feature(feature_id)

    def mark_feature_started(self, feature_id: str) -> None:
        """Mark a feature as started in this session."""
        feature_list = self._load_feature_list()

        for feature in feature_list.features:
            if feature.id == feature_id:
                feature.start_work()
                break
        else:
            raise SessionError(f"Feature not found: {feature_id}")

        feature_list.updated_at = datetime.now()
        self._save_feature_list(feature_list)

    def mark_feature_complete(self, feature_id: str) -> None:
        """Mark a feature as complete in this session."""
        feature_list = self._load_feature_list()

        for feature in feature_list.features:
            if feature.id == feature_id:
                feature.mark_passing()
                break
        else:
            raise SessionError(f"Feature not found: {feature_id}")

        feature_list.updated_at = datetime.now()
        self._save_feature_list(feature_list)

    def mark_feature_failed(self, feature_id: str, reason: str) -> None:
        """Mark a feature as failed in this session."""
        feature_list = self._load_feature_list()

        for feature in feature_list.features:
            if feature.id == feature_id:
                feature.mark_failed(reason)
                break
        else:
            raise SessionError(f"Feature not found: {feature_id}")

        feature_list.updated_at = datetime.now()
        self._save_feature_list(feature_list)
