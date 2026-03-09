"""
Configuration management for AutoDev system.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional, Union

import yaml
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    """Project-related configuration."""
    autodev_dir: str = ".autodev"
    feature_list_file: str = "feature_list.json"
    progress_file: str = "progress.md"
    init_script: str = "init.sh"
    test_results_file: str = "test_results.json"


class AgentConfig(BaseModel):
    """Configuration for a single agent type."""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 8192
    temperature: float = 0.3


class AgentsConfig(BaseModel):
    """Configuration for all agent types."""
    initializer: AgentConfig = Field(default_factory=AgentConfig)
    coder: AgentConfig = Field(default_factory=lambda: AgentConfig(
        model="claude-sonnet-4-20250514",
        max_tokens=16384,
        temperature=0.2
    ))
    tester: AgentConfig = Field(default_factory=lambda: AgentConfig(
        temperature=0.1
    ))


class ExecutionConfig(BaseModel):
    """Execution settings."""
    max_iterations: int = 100
    session_timeout_ms: int = 300000
    retry_attempts: int = 3
    retry_delay_ms: int = 1000


class FeatureListConfig(BaseModel):
    """Feature list generation settings."""
    min_features: int = 5
    max_features: int = 500
    categories: List[str] = Field(default_factory=lambda: [
        "core", "ui", "api", "auth", "storage", "testing"
    ])
    priority_levels: List[str] = Field(default_factory=lambda: [
        "critical", "high", "medium", "low"
    ])


class GitConfig(BaseModel):
    """Git operation settings."""
    auto_commit: bool = True
    commit_prefix: str = "[AutoDev]"
    branch_prefix: str = "autodev/"


class TestingConfig(BaseModel):
    """Testing settings."""
    e2e_enabled: bool = True
    browser: str = "chromium"
    headless: bool = True
    screenshot_on_failure: bool = True
    test_timeout_ms: int = 30000


class LoggingConfig(BaseModel):
    """Logging settings."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: str = "autodev.log"


class PathsConfig(BaseModel):
    """Path configuration."""
    templates: str = "templates"
    prompts: str = "templates/prompts"


class Config(BaseModel):
    """Main configuration model."""
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    feature_list: FeatureListConfig = Field(default_factory=FeatureListConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    testing: TestingConfig = Field(default_factory=TestingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        """Load configuration from YAML file."""
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls(**data)

    def get_autodev_path(self, project_path: Path) -> Path:
        """Get the .autodev directory path for a project."""
        return project_path / self.project.autodev_dir

    def get_feature_list_path(self, project_path: Path) -> Path:
        """Get the feature list file path."""
        return self.get_autodev_path(project_path) / self.project.feature_list_file

    def get_progress_path(self, project_path: Path) -> Path:
        """Get the progress file path."""
        return self.get_autodev_path(project_path) / self.project.progress_file

    def get_init_script_path(self, project_path: Path) -> Path:
        """Get the init.sh script path."""
        return project_path / self.project.init_script


# Global config instance
_config: Optional[Config] = None


def get_config(config_path: Optional[str | Path] = None) -> Config:
    """
    Get the global configuration instance.

    Args:
        config_path: Optional path to config file. If not provided,
                     looks for config/settings.yaml relative to this file.

    Returns:
        Config instance.
    """
    global _config

    if _config is not None:
        return _config

    if config_path is None:
        # Look for default config location
        config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    else:
        config_path = Path(config_path)

    _config = Config.from_yaml(config_path)
    return _config


def reset_config() -> None:
    """Reset the global config instance (useful for testing)."""
    global _config
    _config = None
