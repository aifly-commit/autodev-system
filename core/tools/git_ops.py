"""
Git operations wrapper for AutoDev.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from core.config import Config
from core.exceptions import GitError

logger = logging.getLogger(__name__)


class GitOperations:
    """
    Wrapper for git operations.

    Provides safe, structured access to git functionality.
    """

    def __init__(self, repo_path: Path, config: Optional[Config] = None):
        self.repo_path = Path(repo_path).resolve()
        self.config = config or Config()

    def _run_git(
        self,
        *args: str,
        check: bool = True,
        input: Optional[str] = None,
    ) -> subprocess.CompletedProcess:
        """Run a git command."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=check,
                input=input,
            )
            return result
        except subprocess.CalledProcessError as e:
            raise GitError(f"Git command failed: {e.stderr}") from e

    def is_repo(self) -> bool:
        """Check if path is a git repository."""
        git_dir = self.repo_path / ".git"
        return git_dir.exists()

    def init(self) -> None:
        """Initialize a git repository."""
        if not self.is_repo():
            self._run_git("init")
            logger.info(f"Initialized git repository at {self.repo_path}")

    def status(self) -> Dict[str, Any]:
        """Get repository status."""
        result = self._run_git("status", "--porcelain")
        files = []
        for line in result.stdout.strip().split("\n"):
            if line:
                status = line[:2].strip()
                filepath = line[3:]
                files.append({"status": status, "path": filepath})
        return {"files": files, "clean": len(files) == 0}

    def add(self, *files: str) -> None:
        """Stage files for commit."""
        if files:
            self._run_git("add", *files)
        else:
            self._run_git("add", ".")

    def commit(self, message: str) -> str:
        """
        Create a commit.

        Returns:
            Commit hash.
        """
        prefix = self.config.git.commit_prefix
        full_message = f"{prefix} {message}" if prefix else message

        self._run_git("commit", "-m", full_message)

        # Get the commit hash
        result = self._run_git("rev-parse", "HEAD")
        return result.stdout.strip()[:8]

    def log(self, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent commits."""
        result = self._run_git(
            "log",
            f"-{limit}",
            "--pretty=format:%H|%s|%an|%ai",
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("|", 3)
                if len(parts) >= 2:
                    commits.append({
                        "hash": parts[0][:8],
                        "message": parts[1],
                        "author": parts[2] if len(parts) > 2 else "",
                        "date": parts[3] if len(parts) > 3 else "",
                    })
        return commits

    def current_branch(self) -> str:
        """Get current branch name."""
        result = self._run_git("branch", "--show-current")
        return result.stdout.strip() or "main"

    def create_branch(self, name: str) -> None:
        """Create and checkout a new branch."""
        prefix = self.config.git.branch_prefix
        full_name = f"{prefix}{name}" if prefix else name
        self._run_git("checkout", "-b", full_name)

    def checkout(self, branch: str) -> None:
        """Checkout a branch."""
        self._run_git("checkout", branch)

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        status = self.status()
        return not status["clean"]

    def diff(self, staged: bool = False) -> str:
        """Get diff output."""
        args = ["diff"]
        if staged:
            args.append("--staged")
        result = self._run_git(*args)
        return result.stdout

    def get_last_commit_for_file(self, filepath: str) -> Optional[Dict[str, str]]:
        """Get the last commit that modified a file."""
        result = self._run_git(
            "log",
            "-1",
            "--pretty=format:%H|%s|%ai",
            "--",
            filepath,
        )

        line = result.stdout.strip()
        if line:
            parts = line.split("|", 2)
            if len(parts) >= 2:
                return {
                    "hash": parts[0][:8],
                    "message": parts[1],
                    "date": parts[2] if len(parts) > 2 else "",
                }
        return None

    def get_file_at_commit(self, filepath: str, commit_hash: str) -> Optional[str]:
        """Get file contents at a specific commit."""
        try:
            result = self._run_git("show", f"{commit_hash}:{filepath}")
            return result.stdout
        except GitError:
            return None

    def revert_file(self, filepath: str) -> None:
        """Revert a file to the last committed state."""
        self._run_git("checkout", "HEAD", "--", filepath)

    def stash(self, message: Optional[str] = None) -> None:
        """Stash current changes."""
        if message:
            self._run_git("stash", "push", "-m", message)
        else:
            self._run_git("stash")

    def stash_pop(self) -> None:
        """Pop the last stash."""
        self._run_git("stash", "pop")

    def stash_list(self) -> List[Dict[str, str]]:
        """List all stashes."""
        result = self._run_git("stash", "list")

        stashes = []
        for line in result.stdout.strip().split("\n"):
            if line:
                # Format: stash@{0}: On branch: message
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    stashes.append({
                        "ref": parts[0].strip(),
                        "branch": parts[1].replace("On ", "").strip() if len(parts) > 1 else "",
                        "message": parts[2].strip() if len(parts) > 2 else "",
                    })
        return stashes

    def get_changed_files_since(self, commit_hash: str) -> List[str]:
        """Get files changed since a specific commit."""
        result = self._run_git("diff", "--name-only", f"{commit_hash}..HEAD")
        return [f for f in result.stdout.strip().split("\n") if f]

    def auto_commit(self, message: str) -> Optional[str]:
        """
        Auto-commit if there are changes.

        Returns:
            Commit hash if committed, None if no changes.
        """
        if not self.has_changes():
            return None

        self.add()
        return self.commit(message)

    def get_commit_count(self) -> int:
        """Get total number of commits."""
        result = self._run_git("rev-list", "--count", "HEAD")
        try:
            return int(result.stdout.strip())
        except ValueError:
            return 0

    def get_repo_info(self) -> Dict[str, Any]:
        """Get repository information."""
        return {
            "path": str(self.repo_path),
            "is_repo": self.is_repo(),
            "branch": self.current_branch() if self.is_repo() else None,
            "commit_count": self.get_commit_count() if self.is_repo() else 0,
            "has_changes": self.has_changes() if self.is_repo() else False,
        }

    def is_repo(self) -> bool:
        """Check if path is a git repository."""
        try:
            result = self._run_git("rev-parse", "--git-dir", check=False)
            return result.returncode == 0
        except Exception:
            return False

    def log(self, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent commits (alias for the log method)."""
        return self.log_commits(limit)

    def log_commits(self, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent commits."""
        try:
            result = self._run_git(
                "log",
                f"-{limit}",
                "--pretty=format:%H|%s|%an|%ai",
                check=False,
            )

            if result.returncode != 0:
                return []

            commits = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("|", 3)
                    if len(parts) >= 2:
                        commits.append({
                            "hash": parts[0][:8],
                            "message": parts[1],
                            "author": parts[2] if len(parts) > 2 else "",
                            "date": parts[3] if len(parts) > 3 else "",
                        })
            return commits
        except GitError:
            return []
