"""
AutoDev - Autonomous Development System

A long-running agent harness for autonomous software development.
Based on Anthropic's design principles for multi-context window workflows.
"""

__version__ = "0.1.0"

from core.config import Config, get_config
from core.harness import AutoDevHarness
from core.models import (
    Feature,
    FeatureList,
    FeatureStatus,
    Priority,
    ProgressEntry,
    SessionContext,
    TestResult,
)
from core.progress_manager import ProgressManager
from core.session_manager import SessionManager
from core.e2e_tester import E2ETester, TestCase, TestStep
from core.init_generator import InitScriptGenerator, create_init_script

__all__ = [
    # Config
    "Config",
    "get_config",
    # Main harness
    "AutoDevHarness",
    # Models
    "Feature",
    "FeatureList",
    "FeatureStatus",
    "Priority",
    "ProgressEntry",
    "SessionContext",
    "TestResult",
    # Managers
    "ProgressManager",
    "SessionManager",
    # E2E Testing
    "E2ETester",
    "TestCase",
    "TestStep",
    # Init Script
    "InitScriptGenerator",
    "create_init_script",
]
