"""
Coder Agent for AutoDev system.

The Coder Agent runs in multiple sessions to:
1. Recover context from previous sessions
2. Pick ONE pending feature to work on
3. Implement the feature incrementally
4. Test thoroughly (including E2E)
5. Mark feature as passing only after verification
6. Leave clean state for next session
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from core.agents.base import BaseAgent
from core.config import Config
from core.models import SessionContext, Feature, FeatureList
from core.llm_client import LLMClient, get_tool_definitions
from core.tool_executor import ToolExecutor, create_tool_handler
from core.harness import AutoDevHarness

logger = logging.getLogger(__name__)


CODER_SYSTEM_PROMPT = """You are the Coding Agent for AutoDev. You work in sessions, and each session must make incremental progress on ONE feature.

## Session Start Protocol

1. **Get your bearings**:
   ```bash
   pwd  # Confirm working directory
   ```

2. **Recover context**:
   - Read `.autodev/progress.md` - understand recent work
   - Run `git log --oneline -10` - see recent commits
   - Read `.autodev/feature_list.json` - find next pending feature

3. **Verify environment health**:
   - Run `./init.sh` or equivalent to start dev server
   - Verify basic functionality works
   - If broken, FIX FIRST before implementing new features

## Work Protocol

1. **Pick ONE feature** from feature_list.json where `passes: false`
2. **Implement** the feature incrementally
3. **Test thoroughly**:
   - Write unit tests if applicable
   - Run integration tests
   - For web apps, verify with browser testing or curl
4. **Update feature_list.json** - change `passes: true` ONLY after verification
5. **Update progress.md** with what you did
6. **Git commit** with descriptive message

## Feature List Update Format

When marking a feature as passing, edit the JSON to change only the `passes` field:
```json
{
  "id": "F001",
  "passes": true  // Changed from false
}
```

DO NOT remove or modify test_steps or acceptance_criteria.

## Session End Protocol

1. Update `.autodev/feature_list.json` with feature status
2. Update `.autodev/progress.md` with:
   - What you worked on
   - What was completed
   - Any blockers
   - Next steps
3. Git commit with descriptive message
4. Leave code in clean, working state

## CRITICAL RULES

- Work on ONE feature at a time
- NEVER remove or modify test criteria
- NEVER mark feature as passing without testing
- ALWAYS commit working code
- NEVER start new feature if existing features are broken
- Use the tools (bash, read, write, edit, glob, grep) to do your work
"""


class CoderAgent(BaseAgent):
    """
    Agent responsible for incremental feature implementation.

    This agent runs multiple times throughout a project,
    each time making progress on one feature.
    """

    def __init__(
        self,
        project_path: Path,
        config: Optional[Config] = None,
        session_context: Optional[SessionContext] = None,
    ):
        super().__init__(config, session_context)
        self.project_path = Path(project_path).resolve()
        self.llm_client = LLMClient(config)
        self.tool_executor = ToolExecutor(project_path, config)
        self.harness = AutoDevHarness(project_path, config=config)

    def get_system_prompt(self) -> str:
        """Return the system prompt for the coder agent."""
        return CODER_SYSTEM_PROMPT

    def get_user_prompt(self, context: SessionContext) -> str:
        """Return the user prompt with session context."""
        feature_info = ""
        if context.current_feature:
            feature = context.current_feature
            feature_info = f"""
## Current Feature to Work On

**ID**: {feature.id}
**Description**: {feature.description}
**Priority**: {feature.priority.value}

### Acceptance Criteria
{chr(10).join(f'- {c}' for c in feature.acceptance_criteria)}

### Test Steps
{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(feature.test_steps))}
"""

        return f"""
Begin a new coding session.

{context.to_prompt_context()}

{feature_info}

Please:
1. Verify the environment is healthy (run init.sh if available)
2. Work on the feature identified above
3. Test your implementation thoroughly
4. Update feature_list.json when complete
5. Update progress.md with your work
6. Commit your changes
"""

    def execute(self, *args, **kwargs) -> Any:
        """
        Execute a coding session.

        This calls the LLM with tools and handles the agentic loop.
        """
        if not self.session_context:
            # Recover context if not provided
            self.session_context = self.harness.recover_context()

        logger.info(f"Starting CoderAgent session for {self.project_path}")
        logger.info(f"Current feature: {self.session_context.current_feature.id if self.session_context.current_feature else 'None'}")

        # Get tool definitions
        tools = get_tool_definitions()

        # Create tool handler
        tool_handler = create_tool_handler(self.tool_executor)

        # Get model config
        agent_config = self.config.agents.coder

        # Call LLM with tools
        try:
            result = self.llm_client.create_message_with_tools(
                system_prompt=self.get_system_prompt(),
                user_prompt=self.get_user_prompt(self.session_context),
                tools=tools,
                tool_handler=tool_handler,
                model=agent_config.model,
                max_tokens=agent_config.max_tokens,
                temperature=agent_config.temperature,
                max_tool_calls=150,
            )

            logger.info(f"CoderAgent completed with {result['tool_calls']} tool calls")
            logger.info(f"Token usage: {result['usage']}")

            # Check if feature was completed
            feature_list = self.harness.load_feature_list()
            progress = feature_list.get_progress_summary()

            return {
                "success": True,
                "content": result["content"],
                "tool_calls": result["tool_calls"],
                "usage": result["usage"],
                "features_passing": progress["passing"],
                "features_total": progress["total"],
            }

        except Exception as e:
            logger.error(f"CoderAgent failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }


def run_coder_session(
    project_path: Path,
    config: Optional[Config] = None,
) -> dict:
    """
    Convenience function to run a coder session.

    Args:
        project_path: Path to the project directory.
        config: Optional configuration.

    Returns:
        Result dict with success status.
    """
    agent = CoderAgent(project_path, config)
    return agent.execute()
