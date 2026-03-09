"""
Tests for Phase 3: State Management and Session Recovery.
"""

import pytest
from datetime import datetime
from pathlib import Path
import json

from core.config import Config
from core.progress_manager import ProgressManager
from core.session_manager import SessionManager
from core.tools.git_ops import GitOperations
from core.models import ProgressEntry, Feature, FeatureList, FeatureStatus, Priority


class TestProgressManager:
    """Tests for ProgressManager."""

    @pytest.fixture
    def progress_path(self, tmp_path: Path) -> Path:
        """Create a temporary progress file path."""
        return tmp_path / ".autodev" / "progress.md"

    @pytest.fixture
    def manager(self, progress_path: Path) -> ProgressManager:
        """Create a ProgressManager instance."""
        return ProgressManager(progress_path)

    def test_create_initial(self, manager: ProgressManager):
        """Test creating initial progress file."""
        manager.create_initial()

        assert manager.exists()
        content = manager.read()
        assert "# AutoDev Progress Log" in content

    def test_append_entry(self, manager: ProgressManager):
        """Test appending a progress entry."""
        manager.create_initial()

        entry = ProgressEntry(
            session_id="20240101-001",
            agent_type="coder",
            feature_id="F001",
            action="Implemented login",
            result="Success",
            next_steps=["Add logout"],
        )

        manager.append(entry)

        content = manager.read()
        assert "20240101-001" in content
        assert "Implemented login" in content
        assert "Success" in content
        assert "Add logout" in content

    def test_parse_entries(self, manager: ProgressManager):
        """Test parsing progress entries."""
        manager.create_initial()

        # Add multiple entries
        for i in range(3):
            entry = ProgressEntry(
                session_id=f"2024010{i}-001",
                agent_type="coder",
                feature_id=f"F00{i}",
                action=f"Action {i}",
                result=f"Result {i}",
            )
            manager.append(entry)

        entries = manager.parse_entries()

        assert len(entries) == 3
        assert entries[0].session_id == "20240100-001"
        assert entries[2].session_id == "20240102-001"

    def test_get_last_entry(self, manager: ProgressManager):
        """Test getting the last entry."""
        manager.create_initial()

        # No entries yet
        assert manager.get_last_entry() is None

        # Add entries
        for i in range(3):
            entry = ProgressEntry(
                session_id=f"session-{i}",
                agent_type="coder",
                action=f"Action {i}",
                result=f"Result {i}",
            )
            manager.append(entry)

        last = manager.get_last_entry()
        assert last is not None
        assert last.session_id == "session-2"

    def test_get_entries_for_feature(self, manager: ProgressManager):
        """Test getting entries for a specific feature."""
        manager.create_initial()

        # Add entries for different features
        for i in range(5):
            entry = ProgressEntry(
                session_id=f"session-{i}",
                agent_type="coder",
                feature_id=f"F00{i % 2}",  # F000 and F001
                action=f"Action {i}",
                result=f"Result {i}",
            )
            manager.append(entry)

        f000_entries = manager.get_entries_for_feature("F000")
        f001_entries = manager.get_entries_for_feature("F001")

        assert len(f000_entries) == 3  # 0, 2, 4
        assert len(f001_entries) == 2  # 1, 3

    def test_get_summary(self, manager: ProgressManager):
        """Test getting progress summary."""
        manager.create_initial()

        # Add entries
        for i in range(3):
            entry = ProgressEntry(
                session_id=f"session-{i}",
                agent_type="coder",
                feature_id=f"F00{i}",
                action=f"Action {i}",
                result=f"Result {i}",
            )
            manager.append(entry)

        summary = manager.get_summary()

        assert summary["total_sessions"] == 3
        assert "coder" in summary["agent_counts"]
        assert summary["agent_counts"]["coder"] == 3


