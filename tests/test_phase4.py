"""
Tests for Phase 4: E2E Testing and Init Script Generation.
"""

import pytest
import asyncio
from pathlib import Path
import json

from core.config import Config
from core.e2e_tester import E2ETester, TestCase, TestStep, TestParser
from core.init_generator import InitScriptGenerator, create_init_script


class TestInitScriptGenerator:
    """Tests for init script generator."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a temporary project directory."""
        return tmp_path / "test-project"

    def test_detect_node_project(self, project_path: Path):
        """Test detecting Node.js project."""
        project_path.mkdir()
        (project_path / "package.json").write_text('{"name": "test"}')

        project_type = InitScriptGenerator.detect_project_type(project_path)
        assert project_type == "node"

    def test_detect_python_project_pyproject(self, project_path: Path):
        """Test detecting Python project with pyproject.toml."""
        project_path.mkdir()
        (project_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        project_type = InitScriptGenerator.detect_project_type(project_path)
        assert project_type == "python"

    def test_detect_python_project_requirements(self, project_path: Path):
        """Test detecting Python project with requirements.txt."""
        project_path.mkdir()
        (project_path / "requirements.txt").write_text("requests")

        project_type = InitScriptGenerator.detect_project_type(project_path)
        assert project_type == "python"

    def test_detect_rust_project(self, project_path: Path):
        """Test detecting Rust project."""
        project_path.mkdir()
        (project_path / "Cargo.toml").write_text("[package]\nname = 'test'")

        project_type = InitScriptGenerator.detect_project_type(project_path)
        assert project_type == "rust"

    def test_detect_go_project(self, project_path: Path):
        """Test detecting Go project."""
        project_path.mkdir()
        (project_path / "go.mod").write_text("module test")

        project_type = InitScriptGenerator.detect_project_type(project_path)
        assert project_type == "go"

    def test_detect_java_maven_project(self, project_path: Path):
        """Test detecting Java Maven project."""
        project_path.mkdir()
        (project_path / "pom.xml").write_text("<project></project>")

        project_type = InitScriptGenerator.detect_project_type(project_path)
        assert project_type == "java-maven"

    def test_detect_java_gradle_project(self, project_path: Path):
        """Test detecting Java Gradle project."""
        project_path.mkdir()
        (project_path / "build.gradle").write_text("plugins { id 'java' }")

        project_type = InitScriptGenerator.detect_project_type(project_path)
        assert project_type == "java-gradle"

    def test_detect_unknown_project(self, project_path: Path):
        """Test detecting unknown project type."""
        project_path.mkdir()

        project_type = InitScriptGenerator.detect_project_type(project_path)
        assert project_type == "unknown"

    def test_generate_node_script(self, project_path: Path):
        """Test generating Node.js init script."""
        project_path.mkdir()
        (project_path / "package.json").write_text(json.dumps({
            "name": "test",
            "scripts": {"dev": "vite"}
        }))

        script = InitScriptGenerator.generate(project_path)

        assert "npm install" in script
        assert "npm run dev" in script

    def test_generate_python_script(self, project_path: Path):
        """Test generating Python init script."""
        project_path.mkdir()
        (project_path / "requirements.txt").write_text("flask")
        (project_path / "app.py").write_text("from flask import Flask")

        script = InitScriptGenerator.generate(project_path)

        assert "pip install" in script
        assert "python app.py" in script

    def test_generate_rust_script(self, project_path: Path):
        """Test generating Rust init script."""
        project_path.mkdir()
        (project_path / "Cargo.toml").write_text("[package]\nname = 'test'")

        script = InitScriptGenerator.generate(project_path)

        assert "cargo build" in script
        assert "cargo run" in script

    def test_create_init_script(self, project_path: Path):
        """Test creating init.sh file."""
        project_path.mkdir()
        (project_path / "package.json").write_text('{"name": "test"}')

        init_path = create_init_script(project_path)

        assert init_path.exists()
        assert init_path.name == "init.sh"

        # Check it's executable
        import os
        import stat
        mode = init_path.stat().st_mode
        assert mode & stat.S_IXUSR


class TestTestParser:
    """Tests for test step parser."""

    def test_parse_click_step(self):
        """Test parsing click step."""
        steps = TestParser.parse_steps([
            "Click 'Submit' button"
        ])

        assert len(steps) == 1
        assert steps[0].action == "click"
        assert "submit" in steps[0].selector.lower()

    def test_parse_type_step(self):
        """Test parsing type step."""
        steps = TestParser.parse_steps([
            "Type 'hello@example.com' into 'email' input"
        ])

        assert len(steps) == 1
        assert steps[0].action == "fill"
        assert steps[0].value == "hello@example.com"

    def test_parse_navigate_step(self):
        """Test parsing navigate step."""
        steps = TestParser.parse_steps([
            "Navigate to 'http://localhost:3000'"
        ])

        assert len(steps) == 1
        assert steps[0].action == "navigate"
        assert "localhost:3000" in steps[0].value

    def test_parse_verify_step(self):
        """Test parsing verify step."""
        steps = TestParser.parse_steps([
            "Verify 'Welcome' message contains 'Hello'"
        ])

        assert len(steps) == 1
        assert steps[0].action == "verify_text"

    def test_parse_multiple_steps(self):
        """Test parsing multiple steps."""
        steps = TestParser.parse_steps([
            "Navigate to 'http://localhost:3000'",
            "Click 'Login' button",
            "Type 'user@test.com' into 'email' field",
        ])

        assert len(steps) == 3
        assert steps[0].action == "navigate"
        assert steps[1].action == "click"
        assert steps[2].action == "fill"


class TestE2ETester:
    """Tests for E2E tester."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a temporary project directory."""
        project = tmp_path / "e2e-test-project"
        project.mkdir()
        return project

    def test_is_available(self, project_path: Path):
        """Test checking if Playwright is available."""
        tester = E2ETester(project_path)
        # Should return True or False without error
        result = tester.is_available()
        assert isinstance(result, bool)

    def test_create_test_case(self, project_path: Path):
        """Test creating a test case."""
        test_case = TestCase(
            id="TC001",
            feature_id="F001",
            name="Login Test",
            description="Test user login flow",
            url="http://localhost:3000/login",
            steps=[
                TestStep(
                    name="fill_email",
                    action="fill",
                    selector="#email",
                    value="test@example.com",
                ),
                TestStep(
                    name="click_submit",
                    action="click",
                    selector="button[type='submit']",
                ),
            ],
        )

        assert test_case.id == "TC001"
        assert len(test_case.steps) == 2

    def test_get_summary_empty(self, project_path: Path):
        """Test getting summary with no tests."""
        tester = E2ETester(project_path)
        summary = tester.get_summary()

        assert summary["total"] == 0
        assert summary["passed"] == 0

    @pytest.mark.asyncio
    async def test_browser_lifecycle(self, project_path: Path):
        """Test browser start and stop."""
        tester = E2ETester(project_path)

        if not tester.is_available():
            pytest.skip("Playwright not available")

        try:
            await tester.start_browser(headless=True)
            assert tester._browser is not None
            assert tester._page is not None
        finally:
            await tester.stop_browser()
            assert tester._browser is None
            assert tester._page is None


class TestE2EIntegration:
    """Integration tests for E2E testing."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a project with full structure."""
        project = tmp_path / "integration-project"
        project.mkdir()

        # Create package.json
        (project / "package.json").write_text(json.dumps({
            "name": "test-app",
            "scripts": {"dev": "vite --port 3000"},
            "dependencies": {"react": "^18.0.0"}
        }))

        return project

    def test_full_init_workflow(self, project_path: Path):
        """Test full init script generation workflow."""
        # Generate init script
        init_path = create_init_script(project_path)

        assert init_path.exists()

        # Verify content
        content = init_path.read_text()
        assert "npm install" in content
        assert "npm run dev" in content

    def test_test_case_from_feature(self, project_path: Path):
        """Test creating test case from feature definition."""
        # Simulate feature test steps
        test_steps = [
            "Navigate to 'http://localhost:3000'",
            "Click 'New Chat' button",
            "Type 'Hello' into 'message' input",
            "Click 'Send' button",
            "Verify 'response' contains 'Hello'",
        ]

        parsed_steps = TestParser.parse_steps(test_steps)

        test_case = TestCase(
            id="TC-F001",
            feature_id="F001",
            name="Chat Feature Test",
            description="Test the chat functionality",
            url="http://localhost:3000",
            steps=parsed_steps,
        )

        assert len(test_case.steps) == 5
        assert test_case.steps[0].action == "navigate"
        assert test_case.steps[1].action == "click"
        assert test_case.steps[2].action == "fill"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires running server")
    async def test_e2e_with_mock_server(self, project_path: Path):
        """Test E2E with a mock server (requires actual server)."""
        # This test would require a running server
        # Marked as skip for CI
        pass


class TestTestResult:
    """Tests for test result tracking."""

    def test_result_creation(self):
        """Test creating a test result."""
        from core.models import TestResult

        result = TestResult(
            feature_id="F001",
            passed=True,
            steps_executed=["step1", "step2"],
        )

        assert result.feature_id == "F001"
        assert result.passed is True
        assert len(result.steps_executed) == 2

    def test_result_with_failure(self):
        """Test creating a failed test result."""
        from core.models import TestResult

        result = TestResult(
            feature_id="F001",
            passed=False,
            steps_executed=["step1"],
            failures=["Element not found: #button"],
            error_message="Timeout waiting for selector",
        )

        assert result.passed is False
        assert len(result.failures) == 1
        assert result.error_message is not None
