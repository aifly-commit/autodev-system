"""
Progress file manager for AutoDev.

Handles reading, writing, and parsing of the progress.md file.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from core.config import Config
from core.models import ProgressEntry

logger = logging.getLogger(__name__)


class ProgressManager:
    """
    Manager for the progress.md file.

    The progress file is a markdown log that tracks all agent sessions.
    It enables context recovery across sessions.
    """

    def __init__(self, progress_path: Path, config: Optional[Config] = None):
        self.progress_path = Path(progress_path)
        self.config = config or Config()

    def exists(self) -> bool:
        """Check if progress file exists."""
        return self.progress_path.exists()

    def read(self) -> str:
        """Read the entire progress file."""
        if not self.exists():
            return ""
        return self.progress_path.read_text(encoding="utf-8")

    def write(self, content: str) -> None:
        """Write content to the progress file."""
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        self.progress_path.write_text(content, encoding="utf-8")

    def append(self, entry: ProgressEntry) -> None:
        """Append a progress entry to the file."""
        formatted = self._format_entry(entry)

        existing = self.read()
        if existing:
            content = existing.rstrip("\n") + "\n\n" + formatted
        else:
            content = self._get_header() + formatted

        self.write(content)
        logger.info(f"Appended progress entry for session {entry.session_id}")

    def _get_header(self) -> str:
        """Get the progress file header."""
        return """# AutoDev Progress Log

This file tracks all agent sessions for the project.

---

"""

    def _format_entry(self, entry: ProgressEntry) -> str:
        """Format a progress entry as markdown."""
        lines = [
            f"## Session: {entry.session_id}",
            "",
            f"**Timestamp**: {entry.timestamp.isoformat()}",
            f"**Agent**: {entry.agent_type}",
        ]

        if entry.feature_id:
            lines.append(f"**Feature**: {entry.feature_id}")

        lines.extend([
            "",
            "### Action",
            entry.action if entry.action else "(no action recorded)",
            "",
            "### Result",
            entry.result if entry.result else "(no result recorded)",
            "",
        ])

        if entry.details:
            lines.extend([
                "### Details",
                entry.details,
                "",
            ])

        if entry.next_steps:
            lines.append("### Next Steps")
            for step in entry.next_steps:
                lines.append(f"- {step}")
            lines.append("")

        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def parse_entries(self) -> List[ProgressEntry]:
        """
        Parse all entries from the progress file.

        Returns:
            List of ProgressEntry objects.
        """
        content = self.read()
        if not content:
            return []

        entries = []

        # Split by session headers (## Session: ...)
        session_pattern = r"## Session:\s*(.+?)(?=\n)([\s\S]*?)(?=## Session:|---\s*$|$)"
        matches = re.findall(session_pattern, content)

        for session_id, session_content in matches:
            entry = self._parse_session_block(session_id.strip(), session_content)
            if entry:
                entries.append(entry)

        return entries

    def _parse_session_block(self, session_id: str, block: str) -> Optional[ProgressEntry]:
        """Parse a single session block."""
        try:
            # Extract timestamp
            timestamp_match = re.search(r"\*\*Timestamp\*\*:\s*(.+?)(?:\n|$)", block)
            timestamp_str = timestamp_match.group(1).strip() if timestamp_match else None
            try:
                timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()
            except ValueError:
                timestamp = datetime.now()

            # Extract agent type
            agent_match = re.search(r"\*\*Agent\*\*:\s*(.+?)(?:\n|$)", block)
            agent_type = agent_match.group(1).strip() if agent_match else "unknown"

            # Extract feature ID
            feature_match = re.search(r"\*\*Feature\*\*:\s*(.+?)(?:\n|$)", block)
            feature_id = feature_match.group(1).strip() if feature_match else None

            # Extract action - look for ### Action section
            action_match = re.search(r"### Action\s*\n([\s\S]*?)(?=###|$)", block)
            action = action_match.group(1).strip() if action_match else ""

            # Extract result - look for ### Result section
            result_match = re.search(r"### Result\s*\n([\s\S]*?)(?=###|$)", block)
            result = result_match.group(1).strip() if result_match else ""

            # Extract details
            details_match = re.search(r"### Details\s*\n([\s\S]*?)(?=###|$)", block)
            details = details_match.group(1).strip() if details_match else None

            # Extract next steps
            next_steps = []
            steps_match = re.search(r"### Next Steps\s*\n([\s\S]*?)(?=---|$)", block)
            if steps_match:
                for line in steps_match.group(1).strip().split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        next_steps.append(line[2:])

            return ProgressEntry(
                timestamp=timestamp,
                session_id=session_id,
                agent_type=agent_type,
                feature_id=feature_id,
                action=action,
                result=result,
                details=details,
                next_steps=next_steps,
            )
        except Exception as e:
            logger.warning(f"Failed to parse session block: {e}")
            return None

    def get_last_entry(self) -> Optional[ProgressEntry]:
        """Get the most recent progress entry."""
        entries = self.parse_entries()
        return entries[-1] if entries else None

    def get_entries_for_feature(self, feature_id: str) -> List[ProgressEntry]:
        """Get all entries for a specific feature."""
        entries = self.parse_entries()
        return [e for e in entries if e.feature_id == feature_id]

    def get_entries_since(self, timestamp: datetime) -> List[ProgressEntry]:
        """Get all entries since a specific timestamp."""
        entries = self.parse_entries()
        return [e for e in entries if e.timestamp >= timestamp]

    def get_summary(self, limit: int = 5) -> Dict[str, Any]:
        """Get a summary of recent progress."""
        entries = self.parse_entries()

        # Get recent entries
        recent = entries[-limit:] if entries else []

        # Count by agent type
        agent_counts: Dict[str, int] = {}
        for entry in entries:
            agent_counts[entry.agent_type] = agent_counts.get(entry.agent_type, 0) + 1

        # Count by feature
        feature_counts: Dict[str, int] = {}
        for entry in entries:
            if entry.feature_id:
                feature_counts[entry.feature_id] = feature_counts.get(entry.feature_id, 0) + 1

        return {
            "total_sessions": len(entries),
            "agent_counts": agent_counts,
            "feature_counts": feature_counts,
            "recent_sessions": [
                {
                    "session_id": e.session_id,
                    "timestamp": e.timestamp.isoformat(),
                    "agent": e.agent_type,
                    "feature": e.feature_id,
                    "action": e.action[:100] + "..." if len(e.action) > 100 else e.action,
                }
                for e in recent
            ],
        }

    def create_initial(self) -> None:
        """Create the initial progress file with a header."""
        self.write(self._get_header())