class TestGitOperations:
    """Tests for GitOperations."""

    @pytest.fixture
    def repo_path(self, tmp_path: Path) -> Path:
        """Create a temporary git repository."""
        repo = tmp_path / "test-repo"
        repo.mkdir()

        # Initialize git
        import subprocess
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

        # Create initial commit
        (repo / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True, capture_output=True)

        return repo

    @pytest.fixture
    def git_ops(self, repo_path: Path) -> GitOperations:
        """Create a GitOperations instance."""
        return GitOperations(repo_path)

    def test_is_repo(self, git_ops: GitOperations):
        """Test checking if path is a repo."""
        assert git_ops.is_repo() is True

    def test_status(self, git_ops: GitOperations, repo_path: Path):
        """Test getting repository status."""
        status = git_ops.status()

        assert "files" in status
        assert "clean" in status
        assert status["clean"] is True

    def test_status_with_changes(self, git_ops: GitOperations, repo_path: Path):
        """Test status with uncommitted changes."""
        (repo_path / "new_file.txt").write_text("test")

        status = git_ops.status()

        assert status["clean"] is False
        assert len(status["files"]) == 1

    def test_commit(self, git_ops: GitOperations, repo_path: Path):
        """Test creating a commit."""
        (repo_path / "test.txt").write_text("test content")
        git_ops.add("test.txt")

        commit_hash = git_ops.commit("Add test file")

        assert commit_hash is not None
        assert len(commit_hash) == 8

    def test_log(self, git_ops: GitOperations):
        """Test getting commit log."""
        commits = git_ops.log(5)

        assert len(commits) >= 1
        assert "hash" in commits[0]
        assert "message" in commits[0]

    def test_current_branch(self, git_ops: GitOperations):
        """Test getting current branch."""
        branch = git_ops.current_branch()

        assert branch in ["main", "master"]

    def test_create_branch(self, git_ops: GitOperations):
        """Test creating a new branch."""
        git_ops.create_branch("test-feature")

        assert git_ops.current_branch() == "autodev/test-feature"

    def test_has_changes(self, git_ops: GitOperations, repo_path: Path):
        """Test checking for uncommitted changes."""
        assert git_ops.has_changes() is False

        (repo_path / "new.txt").write_text("new")
        assert git_ops.has_changes() is True

    def test_get_repo_info(self, git_ops: GitOperations):
        """Test getting repository info."""
        info = git_ops.get_repo_info()

        assert info["is_repo"] is True
        assert info["branch"] is not None
        assert info["commit_count"] >= 1


