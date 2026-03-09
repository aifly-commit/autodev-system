"""
Browser automation for E2E testing.

Uses Playwright for browser automation.
"""

import logging
from pathlib import Path
from typing import Optional

from core.config import Config
from core.exceptions import TestError
from core.models import TestResult

logger = logging.getLogger(__name__)


class BrowserAutomation:
    """
    Browser automation using Playwright.

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

    def is_available(self) -> bool:
        """Check if Playwright is available."""
        try:
            import playwright
            return True
        except ImportError:
            return False

    async def start(self, url: str = "http://localhost:3000") -> None:
        """
        Start the browser and navigate to URL.

        Args:
            url: URL to navigate to.
        """
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            browser_type = getattr(self._playwright, self.config.testing.browser)
            self._browser = await browser_type.launch(
                headless=self.config.testing.headless
            )
            self._page = await self._browser.new_page()

            logger.info(f"Navigating to {url}")
            await self._page.goto(url)

        except ImportError:
            raise TestError(
                "Playwright not installed. Run: pip install playwright && playwright install"
            )

    async def stop(self) -> None:
        """Stop the browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

        self._browser = None
        self._page = None
        self._playwright = None

    async def click(self, selector: str) -> None:
        """Click an element."""
        if not self._page:
            raise TestError("Browser not started")

        await self._page.click(selector)

    async def fill(self, selector: str, value: str) -> None:
        """Fill a form field."""
        if not self._page:
            raise TestError("Browser not started")

        await self._page.fill(selector, value)

    async def text_content(self, selector: str) -> Optional[str]:
        """Get text content of an element."""
        if not self._page:
            raise TestError("Browser not started")

        return await self._page.text_content(selector)

    async def screenshot(self, path: Optional[str] = None) -> bytes:
        """
        Take a screenshot.

        Args:
            path: Optional path to save screenshot.

        Returns:
            Screenshot as bytes.
        """
        if not self._page:
            raise TestError("Browser not started")

        if path:
            await self._page.screenshot(path=path)
            logger.info(f"Screenshot saved to {path}")

        return await self._page.screenshot()

    async def wait_for_selector(self, selector: str, timeout: int = 30000) -> None:
        """Wait for a selector to appear."""
        if not self._page:
            raise TestError("Browser not started")

        await self._page.wait_for_selector(selector, timeout=timeout)

    async def verify_text(self, selector: str, expected: str) -> bool:
        """Verify that an element contains expected text."""
        content = await self.text_content(selector)
        if content is None:
            return False
        return expected in content

    async def run_test_steps(self, steps: list[str]) -> TestResult:
        """
        Run a series of test steps.

        This is a simplified interpreter for test steps.
        A full implementation would use NLP or structured steps.

        Args:
            steps: List of test step descriptions.

        Returns:
            TestResult with pass/fail status.
        """
        executed = []
        failures = []

        for step in steps:
            try:
                # This is a placeholder - actual implementation would
                # parse the step and execute appropriate actions
                logger.info(f"Executing step: {step}")
                executed.append(step)

                # Placeholder success
                # Real implementation would verify each step

            except Exception as e:
                failures.append(f"{step}: {str(e)}")
                if self.config.testing.screenshot_on_failure:
                    await self.screenshot(f"failure-{len(failures)}.png")
                break

        return TestResult(
            feature_id="e2e-test",
            passed=len(failures) == 0,
            steps_executed=executed,
            failures=failures,
        )


# Sync wrapper for convenience
class SyncBrowserAutomation:
    """
    Synchronous wrapper for BrowserAutomation.

    Useful for simple test scripts.
    """

    def __init__(self, project_path: Path, config: Optional[Config] = None):
        self._async = BrowserAutomation(project_path, config)

    def run_test(self, url: str, steps: list[str]) -> TestResult:
        """
        Run an E2E test synchronously.

        Args:
            url: URL to test.
            steps: Test steps to execute.

        Returns:
            TestResult.
        """
        import asyncio

        async def _run():
            await self._async.start(url)
            try:
                return await self._async.run_test_steps(steps)
            finally:
                await self._async.stop()

        return asyncio.run(_run())
