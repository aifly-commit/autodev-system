"""
Tests for data models.
"""

import pytest
from datetime import datetime

from core.models import (
    Feature,
    FeatureList,
    FeatureStatus,
    Priority,
    ProgressEntry,
    SessionContext,
)


class TestFeature:
    """Tests for Feature model."""

    def test_feature_creation(self):
        """Test creating a feature."""
        feature = Feature(
            id="F001",
            category="core",
            description="Test feature",
            acceptance_criteria=["AC1", "AC2"],
            test_steps=["Step 1", "Step 2"],
        )

        assert feature.id == "F001"
        assert feature.category == "core"
        assert feature.description == "Test feature"
        assert feature.passes is False
        assert feature.status == FeatureStatus.PENDING

    def test_feature_mark_passing(self):
        """Test marking a feature as passing."""
        feature = Feature(id="F001", description="Test")

        assert feature.passes is False
        assert feature.tested_at is None

        feature.mark_passing()

        assert feature.passes is True
        assert feature.status == FeatureStatus.PASSING
        assert feature.tested_at is not None

    def test_feature_mark_failed(self):
        """Test marking a feature as failed."""
        feature = Feature(id="F001", description="Test")

        feature.mark_failed("Something went wrong")

        assert feature.passes is False
        assert feature.status == FeatureStatus.FAILED
        assert feature.notes == "Something went wrong"

    def test_feature_start_work(self):
        """Test starting work on a feature."""
        feature = Feature(id="F001", description="Test")

        feature.start_work()

        assert feature.status == FeatureStatus.IN_PROGRESS


class TestFeatureList:
    """Tests for FeatureList model."""

    def test_feature_list_creation(self):
        """Test creating a feature list."""
        fl = FeatureList(
            project="test-project",
            spec="Build a test app",
        )

        assert fl.project == "test-project"
        assert fl.spec == "Build a test app"
        assert len(fl.features) == 0

    def test_add_feature(self):
        """Test adding features to the list."""
        fl = FeatureList(project="test")
        feature = Feature(id="F001", description="Test")

        fl.add_feature(feature)

        assert len(fl.features) == 1
        assert fl.features[0].id == "F001"

    def test_get_pending_features(self):
        """Test getting pending features."""
        fl = FeatureList(project="test")
        fl.add_feature(Feature(id="F001", description="Passing", passes=True))
        fl.add_feature(Feature(id="F002", description="Pending"))
        fl.add_feature(Feature(id="F003", description="Also pending"))

        pending = fl.get_pending_features()

        assert len(pending) == 2
        assert all(not f.passes for f in pending)

    def test_get_next_feature(self):
        """Test getting the next feature to work on."""
        fl = FeatureList(project="test")
        fl.add_feature(Feature(id="F001", description="Low", priority=Priority.LOW))
        fl.add_feature(Feature(id="F002", description="High", priority=Priority.HIGH))
        fl.add_feature(Feature(id="F003", description="Critical", priority=Priority.CRITICAL))

        next_feature = fl.get_next_feature()

        assert next_feature.id == "F003"  # Critical should be first

    def test_get_next_feature_no_pending(self):
        """Test getting next feature when none pending."""
        fl = FeatureList(project="test")
        fl.add_feature(Feature(id="F001", description="Done", passes=True))

        next_feature = fl.get_next_feature()

        assert next_feature is None

    def test_get_progress_summary(self):
        """Test getting progress summary."""
        fl = FeatureList(project="test")
        fl.add_feature(Feature(id="F001", description="Done", passes=True))
        fl.add_feature(Feature(id="F002", description="Done", passes=True))
        fl.add_feature(Feature(id="F003", description="Pending"))

        summary = fl.get_progress_summary()

        assert summary["total"] == 3
        assert summary["passing"] == 2
        assert summary["pending"] == 1
        assert summary["completion_percentage"] == pytest.approx(66.67, rel=0.01)

    def test_is_complete(self):
        """Test checking if all features are complete."""
        fl = FeatureList(project="test")

        # Empty list is NOT complete (no features to complete)
        assert fl.is_complete() is False

        fl.add_feature(Feature(id="F001", description="Pending"))
        assert fl.is_complete() is False

        fl.features[0].mark_passing()
        assert fl.is_complete() is True


class TestProgressEntry:
    """Tests for ProgressEntry model."""

    def test_progress_entry_creation(self):
        """Test creating a progress entry."""
        entry = ProgressEntry(
            session_id="20240101-001",
            agent_type="coder",
            feature_id="F001",
            action="Implemented login",
            result="Success",
            next_steps=["Add logout"],
        )

        assert entry.session_id == "20240101-001"
        assert entry.agent_type == "coder"
        assert entry.feature_id == "F001"
        assert entry.next_steps == ["Add logout"]


class TestSessionContext:
    """Tests for SessionContext model."""

    def test_session_context_creation(self):
        """Test creating a session context."""
        context = SessionContext(
            working_directory="/project",
            project_name="my-project",
            current_branch="main",
            pending_features_count=5,
            progress_summary={"total": 10, "passing": 5},
        )

        assert context.working_directory == "/project"
        assert context.project_name == "my-project"
        assert context.pending_features_count == 5
        assert context.environment_healthy is True

    def test_to_prompt_context(self):
        """Test generating prompt context."""
        context = SessionContext(
            working_directory="/project",
            project_name="my-project",
            current_branch="main",
            recent_commits=[
                {"hash": "abc12345", "message": "Initial commit"}
            ],
            pending_features_count=3,
            progress_summary={"total": 5, "passing": 2, "completion_percentage": 40.0},
        )

        prompt = context.to_prompt_context()

        assert "my-project" in prompt
        assert "main" in prompt
        assert "abc12345" in prompt
        assert "40.0%" in prompt