class TestSessionManager:
    """Tests for SessionManager."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a temporary project directory."""
        project = tmp_path / "test-project"
        project.mkdir()

        # Create .autodev directory
        autodev = project / ".autodev"
        autodev.mkdir()

        # Create feature list
        feature_list = FeatureList(
            project="test-project",
            features=[
                Feature(id="F001", description="Feature 1", passes=False),
                Feature(id="F002", description="Feature 2", passes=True),
                Feature(id="F003", description="Feature 3", passes=False),
            ]
        )

        with open(autodev / "feature_list.json", "w") as f:
            json.dump(feature_list.model_dump(mode="json"), f, indent=2, default=str)

        # Create initial progress file
        (autodev / "progress.md").write_text("# AutoDev Progress Log\n\n---\n")

        # Initialize git
        import subprocess
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True, capture_output=True)
        (project / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=project, check=True, capture_output=True)

        return project

    @pytest.fixture
    def session_manager(self, project_path: Path) -> SessionManager:
        """Create a SessionManager instance."""
        return SessionManager(project_path)

    def test_is_initialized(self, session_manager: SessionManager):
        """Test checking if project is initialized."""
        assert session_manager.is_initialized() is True

    def test_start_session(self, session_manager: SessionManager):
        """Test starting a session."""
        session_id = session_manager.start_session("coder")

        assert session_id is not None
        assert "cod" in session_id
        assert session_manager.current_session_id == session_id

    def test_end_session(self, session_manager: SessionManager):
        """Test ending a session."""
        session_manager.start_session("coder")
        session_manager.end_session(
            action="Test action",
            result="Test result",
            feature_id="F001",
            next_steps=["Step 1", "Step 2"],
        )

        # Check progress was logged
        entries = session_manager.progress_manager.parse_entries()
        assert len(entries) == 1
        assert entries[0].action == "Test action"
        assert entries[0].feature_id == "F001"

    def test_get_session_history(self, session_manager: SessionManager):
        """Test getting session history."""
        # Add some sessions
        for i in range(3):
            session_manager.start_session("coder")
            session_manager.end_session(
                action=f"Action {i}",
                result=f"Result {i}",
            )

        history = session_manager.get_session_history()

        assert len(history) == 3

    def test_recover_context(self, session_manager: SessionManager):
        """Test recovering session context."""
        context = session_manager.recover_context()

        assert context.working_directory is not None
        assert context.project_name == "test-project"
        assert context.current_feature is not None
        assert context.current_feature.id == "F001"  # First pending
        assert context.pending_features_count == 2  # F001 and F003

    def test_mark_feature_started(self, session_manager: SessionManager):
        """Test marking a feature as started."""
        session_manager.mark_feature_started("F001")

        # Verify the feature status changed
        feature_list = session_manager._load_feature_list()
        feature = next(f for f in feature_list.features if f.id == "F001")
        assert feature.status == FeatureStatus.IN_PROGRESS

    def test_mark_feature_complete(self, session_manager: SessionManager):
        """Test marking a feature as complete."""
        session_manager.mark_feature_complete("F001")

        feature_list = session_manager._load_feature_list()
        feature = next(f for f in feature_list.features if f.id == "F001")
        assert feature.passes is True

    def test_mark_feature_failed(self, session_manager: SessionManager):
        """Test marking a feature as failed."""
        session_manager.mark_feature_failed("F001", "Something went wrong")

        feature_list = session_manager._load_feature_list()
        feature = next(f for f in feature_list.features if f.id == "F001")
        assert feature.status == FeatureStatus.FAILED
        assert feature.notes == "Something went wrong"

    def test_detect_known_issues(self, session_manager: SessionManager, project_path: Path):
        """Test detecting known issues."""
        issues = session_manager._detect_known_issues()

        # Should have no dependency file issue
        assert any("dependency" in i.lower() for i in issues)

    def test_get_feature_history(self, session_manager: SessionManager):
        """Test getting history for a specific feature."""
        # Add sessions for different features
        for feature_id in ["F001", "F002", "F001"]:
            session_manager.start_session("coder")
            session_manager.end_session(
                action=f"Work on {feature_id}",
                result="Done",
                feature_id=feature_id,
            )

        f001_history = session_manager.get_feature_history("F001")

        assert len(f001_history) == 2
        assert all(e.feature_id == "F001" for e in f001_history)


class TestIntegration:
    """Integration tests for Phase 3."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a full project setup."""
        project = tmp_path / "integration-project"
        project.mkdir()

        # Create .autodev
        autodev = project / ".autodev"
        autodev.mkdir()

        # Create feature list
        feature_list = FeatureList(
            project="integration-test",
            features=[
                Feature(
                    id="F001",
                    description="First feature",
                    priority=Priority.HIGH,
                    passes=False,
                ),
            ]
        )

        with open(autodev / "feature_list.json", "w") as f:
            json.dump(feature_list.model_dump(mode="json"), f, indent=2, default=str)

        (autodev / "progress.md").write_text("# AutoDev Progress Log\n\n---\n")

        # Git setup
        import subprocess
        subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True, capture_output=True)

        return project

    def test_full_session_workflow(self, project_path: Path):
        """Test a complete session workflow."""
        manager = SessionManager(project_path)

        # Start session
        session_id = manager.start_session("coder")

        # Recover context
        context = manager.recover_context()

        # Mark feature as started
        manager.mark_feature_started(context.current_feature.id)

        # End session with results
        manager.end_session(
            action=f"Implemented {context.current_feature.id}",
            result="Feature implemented and tested",
            feature_id=context.current_feature.id,
            next_steps=["Move to next feature"],
        )

        # Mark feature as complete
        manager.mark_feature_complete(context.current_feature.id)

        # Verify final state
        final_context = manager.recover_context()
        assert final_context.pending_features_count == 0

        # Check history
        history = manager.get_session_history()
        assert len(history) == 1
        assert history[0]["feature_id"] == context.current_feature.id
