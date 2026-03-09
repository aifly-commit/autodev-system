"""
LLM client wrapper for AutoDev system.

Provides a unified interface for calling LLM APIs.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Union

from core.config import Config
from core.exceptions import LLMError

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Wrapper for LLM API calls.

    Supports Anthropic Claude API.
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._client = None

    @property
    def client(self):
        """Lazy initialization of the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if not api_key:
                    raise LLMError("ANTHROPIC_API_KEY environment variable not set")
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise LLMError(
                    "anthropic package not installed. "
                    "Run: pip install anthropic"
                )
        return self._client

    def create_message(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Create a message using the LLM.

        Args:
            system_prompt: System prompt for the conversation.
            user_prompt: User message content.
            model: Model to use (overrides config).
            max_tokens: Max tokens (overrides config).
            temperature: Temperature (overrides config).
            tools: List of tools available to the model.

        Returns:
            Response dict with content and usage info.
        """
        model = model or self.config.agents.coder.model
        max_tokens = max_tokens or self.config.agents.coder.max_tokens
        temperature = temperature if temperature is not None else self.config.agents.coder.temperature

        try:
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }

            if tools:
                kwargs["tools"] = tools

            response = self.client.messages.create(**kwargs)

            return {
                "content": response.content,
                "model": response.model,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                "stop_reason": response.stop_reason,
            }

        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            raise LLMError(f"LLM API call failed: {e}") from e

    def create_message_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: List[Dict[str, Any]],
        tool_handler: callable,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        max_tool_calls: int = 50,
    ) -> Dict[str, Any]:
        """
        Create a message with tool support and automatic tool handling.

        This implements the agentic loop:
        1. Send message to LLM
        2. If LLM requests tool use, execute tool and send result back
        3. Repeat until LLM returns text response

        Args:
            system_prompt: System prompt.
            user_prompt: Initial user message.
            tools: List of tool definitions.
            tool_handler: Function to handle tool calls.
            model: Model to use.
            max_tokens: Max tokens.
            temperature: Temperature.
            max_tool_calls: Maximum tool calls before stopping.

        Returns:
            Final response dict.
        """
        model = model or self.config.agents.coder.model
        max_tokens = max_tokens or self.config.agents.coder.max_tokens
        temperature = temperature if temperature is not None else self.config.agents.coder.temperature

        messages = [{"role": "user", "content": user_prompt}]
        tool_call_count = 0

        while tool_call_count < max_tool_calls:
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                )

                # Check stop reason
                if response.stop_reason == "end_turn":
                    # Extract text response
                    text_content = ""
                    for block in response.content:
                        if hasattr(block, "text"):
                            text_content += block.text

                    return {
                        "content": text_content,
                        "model": response.model,
                        "usage": {
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                        },
                        "tool_calls": tool_call_count,
                    }

                # Handle tool use
                tool_results = []
                assistant_content = []

                for block in response.content:
                    assistant_content.append(block)

                    if block.type == "tool_use":
                        tool_call_count += 1
                        logger.info(f"Tool call: {block.name}")

                        try:
                            result = tool_handler(block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            })
                        except Exception as e:
                            logger.error(f"Tool {block.name} failed: {e}")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Error: {str(e)}",
                                "is_error": True,
                            })

                # Add assistant message with tool use
                messages.append({"role": "assistant", "content": assistant_content})

                # Add tool results
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})

            except Exception as e:
                logger.error(f"LLM API call failed: {e}")
                raise LLMError(f"LLM API call failed: {e}") from e

        raise LLMError(f"Exceeded maximum tool calls ({max_tool_calls})")


def get_tool_definitions() -> List[Dict[str, Any]]:
    """
    Get standard tool definitions for the coding agent.

    These tools allow the agent to:
    - Read files
    - Write files
    - Execute bash commands
    - Search files
    """
    return [
        {
            "name": "bash",
            "description": "Execute a bash command. Use for git operations, running tests, installing dependencies, etc.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Optional timeout in milliseconds (default 120000)",
                        "default": 120000
                    }
                },
                "required": ["command"]
            }
        },
        {
            "name": "read",
            "description": "Read a file from the filesystem. Returns the file contents.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to read"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read"
                    }
                },
                "required": ["file_path"]
            }
        },
        {
            "name": "write",
            "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file"
                    }
                },
                "required": ["file_path", "content"]
            }
        },
        {
            "name": "edit",
            "description": "Perform an exact string replacement in a file.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to edit"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The text to replace"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The text to replace it with"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences",
                        "default": False
                    }
                },
                "required": ["file_path", "old_string", "new_string"]
            }
        },
        {
            "name": "glob",
            "description": "Find files matching a glob pattern.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The glob pattern to match (e.g., '**/*.py')"
                    },
                    "path": {
                        "type": "string",
                        "description": "The directory to search in (default: current directory)"
                    }
                },
                "required": ["pattern"]
            }
        },
        {
            "name": "grep",
            "description": "Search for a pattern in file contents.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The pattern to search for"
                    },
                    "path": {
                        "type": "string",
                        "description": "The file or directory to search in"
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["content", "files_with_matches", "count"],
                        "description": "Output mode",
                        "default": "content"
                    }
                },
                "required": ["pattern"]
            }
        }
    ]
