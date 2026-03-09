"""
Data models for AutoDev system.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FeatureStatus(str, Enum):
    """Status of a feature."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSING = "passing"
    FAILED = "failed"
    SKIPPED = "skipped"


class Priority(str, Enum):
    """Feature priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Feature(BaseModel):
    """
    A single feature to be implemented.

    Based on Anthropic's feature list design:
    - Clear description of expected behavior
    - Test steps for E2E verification
    - passes field to track completion
    """

    id: str = Field(..., description="Unique feature identifier, e.g., F001")
    category: str = Field(default="core", description="Feature category")
    priority: Priority = Field(default=Priority.MEDIUM, description="Feature priority")
    description: str = Field(..., description="What the feature does")
    acceptance_criteria: List[str] = Field(
        default_factory=list,
        description="Criteria that must be met for feature to be complete"
    )
    test_steps: List[str] = Field(
        default_factory=list,
        description="Steps to verify the feature works end-to-end"
    )
    status: FeatureStatus = Field(default=FeatureStatus.PENDING, description="Current status")
    passes: bool = Field(default=False, description="Whether the feature passes E2E tests")
    implemented_at: Optional[datetime] = Field(default=None, description="When feature was implemented")
    tested_at: Optional[datetime] = Field(default=None, description="When feature was tested")
    notes: Optional[str] = Field(default=None, description="Additional notes")

    def mark_passing(self) -> None:
        """Mark this feature as passing."""
        self.passes = True
        self.status = FeatureStatus.PASSING
        self.tested_at = datetime.now()

    def mark_failed(self, reason: Optional[str] = None) -> None:
        """Mark this feature as failed."""
        self.passes = False
        self.status = FeatureStatus.FAILED
        self.tested_at = datetime.now()
        if reason:
            self.notes = reason

    def start_work(self) -> None:
        """Mark this feature as in progress."""
        self.status = FeatureStatus.IN_PROGRESS


class FeatureList(BaseModel):
    """
    Complete feature list for a project.

    This is the core artifact that enables long-running agents to:
    1. Understand what needs to be built
    2. Track progress across sessions
    3. Know when the project is complete
    """

    project: str = Field(..., description="Project name")
    version: str = Field(default="1.0.0", description="Feature list version")
    created_at: datetime = Field(default_factory=datetime.now, description="When list was created")
    updated_at: datetime = Field(default_factory=datetime.now, description="When list was last updated")
    spec: Optional[str] = Field(default=None, description="Original specification")
    features: List[Feature] = Field(default_factory=list, description="All features")

    def add_feature(self, feature: Feature) -> None:
        """Add a new feature to the list."""
        self.features.append(feature)
        self.updated_at = datetime.now()

    def get_pending_features(self) -> List[Feature]:
        """Get all features that are not yet passing."""
        return [f for f in self.features if not f.passes]

    def get_next_feature(self) -> Optional[Feature]:
        """Get the highest priority pending feature."""
        pending = self.get_pending_features()
        if not pending:
            return None

        # Sort by priority (critical > high > medium > low)
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3,
        }
        pending.sort(key=lambda f: priority_order.get(f.priority, 4))
        return pending[0]

    def get_progress_summary(self) -> Dict[str, Any]:
        """Get a summary of progress."""
        total = len(self.features)
        passing = sum(1 for f in self.features if f.passes)
        in_progress = sum(1 for f in self.features if f.status == FeatureStatus.IN_PROGRESS)
        failed = sum(1 for f in self.features if f.status == FeatureStatus.FAILED)

        return {
            "total": total,
            "passing": passing,
            "in_progress": in_progress,
            "failed": failed,
            "pending": total - passing - in_progress - failed,
            "completion_percentage": (passing / total * 100) if total > 0 else 0,
        }

    def is_complete(self) -> bool:
        """Check if all features are passing."""
        return all(f.passes for f in self.features) if self.features else False


class ProgressEntry(BaseModel):
    """
    A single entry in the progress log.

    This enables context recovery across sessions.
    """

    timestamp: datetime = Field(default_factory=datetime.now)
    session_id: str = Field(..., description="Unique session identifier")
    agent_type: str = Field(..., description="Type of agent (initializer/coder/tester)")
    feature_id: Optional[str] = Field(default=None, description="Feature being worked on")
    action: str = Field(..., description="What was done")
    result: str = Field(..., description="Result of the action")
    details: Optional[str] = Field(default=None, description="Additional details")
    next_steps: List[str] = Field(default_factory=list, description="Suggested next steps")


class SessionContext(BaseModel):
    """
    Context recovered at the start of a new session.

    This is the key to enabling long-running agents:
    - Each session starts fresh with no memory
    - This context bridges the gap between sessions
    """

    working_directory: str = Field(..., description="Current working directory")
    project_name: str = Field(..., description="Project name")
    current_branch: str = Field(default="main", description="Current git branch")
    recent_commits: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Recent git commits"
    )
    current_feature: Optional[Feature] = Field(default=None, description="Feature being worked on")
    pending_features_count: int = Field(default=0, description="Number of pending features")
    progress_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary of project progress"
    )
    last_progress_entry: Optional[ProgressEntry] = Field(
        default=None,
        description="Most recent progress entry"
    )
    known_issues: List[str] = Field(
        default_factory=list,
        description="Known issues or blockers"
    )
    environment_healthy: bool = Field(
        default=True,
        description="Whether the dev environment is healthy"
    )

    def to_prompt_context(self) -> str:
        """Generate a human-readable context summary for the agent."""
        lines = [
            "# Session Context Recovery",
            "",
            f"**Working Directory**: {self.working_directory}",
            f"**Project**: {self.project_name}",
            f"**Branch**: {self.current_branch}",
            "",
            "## Progress Summary",
            f"- Total features: {self.progress_summary.get('total', 0)}",
            f"- Passing: {self.progress_summary.get('passing', 0)}",
            f"- Pending: {self.pending_features_count}",
            f"- Completion: {self.progress_summary.get('completion_percentage', 0):.1f}%",
            "",
        ]

        if self.recent_commits:
            lines.append("## Recent Commits")
            for commit in self.recent_commits[:5]:
                lines.append(f"- {commit.get('hash', '???')}: {commit.get('message', '')}")
            lines.append("")

        if self.current_feature:
            lines.extend([
                "## Current Feature",
                f"**ID**: {self.current_feature.id}",
                f"**Description**: {self.current_feature.description}",
                "",
            ])

        if self.known_issues:
            lines.extend([
                "## Known Issues",
                *[f"- {issue}" for issue in self.known_issues],
                "",
            ])

        if self.last_progress_entry:
            lines.extend([
                "## Last Session",
                f"**Action**: {self.last_progress_entry.action}",
                f"**Result**: {self.last_progress_entry.result}",
            ])
            if self.last_progress_entry.next_steps:
                lines.append("**Next Steps**:")
                for step in self.last_progress_entry.next_steps:
                    lines.append(f"- {step}")

        return "\n".join(lines)


class TestResult(BaseModel):
    """Result of a test execution."""
    feature_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    passed: bool
    steps_executed: List[str] = Field(default_factory=list)
    failures: List[str] = Field(default_factory=list)
    screenshots: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
