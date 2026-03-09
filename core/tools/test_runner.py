"""
Test runner for AutoDev.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from core.config import Config
from core.exceptions import TestError
from core.models import TestResult

logger = logging.getLogger(__name__)


class TestRunner:
    """
    Runs tests for the project.

    Supports various test frameworks:
    - pytest (Python)
    - jest (JavaScript/TypeScript)
    - vitest (JavaScript/TypeScript)
    """

    def __init__(self, project_path: Path, config: Optional[Config] = None):
        self.project_path = Path(project_path).resolve()
        self.config = config or Config()

    def detect_framework(self) -> Optional[str]:
        """Detect the test framework being used."""
        if (self.project_path / "pytest.ini").exists() or \
           (self.project_path / "setup.cfg").exists():
            return "pytest"

        if (self.project_path / "jest.config.js").exists() or \
           (self.project_path / "jest.config.ts").exists():
            return "jest"

        if (self.project_path / "vitest.config.js").exists() or \
           (self.project_path / "vitest.config.ts").exists():
            return "vitest"

        # Check package.json for jest/vitest
        package_json = self.project_path / "package.json"
        if package_json.exists():
            import json
            with open(package_json) as f:
                data = json.load(f)
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "jest" in deps:
                    return "jest"
                if "vitest" in deps:
                    return "vitest"

        # Check for requirements.txt or pyproject.toml
        if (self.project_path / "requirements.txt").exists() or \
           (self.project_path / "pyproject.toml").exists():
            return "pytest"

        return None

    def run_unit_tests(self) -> TestResult:
        """Run unit tests."""
        framework = self.detect_framework()

        if framework == "pytest":
            return self._run_pytest()
        elif framework == "jest":
            return self._run_jest()
        elif framework == "vitest":
            return self._run_vitest()
        else:
            raise TestError(f"Unknown test framework: {framework}")

    def _run_pytest(self) -> TestResult:
        """Run pytest."""
        try:
            result = subprocess.run(
                ["pytest", "-v", "--tb=short"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=self.config.testing.test_timeout_ms / 1000,
            )

            return TestResult(
                feature_id="unit-tests",
                passed=result.returncode == 0,
                steps_executed=["pytest -v --tb=short"],
                failures=[result.stderr] if result.returncode != 0 else [],
                error_message=result.stderr if result.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired:
            raise TestError("Unit tests timed out")
        except FileNotFoundError:
            raise TestError("pytest not found")

    def _run_jest(self) -> TestResult:
        """Run jest."""
        try:
            result = subprocess.run(
                ["npx", "jest", "--passWithNoTests"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=self.config.testing.test_timeout_ms / 1000,
            )

            return TestResult(
                feature_id="unit-tests",
                passed=result.returncode == 0,
                steps_executed=["npx jest --passWithNoTests"],
                failures=[result.stderr] if result.returncode != 0 else [],
                error_message=result.stderr if result.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired:
            raise TestError("Unit tests timed out")
        except FileNotFoundError:
            raise TestError("jest not found")

    def _run_vitest(self) -> TestResult:
        """Run vitest."""
        try:
            result = subprocess.run(
                ["npx", "vitest", "run", "--passWithNoTests"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=self.config.testing.test_timeout_ms / 1000,
            )

            return TestResult(
                feature_id="unit-tests",
                passed=result.returncode == 0,
                steps_executed=["npx vitest run --passWithNoTests"],
                failures=[result.stderr] if result.returncode != 0 else [],
                error_message=result.stderr if result.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired:
            raise TestError("Unit tests timed out")
        except FileNotFoundError:
            raise TestError("vitest not found")

    def run_smoke_test(self) -> bool:
        """
        Run a quick smoke test to verify basic functionality.

        This should be fast and verify the app starts correctly.
        """
        # Placeholder - would be implemented based on project type
        logger.info("Running smoke test...")
        return True
