"""
Initializer Agent for AutoDev system.

The Initializer Agent runs ONCE at the start of a project to:
1. Analyze the specification
2. Generate a comprehensive feature list
3. Create init.sh script
4. Set up the initial project structure
5. Create the first git commit
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from core.agents.base import BaseAgent
from core.config import Config
from core.models import SessionContext
from core.llm_client import LLMClient, get_tool_definitions
from core.tool_executor import ToolExecutor, create_tool_handler

logger = logging.getLogger(__name__)


INITIALIZER_SYSTEM_PROMPT = """You are the Initializer Agent for AutoDev. Your job is to set up the development environment for a long-running autonomous coding project.

## Your Responsibilities

1. **Analyze the specification** and create a comprehensive feature list:
   - Break down the user's requirements into atomic, testable features
   - Each feature should be small enough to complete in one session
   - Include clear acceptance criteria and test steps for E2E verification

2. **Create the project structure**:
   - Initialize the appropriate tech stack
   - Set up the framework and dependencies
   - Create a clean project skeleton

3. **Write init.sh** - A script that:
   - Installs dependencies
   - Starts the development server
   - Includes basic health checks

4. **Create artifacts in .autodev directory**:
   - `feature_list.json` - All features with `passes: false`
   - Update `progress.md` with initialization details

5. **Git commit**: Create initial commit with message "Initial project setup by AutoDev"

## Feature List Format

The feature_list.json must follow this exact structure:

```json
{
  "project": "project-name",
  "version": "1.0.0",
  "spec": "original specification here",
  "features": [
    {
      "id": "F001",
      "category": "core",
      "priority": "high",
      "description": "Clear description of what this feature does",
      "acceptance_criteria": ["Criteria 1", "Criteria 2"],
      "test_steps": ["Step 1", "Step 2", "Step 3"],
      "status": "pending",
      "passes": false
    }
  ]
}
```

## Critical Rules

- DO NOT implement any features - only set up the environment
- Feature list MUST be valid JSON saved to `.autodev/feature_list.json`
- Each feature MUST have test_steps for E2E verification
- ALL features MUST start with `passes: false`
- Create a working project skeleton that can be started with `./init.sh`
- Use the tools available to you (bash, read, write, edit, glob, grep)
"""


class InitializerAgent(BaseAgent):
    """
    Agent responsible for project initialization.

    This agent runs only once at the start of a project.
    It sets up the foundation for all subsequent coding sessions.
    """

    def __init__(
        self,
        spec: str,
        project_path: Path,
        config: Optional[Config] = None,
        session_context: Optional[SessionContext] = None,
    ):
        super().__init__(config, session_context)
        self.spec = spec
        self.project_path = Path(project_path).resolve()
        self.llm_client = LLMClient(config)
        self.tool_executor = ToolExecutor(project_path, config)

    def get_system_prompt(self) -> str:
        """Return the system prompt for the initializer agent."""
        return INITIALIZER_SYSTEM_PROMPT

    def get_user_prompt(self) -> str:
        """Return the user prompt with the specification."""
        return f"""
Please initialize a new project at {self.project_path} with the following specification:

---
{self.spec}
---

Your tasks:
1. Create the project structure and initialize the tech stack
2. Create a comprehensive feature_list.json in .autodev/ directory
3. Create init.sh script to start the development server
4. Update progress.md with initialization details
5. Create initial git commit

Use the available tools (bash, read, write, edit, glob, grep) to complete these tasks.
"""

    def execute(self, *args, **kwargs) -> Any:
        """
        Execute the initialization.

        This calls the LLM with tools and handles the agentic loop.
        """
        logger.info(f"Starting InitializerAgent for project at {self.project_path}")

        # Ensure .autodev directory exists
        autodev_dir = self.project_path / ".autodev"
        autodev_dir.mkdir(parents=True, exist_ok=True)

        # Get tool definitions
        tools = get_tool_definitions()

        # Create tool handler
        tool_handler = create_tool_handler(self.tool_executor)

        # Get model config
        agent_config = self.config.agents.initializer

        # Call LLM with tools
        try:
            result = self.llm_client.create_message_with_tools(
                system_prompt=self.get_system_prompt(),
                user_prompt=self.get_user_prompt(),
                tools=tools,
                tool_handler=tool_handler,
                model=agent_config.model,
                max_tokens=agent_config.max_tokens,
                temperature=agent_config.temperature,
                max_tool_calls=100,
            )

            logger.info(f"InitializerAgent completed with {result['tool_calls']} tool calls")
            logger.info(f"Token usage: {result['usage']}")

            return {
                "success": True,
                "content": result["content"],
                "tool_calls": result["tool_calls"],
                "usage": result["usage"],
            }

        except Exception as e:
            logger.error(f"InitializerAgent failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }


def run_initializer(
    project_path: Path,
    spec: str,
    config: Optional[Config] = None,
) -> dict:
    """
    Convenience function to run the initializer agent.

    Args:
        project_path: Path to the project directory.
        spec: Project specification.
        config: Optional configuration.

    Returns:
        Result dict with success status.
    """
    agent = InitializerAgent(spec, project_path, config)
    return agent.execute()
