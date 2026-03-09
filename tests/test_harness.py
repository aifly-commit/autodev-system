"""
Tests for the main harness.
"""

import json
import pytest
from pathlib import Path

from core.config import Config
from core.harness import AutoDevHarness, create_harness
from core.exceptions import ProjectNotFoundError, ConfigurationError
from core.models import Feature, FeatureList


class TestAutoDevHarness:
    """Tests for AutoDevHarness class."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a temporary project directory."""
        project = tmp_path / "test-project"
        project.mkdir()
        return project

    @pytest.fixture
    def config(self) -> Config:
        """Create a test configuration."""
        return Config()

    def test_harness_creation(self, project_path: Path, config: Config):
        """Test creating a harness."""
        harness = AutoDevHarness(project_path, config=config)

        assert harness.project_path == project_path.resolve()
        assert harness.config == config
        assert harness.session_count == 0

    def test_is_initialized_false(self, project_path: Path, config: Config):
        """Test is_initialized returns False for new projects."""
        harness = AutoDevHarness(project_path, config=config)

        assert harness.is_initialized() is False

    def test_initialize_creates_directory(self, project_path: Path, config: Config):
        """Test that initialize creates the .autodev directory."""
        harness = AutoDevHarness(project_path, spec="Test project", config=config)

        harness.initialize()

        assert harness.autodev_path.exists()
        assert harness.autodev_path.name == ".autodev"

    def test_initialize_creates_feature_list(self, project_path: Path, config: Config):
        """Test that initialize creates the feature list."""
        harness = AutoDevHarness(project_path, spec="Build a todo app", config=config)

        harness.initialize()

        assert harness.feature_list_path.exists()

        # Load and verify
        feature_list = harness.load_feature_list()
        assert feature_list.project == project_path.name
        assert feature_list.spec == "Build a todo app"

    def test_initialize_creates_progress_file(self, project_path: Path, config: Config):
        """Test that initialize creates the progress file."""
        harness = AutoDevHarness(project_path, spec="Test", config=config)

        harness.initialize()

        assert harness.progress_path.exists()
        content = harness.progress_path.read_text()
        assert "initialized" in content.lower()

    def test_initialize_nonexistent_project(self, tmp_path: Path, config: Config):
        """Test initializing a nonexistent project raises error."""
        harness = AutoDevHarness(tmp_path / "nonexistent", config=config)

        with pytest.raises(ProjectNotFoundError):
            harness.initialize()

    def test_load_feature_list(self, project_path: Path, config: Config):
        """Test loading the feature list."""
        harness = AutoDevHarness(project_path, spec="Test", config=config)
        harness.initialize()

        feature_list = harness.load_feature_list()

        assert isinstance(feature_list, FeatureList)
        assert feature_list.project == project_path.name

    def test_mark_feature_passing(self, project_path: Path, config: Config):
        """Test marking a feature as passing."""
        harness = AutoDevHarness(project_path, spec="Test", config=config)
        harness.initialize()

        # Add a feature manually for testing
        feature_list = harness.load_feature_list()
        feature_list.add_feature(Feature(id="F001", description="Test feature"))
        harness._save_feature_list(feature_list)

        # Mark as passing
        harness.mark_feature_passing("F001")

        # Verify
        updated = harness.load_feature_list()
        # Find the feature by ID
        f001 = next((f for f in updated.features if f.id == "F001"), None)
        assert f001 is not None
        assert f001.passes is True

    def test_mark_feature_failed(self, project_path: Path, config: Config):
        """Test marking a feature as failed."""
        harness = AutoDevHarness(project_path, spec="Test", config=config)
        harness.initialize()

        # Add a feature
        feature_list = harness.load_feature_list()
        feature_list.add_feature(Feature(id="F001", description="Test feature"))
        harness._save_feature_list(feature_list)

        # Mark as failed
        harness.mark_feature_failed("F001", "Test failed")

        # Verify
        updated = harness.load_feature_list()
        # Find the feature by ID
        f001 = next((f for f in updated.features if f.id == "F001"), None)
        assert f001 is not None
        assert f001.passes is False
        assert f001.notes == "Test failed"

    def test_recover_context(self, project_path: Path, config: Config):
        """Test recovering session context."""
        harness = AutoDevHarness(project_path, spec="Test project", config=config)
        harness.initialize()

        context = harness.recover_context()

        assert context.working_directory == str(project_path.resolve())
        assert context.project_name == project_path.name
        assert context.environment_healthy is True

    def test_recover_context_with_progress(self, project_path: Path, config: Config):
        """Test recovering context with some progress."""
        harness = AutoDevHarness(project_path, spec="Test", config=config)
        harness.initialize()

        # Add some features
        feature_list = harness.load_feature_list()
        feature_list.add_feature(Feature(id="F001", description="Feature 1", passes=True))
        feature_list.add_feature(Feature(id="F002", description="Feature 2"))
        harness._save_feature_list(feature_list)

        context = harness.recover_context()

        assert context.progress_summary["total"] == 3  # 1 placeholder + 2 added
        assert context.progress_summary["passing"] == 1
        assert context.pending_features_count == 2

    def test_is_initialized_true(self, project_path: Path, config: Config):
        """Test is_initialized returns True after initialization."""
        harness = AutoDevHarness(project_path, spec="Test", config=config)

        harness.initialize()

        assert harness.is_initialized() is True


class TestCreateHarness:
    """Tests for create_harness factory function."""

    def test_create_harness_basic(self, tmp_path: Path):
        """Test creating a harness with basic parameters."""
        project = tmp_path / "project"
        project.mkdir()

        harness = create_harness(project)

        assert harness.project_path == project.resolve()

    def test_create_harness_with_spec(self, tmp_path: Path):
        """Test creating a harness with a spec."""
        project = tmp_path / "project"
        project.mkdir()

        harness = create_harness(project, spec="Build something")

        assert harness.spec == "Build something"


class TestHarnessIntegration:
    """Integration tests for the harness."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a temporary project directory."""
        project = tmp_path / "integration-test"
        project.mkdir()
        return project

    @pytest.fixture
    def config(self) -> Config:
        """Create a test configuration."""
        return Config()

    def test_full_init_cycle(self, project_path: Path, config: Config):
        """Test a full initialization cycle."""
        harness = AutoDevHarness(
            project_path,
            spec="Build a counter app with increment and decrement",
            config=config,
        )

        # Should not be initialized
        assert not harness.is_initialized()

        # Initialize
        harness.initialize()

        # Should be initialized now
        assert harness.is_initialized()

        # Should have artifacts
        assert harness.feature_list_path.exists()
        assert harness.progress_path.exists()

        # Should be able to recover context
        context = harness.recover_context()
        assert context is not None
