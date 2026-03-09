"""
Tests for configuration module.
"""

import pytest
from pathlib import Path

from core.config import Config, get_config, reset_config


class TestConfig:
    """Tests for Config class."""

    def test_default_config(self):
        """Test that default config is created correctly."""
        config = Config()

        assert config.project.autodev_dir == ".autodev"
        assert config.project.feature_list_file == "feature_list.json"
        assert config.execution.max_iterations == 100
        assert config.git.auto_commit is True

    def test_config_from_yaml(self, tmp_path: Path):
        """Test loading config from YAML file."""
        yaml_content = """
project:
  autodev_dir: ".autodev_custom"
execution:
  max_iterations: 50
"""
        config_file = tmp_path / "settings.yaml"
        config_file.write_text(yaml_content)

        config = Config.from_yaml(config_file)

        assert config.project.autodev_dir == ".autodev_custom"
        assert config.execution.max_iterations == 50

    def test_config_from_nonexistent_yaml(self, tmp_path: Path):
        """Test loading config from nonexistent file returns defaults."""
        config = Config.from_yaml(tmp_path / "nonexistent.yaml")
        assert config.project.autodev_dir == ".autodev"

    def test_get_autodev_path(self, tmp_path: Path):
        """Test getting .autodev path."""
        config = Config()
        result = config.get_autodev_path(tmp_path)

        assert result == tmp_path / ".autodev"

    def test_get_feature_list_path(self, tmp_path: Path):
        """Test getting feature list path."""
        config = Config()
        result = config.get_feature_list_path(tmp_path)

        assert result == tmp_path / ".autodev" / "feature_list.json"

    def test_get_progress_path(self, tmp_path: Path):
        """Test getting progress file path."""
        config = Config()
        result = config.get_progress_path(tmp_path)

        assert result == tmp_path / ".autodev" / "progress.md"

    def test_get_init_script_path(self, tmp_path: Path):
        """Test getting init script path."""
        config = Config()
        result = config.get_init_script_path(tmp_path)

        assert result == tmp_path / "init.sh"


class TestGetConfig:
    """Tests for get_config function."""

    def teardown_method(self):
        """Reset config after each test."""
        reset_config()

    def test_get_config_returns_singleton(self):
        """Test that get_config returns the same instance."""
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_reset_config(self):
        """Test that reset_config clears the singleton."""
        config1 = get_config()
        reset_config()
        config2 = get_config()

        # They should be equal but not the same instance
        assert config1 == config2
        assert config1 is not config2
