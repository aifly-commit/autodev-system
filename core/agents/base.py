"""
Base agent class for AutoDev system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from core.config import Config
from core.models import SessionContext


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    All agents share:
    - Configuration access
    - Session context
    - Tool access
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        session_context: Optional[SessionContext] = None,
    ):
        self.config = config or Config()
        self.session_context = session_context

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        pass

    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        """Execute the agent's task."""
        pass

    def set_context(self, context: SessionContext) -> None:
        """Set the session context."""
        self.session_context = context
