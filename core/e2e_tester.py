"""
E2E testing framework for AutoDev.

Uses Playwright for browser automation to verify features work.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.config import Config
from core.models import TestResult

logger = logging.getLogger(__name__)


@dataclass
class TestStep:
    """A single step in an E2E test."""
    name: str
    action: str
    selector: Optional[str] = None
    value: Optional[str] = None
    expected: Optional[str] = None
    timeout: int = 5000
    optional: bool = False


@dataclass
class TestCase:
    """An E2E test case definition."""
    id: str
    feature_id: str
    name: str
    description: str
    url: str
    steps: List[TestStep] = field(default_factory=list)
    setup_steps: List[TestStep] = field(default_factory=list)
    teardown_steps: List[TestStep] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)


class E2ETester:
    """
    E2E testing framework using Playwright.

    This enables the agent to test features like a human user would.
    """

    def __init__(
        self,
        project_path: Path,
        config: Optional[Config] = None,
    ):
        self.project_path = Path(project_path).resolve()
        self.config = config or Config()
        self._browser = None
        self._page = None
        self._playwright = None
        self._test_results: List[TestResult] = []
        self._screenshots_dir = self.project_path / ".autodev" / "screenshots"

    def is_available(self) -> bool:
        """Check if Playwright is available."""
        try:
            import playwright
            return True
        except ImportError:
            return False

    async def start_browser(
        self,
        headless: Optional[bool] = None,
        browser_type: Optional[str] = None,
    ) -> None:
        """
        Start the browser.

        Args:
            headless: Run in headless mode (default from config).
            browser_type: Browser to use (chromium, firefox, webkit).
        """
        try:
            from playwright.async_api import async_playwright

            headless = headless if headless is not None else self.config.testing.headless
            browser_type = browser_type or self.config.testing.browser

            self._playwright = await async_playwright().start()

            browser_launcher = getattr(self._playwright, browser_type, self._playwright.chromium)
            self._browser = await browser_launcher.launch(headless=headless)
            self._page = await self._browser.new_page()

            # Create screenshots directory
            self._screenshots_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Started {browser_type} browser (headless={headless})")

        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install"
            )

    async def stop_browser(self) -> None:
        """Stop the browser."""
        if self._page:
            await self._page.close()
            self._page = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        logger.info("Browser stopped")

    async def navigate(self, url: str, wait_until: str = "load") -> None:
        """Navigate to a URL."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start_browser() first.")

        await self._page.goto(url, wait_until=wait_until)
        logger.debug(f"Navigated to {url}")

    async def click(self, selector: str, timeout: int = 5000) -> None:
        """Click an element."""
        if not self._page:
            raise RuntimeError("Browser not started")

        await self._page.click(selector, timeout=timeout)
        logger.debug(f"Clicked: {selector}")

    async def fill(self, selector: str, value: str, timeout: int = 5000) -> None:
        """Fill a form field."""
        if not self._page:
            raise RuntimeError("Browser not started")

        await self._page.fill(selector, value, timeout=timeout)
        logger.debug(f"Filled: {selector} = {value}")

    async def type(self, selector: str, text: str, delay: int = 50) -> None:
        """Type text into an element (character by character)."""
        if not self._page:
            raise RuntimeError("Browser not started")

        await self._page.type(selector, text, delay=delay)
        logger.debug(f"Typed into: {selector}")

    async def press(self, key: str) -> None:
        """Press a keyboard key."""
        if not self._page:
            raise RuntimeError("Browser not started")

        await self._page.keyboard.press(key)
        logger.debug(f"Pressed key: {key}")

    async def wait_for_selector(
        self,
        selector: str,
        timeout: int = 30000,
        state: str = "visible",
    ) -> None:
        """Wait for a selector to appear."""
        if not self._page:
            raise RuntimeError("Browser not started")

        await self._page.wait_for_selector(selector, timeout=timeout, state=state)
        logger.debug(f"Waited for: {selector}")

    async def wait_for_load_state(self, state: str = "networkidle") -> None:
        """Wait for page to reach a load state."""
        if not self._page:
            raise RuntimeError("Browser not started")

        await self._page.wait_for_load_state(state)
        logger.debug(f"Waited for load state: {state}")

    async def get_text(self, selector: str) -> str:
        """Get text content of an element."""
        if not self._page:
            raise RuntimeError("Browser not started")

        element = await self._page.wait_for_selector(selector)
        if element:
            text = await element.text_content()
            return text or ""
        return ""

    async def get_value(self, selector: str) -> str:
        """Get value of a form field."""
        if not self._page:
            raise RuntimeError("Browser not started")

        value = await self._page.input_value(selector)
        return value or ""

    async def is_visible(self, selector: str) -> bool:
        """Check if an element is visible."""
        if not self._page:
            raise RuntimeError("Browser not started")

        try:
            element = await self._page.query_selector(selector)
            if element:
                return await element.is_visible()
        except Exception:
            pass
        return False

    async def screenshot(self, name: Optional[str] = None) -> str:
        """
        Take a screenshot.

        Args:
            name: Screenshot name (will be saved as {name}.png).

        Returns:
            Path to the screenshot file.
        """
        if not self._page:
            raise RuntimeError("Browser not started")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}-{name or 'screenshot'}.png"
        filepath = self._screenshots_dir / filename

        await self._page.screenshot(path=str(filepath))
        logger.info(f"Screenshot saved: {filepath}")

        return str(filepath)

    async def verify_text(
        self,
        selector: str,
        expected: str,
        exact: bool = False,
    ) -> bool:
        """
        Verify that an element contains expected text.

        Args:
            selector: Element selector.
            expected: Expected text.
            exact: If True, text must match exactly.

        Returns:
            True if verification passed.
        """
        text = await self.get_text(selector)

        if exact:
            passed = text.strip() == expected.strip()
        else:
            passed = expected in text

        logger.debug(f"Text verification ({'passed' if passed else 'failed'}): {selector}")
        return passed

    async def verify_value(
        self,
        selector: str,
        expected: str,
    ) -> bool:
        """Verify that a form field has the expected value."""
        value = await self.get_value(selector)
        passed = value == expected
        logger.debug(f"Value verification ({'passed' if passed else 'failed'}): {selector}")
        return passed

    async def execute_step(self, step: TestStep) -> Dict[str, Any]:
        """
        Execute a single test step.

        Returns:
            Dict with success status and any captured values.
        """
        result = {
            "name": step.name,
            "action": step.action,
            "success": False,
            "error": None,
            "value": None,
        }

        try:
            if step.action == "click":
                await self.click(step.selector, timeout=step.timeout)
                result["success"] = True

            elif step.action == "fill":
                await self.fill(step.selector, step.value, timeout=step.timeout)
                result["success"] = True

            elif step.action == "type":
                await self.type(step.selector, step.value)
                result["success"] = True

            elif step.action == "press":
                await self.press(step.value)
                result["success"] = True

            elif step.action == "wait":
                await self.wait_for_selector(step.selector, timeout=step.timeout)
                result["success"] = True

            elif step.action == "navigate":
                await self.navigate(step.value)
                result["success"] = True

            elif step.action == "verify_text":
                passed = await self.verify_text(step.selector, step.expected)
                result["success"] = passed
                if not passed:
                    actual = await self.get_text(step.selector)
                    result["error"] = f"Expected '{step.expected}' but got '{actual}'"

            elif step.action == "verify_value":
                passed = await self.verify_value(step.selector, step.expected)
                result["success"] = passed

            elif step.action == "screenshot":
                path = await self.screenshot(step.value)
                result["value"] = path
                result["success"] = True

            elif step.action == "wait_for_load":
                await self.wait_for_load_state(step.value or "networkidle")
                result["success"] = True

            else:
                result["error"] = f"Unknown action: {step.action}"

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Step '{step.name}' failed: {e}")

            # Take screenshot on failure if configured
            if self.config.testing.screenshot_on_failure:
                try:
                    await self.screenshot(f"failure-{step.name}")
                except Exception:
                    pass

        return result

    async def run_test(self, test_case: TestCase) -> TestResult:
        """
        Run a complete E2E test case.

        Args:
            test_case: TestCase to run.

        Returns:
            TestResult with pass/fail status.
        """
        logger.info(f"Running E2E test: {test_case.name}")

        result = TestResult(
            feature_id=test_case.feature_id,
            passed=False,
        )

        try:
            # Start browser
            await self.start_browser()

            # Navigate to URL
            await self.navigate(test_case.url)

            # Run setup steps
            for step in test_case.setup_steps:
                step_result = await self.execute_step(step)
                if not step_result["success"] and not step.optional:
                    result.failures.append(f"Setup failed: {step.name} - {step_result['error']}")
                    result.error_message = f"Setup step '{step.name}' failed"
                    return result

            # Run main test steps
            steps_executed = []
            for step in test_case.steps:
                step_result = await self.execute_step(step)
                steps_executed.append(step.name)

                result.steps_executed.append(f"{step.name}: {step.action}")

                if not step_result["success"] and not step.optional:
                    result.failures.append(f"{step.name}: {step_result['error']}")

                    # Take failure screenshot
                    if self.config.testing.screenshot_on_failure:
                        screenshot_path = await self.screenshot(f"failure-{test_case.id}")
                        result.screenshots.append(screenshot_path)

                    result.error_message = f"Step '{step.name}' failed: {step_result['error']}"
                    return result

            # Run teardown steps
            for step in test_case.teardown_steps:
                await self.execute_step(step)

            # All steps passed
            result.passed = True
            logger.info(f"E2E test passed: {test_case.name}")

        except Exception as e:
            result.error_message = str(e)
            result.failures.append(str(e))
            logger.error(f"E2E test failed: {test_case.name} - {e}")

        finally:
            await self.stop_browser()

        self._test_results.append(result)
        return result

    def get_results(self) -> List[TestResult]:
        """Get all test results."""
        return self._test_results

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all test results."""
        total = len(self._test_results)
        passed = sum(1 for r in self._test_results if r.passed)
        failed = total - passed

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / total * 100) if total > 0 else 0,
        }


class TestParser:
    """Parse natural language test steps into TestStep objects."""

    @staticmethod
    def parse_steps(step_descriptions: List[str]) -> List[TestStep]:
        """
        Parse natural language step descriptions into TestStep objects.

        This uses heuristics to convert human-readable steps into
        structured test steps.
        """
        steps = []

        for i, desc in enumerate(step_descriptions):
            step = TestParser._parse_single_step(desc, i)
            if step:
                steps.append(step)

        return steps

    @staticmethod
    def _parse_single_step(description: str, index: int) -> Optional[TestStep]:
        """Parse a single step description."""
        import re

        desc_lower = description.lower().strip()

        # Generate step name
        name = f"step_{index + 1}"

        # Pattern: Click [on] X
        click_match = re.search(r"click\s+(?:on\s+)?['\"]?([^'\"]+)['\"]?", description, re.I)
        if click_match:
            return TestStep(
                name=name,
                action="click",
                selector=TestParser._extract_selector(click_match.group(1)),
            )

        # Pattern: Type X [into] Y
        type_match = re.search(r"type\s+['\"]?([^'\"]+)['\"]?\s+(?:into\s+)?['\"]?([^'\"]+)['\"]?", description, re.I)
        if type_match:
            return TestStep(
                name=name,
                action="fill",
                selector=TestParser._extract_selector(type_match.group(2)),
                value=type_match.group(1),
            )

        # Pattern: Navigate to X
        nav_match = re.search(r"navigate\s+(?:to\s+)?['\"]?([^'\"]+)['\"]?", description, re.I)
        if nav_match:
            return TestStep(
                name=name,
                action="navigate",
                value=nav_match.group(1),
            )

        # Pattern: Verify [that] X [contains/equals] Y
        verify_match = re.search(
            r"verify\s+(?:that\s+)?['\"]?([^'\"]+)['\"]?\s+(?:contains|equals|shows|displays)\s+['\"]?([^'\"]+)['\"]?",
            description, re.I
        )
        if verify_match:
            return TestStep(
                name=name,
                action="verify_text",
                selector=TestParser._extract_selector(verify_match.group(1)),
                expected=verify_match.group(2),
            )

        # Pattern: Wait for X
        wait_match = re.search(r"wait\s+(?:for\s+)?['\"]?([^'\"]+)['\"]?", description, re.I)
        if wait_match:
            return TestStep(
                name=name,
                action="wait",
                selector=TestParser._extract_selector(wait_match.group(1)),
            )

        # Pattern: Press X (key)
        press_match = re.search(r"press\s+['\"]?([^'\"]+)['\"]?", description, re.I)
        if press_match:
            return TestStep(
                name=name,
                action="press",
                value=press_match.group(1).upper(),
            )

        # Default: treat as a generic action (will need manual implementation)
        return TestStep(
            name=name,
            action="verify_text",
            selector=TestParser._extract_selector(description),
            expected="",
        )

    @staticmethod
    def _extract_selector(text: str) -> str:
        """Extract a CSS selector from text."""
        import re

        # If it looks like a CSS selector already, use it
        if re.match(r"^[#.\[\w]", text):
            return text

        # Try to convert common patterns
        text = text.strip().lower()

        # "New Chat button" -> button:has-text("New Chat")
        if "button" in text:
            button_text = re.search(r"['\"]?([^'\"]+)['\"]?\s+button", text)
            if button_text:
                return f'button:has-text("{button_text.group(1)}")'
            return "button"

        # "X input/field" -> input[placeholder*="X"]
        if "input" in text or "field" in text:
            return "input"

        # "X link" -> a:has-text("X")
        if "link" in text:
            link_text = re.search(r"['\"]?([^'\"]+)['\"]?\s+link", text)
            if link_text:
                return f'a:has-text("{link_text.group(1)}")'
            return "a"

        # Default: try text content
        return f'text="{text}"'


# Convenience function for sync usage
def run_e2e_test(
    project_path: Path,
    test_case: TestCase,
    config: Optional[Config] = None,
) -> TestResult:
    """
    Run an E2E test synchronously.

    This is a convenience wrapper for the async E2ETester.
    """
    tester = E2ETester(project_path, config)
    return asyncio.run(tester.run_test(test_case))
