"""
Tests for LLM client and tool executor.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from core.config import Config
from core.llm_client import LLMClient, get_tool_definitions
from core.tool_executor import ToolExecutor


class TestLLMClient:
    """Tests for LLM client."""

    def test_get_tool_definitions(self):
        """Test that tool definitions are returned correctly."""
        tools = get_tool_definitions()

        assert len(tools) == 6
        tool_names = [t["name"] for t in tools]
        assert "bash" in tool_names
        assert "read" in tool_names
        assert "write" in tool_names
        assert "edit" in tool_names
        assert "glob" in tool_names
        assert "grep" in tool_names

    def test_llm_client_initialization(self):
        """Test LLM client initialization."""
        config = Config()
        client = LLMClient(config)

        assert client.config == config
        assert client._client is None  # Lazy initialization


class TestToolExecutor:
    """Tests for tool executor."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a temporary project directory."""
        project = tmp_path / "test-project"
        project.mkdir()
        return project

    @pytest.fixture
    def executor(self, project_path: Path) -> ToolExecutor:
        """Create a tool executor."""
        return ToolExecutor(project_path)

    def test_tool_bash_echo(self, executor: ToolExecutor):
        """Test bash echo command."""
        result = executor.execute("bash", {"command": "echo 'hello'"})
        assert "hello" in result

    def test_tool_bash_pwd(self, executor: ToolExecutor, project_path: Path):
        """Test bash pwd command."""
        result = executor.execute("bash", {"command": "pwd"})
        assert str(project_path) in result

    def test_tool_write_and_read(self, executor: ToolExecutor, project_path: Path):
        """Test write and read tools."""
        # Write a file
        file_path = str(project_path / "test.txt")
        write_result = executor.execute("write", {
            "file_path": file_path,
            "content": "Hello, World!"
        })
        assert "Successfully wrote" in write_result

        # Read the file
        read_result = executor.execute("read", {"file_path": file_path})
        assert "Hello, World!" in read_result

    def test_tool_read_nonexistent_file(self, executor: ToolExecutor):
        """Test reading a nonexistent file."""
        result = executor.execute("read", {"file_path": "/nonexistent/file.txt"})
        assert "Error" in result

    def test_tool_edit(self, executor: ToolExecutor, project_path: Path):
        """Test edit tool."""
        # Create a file first
        file_path = str(project_path / "edit_test.txt")
        executor.execute("write", {
            "file_path": file_path,
            "content": "Hello World\nHello World"
        })

        # Edit it
        edit_result = executor.execute("edit", {
            "file_path": file_path,
            "old_string": "Hello World",
            "new_string": "Goodbye World",
            "replace_all": False
        })
        assert "Successfully replaced" in edit_result

        # Verify content
        read_result = executor.execute("read", {"file_path": file_path})
        assert "Goodbye World" in read_result
        assert "Hello World" in read_result  # Second occurrence unchanged

    def test_tool_edit_replace_all(self, executor: ToolExecutor, project_path: Path):
        """Test edit tool with replace_all."""
        # Create a file
        file_path = str(project_path / "edit_all_test.txt")
        executor.execute("write", {
            "file_path": file_path,
            "content": "foo bar foo bar foo"
        })

        # Edit with replace_all
        edit_result = executor.execute("edit", {
            "file_path": file_path,
            "old_string": "foo",
            "new_string": "baz",
            "replace_all": True
        })
        assert "3 occurrence" in edit_result

        # Verify all replaced
        read_result = executor.execute("read", {"file_path": file_path})
        assert "foo" not in read_result
        assert read_result.count("baz") == 3

    def test_tool_glob(self, executor: ToolExecutor, project_path: Path):
        """Test glob tool."""
        # Create some files
        (project_path / "test.py").touch()
        (project_path / "test.txt").touch()
        (project_path / "src").mkdir()
        (project_path / "src" / "main.py").touch()

        # Find Python files
        result = executor.execute("glob", {"pattern": "**/*.py"})
        assert "test.py" in result
        assert "main.py" in result
        assert "test.txt" not in result

    def test_tool_grep(self, executor: ToolExecutor, project_path: Path):
        """Test grep tool."""
        # Create some files
        (project_path / "file1.txt").write_text("hello world\nfoo bar")
        (project_path / "file2.txt").write_text("hello universe\nbaz qux")

        # Search for "hello"
        result = executor.execute("grep", {
            "pattern": "hello",
            "output_mode": "content"
        })
        assert "hello" in result

    def test_tool_unknown(self, executor: ToolExecutor):
        """Test unknown tool."""
        result = executor.execute("unknown_tool", {})
        assert "Error" in result
        assert "Unknown tool" in result

    def test_tool_bash_dangerous_blocked(self, executor: ToolExecutor):
        """Test that dangerous commands are blocked."""
        result = executor.execute("bash", {"command": "sudo rm -rf /"})
        assert "Dangerous command blocked" in result


class TestToolExecutorIntegration:
    """Integration tests for tool executor."""

    @pytest.fixture
    def project_path(self, tmp_path: Path) -> Path:
        """Create a temporary project directory with some structure."""
        project = tmp_path / "integration-project"
        project.mkdir()

        # Create some structure
        (project / "src").mkdir()
        (project / "src" / "__init__.py").write_text("")
        (project / "src" / "main.py").write_text("""
def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
""")
        (project / "README.md").write_text("# Test Project\n\nThis is a test.")
        (project / "requirements.txt").write_text("anthropic>=0.40.0")

        return project

    @pytest.fixture
    def executor(self, project_path: Path) -> ToolExecutor:
        """Create a tool executor."""
        return ToolExecutor(project_path)

    def test_full_file_workflow(self, executor: ToolExecutor, project_path: Path):
        """Test a full workflow of reading, editing, and verifying files."""
        # Read existing file
        readme_path = str(project_path / "README.md")
        content = executor.execute("read", {"file_path": readme_path})
        assert "Test Project" in content

        # Edit the file
        result = executor.execute("edit", {
            "file_path": readme_path,
            "old_string": "# Test Project",
            "new_string": "# My Awesome Project"
        })
        assert "Successfully" in result

        # Verify the change
        new_content = executor.execute("read", {"file_path": readme_path})
        assert "My Awesome Project" in new_content
        assert "Test Project" not in new_content

    def test_create_new_file_and_search(self, executor: ToolExecutor, project_path: Path):
        """Test creating a new file and searching for its content."""
        # Create a new file
        new_file = str(project_path / "src" / "utils.py")
        result = executor.execute("write", {
            "file_path": new_file,
            "content": '''
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"
'''
        })
        assert "Successfully" in result

        # Search for the function
        search_result = executor.execute("grep", {
            "pattern": "def greet",
            "path": str(project_path / "src")
        })
        assert "def greet" in search_result
