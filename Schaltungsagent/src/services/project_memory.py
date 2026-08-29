import os
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.domain.ports import FileSystemService
from src.domain.exceptions import WorkspaceError

logger = logging.getLogger(__name__)

MEMORY_FILENAME = "memory.md"


class ProjectMemoryService:
    """Verwaltet das projektbezogene Gedächtnis als Markdown-Datei (memory.md).

    Jedes Projekt führt seine eigene memory.md, in der der Chatverlauf und
    projektspezifische Notizen gesammelt werden. So können Rückfragen zu einem
    Projekt mit dem nötigen Kontext beantwortet werden.
    """

    def __init__(self, filesystem_service: FileSystemService):
        self._fs = filesystem_service

    def memory_path(self, workspace: str) -> str:
        return os.path.join(workspace, MEMORY_FILENAME)

    def exists(self, workspace: str) -> bool:
        return self._fs.file_exists(self.memory_path(workspace))

    def load(self, workspace: str) -> str:
        """Lädt den Inhalt der memory.md (leerer String, falls nicht vorhanden)."""
        path = self.memory_path(workspace)
        if not self._fs.file_exists(path):
            return ""
        try:
            return self._fs.read_file(path)
        except Exception as e:
            logger.warning("Failed to load project memory %s: %s", path, e)
            return ""

    def load_entries(self, workspace: str, limit: int = 0) -> list[dict]:
        """Parst die memory.md und liefert die Verlaufseinträge als Liste."""
        content = self.load(workspace)
        entries: list[dict] = []
        current: dict | None = None
        for line in content.splitlines():
            if line.startswith("### "):
                if current:
                    entries.append(current)
                stamp = line[4:].split(" — ", 1)
                current = {"role": "", "content": [], "timestamp": stamp[0].strip()}
                if len(stamp) > 1:
                    label = stamp[1].strip().lower()
                    current["role"] = "assistant" if "assist" in label else "user"
            elif current is not None:
                current["content"].append(line)
        if current:
            entries.append(current)
        for entry in entries:
            entry["content"] = "\n".join(entry["content"]).strip()
        if limit and limit > 0:
            entries = entries[-limit:]
        return entries

    def append(self, workspace: str, role: str, content: str) -> str:
        """Fügt einen Verlaufseintrag zur memory.md hinzu und erzeugt sie bei Bedarf."""
        path = self.memory_path(workspace)
        role_label = "Assistent" if role == "assistant" else "Benutzer"
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = f"\n### {timestamp} — {role_label}\n{content.strip()}\n"
        try:
            if not self._fs.file_exists(path):
                self._fs.write_file(path, self._header(workspace, Path(workspace).name))
            existing = self._fs.read_file(path)
            self._fs.write_file(path, existing.rstrip() + "\n" + entry.lstrip("\n"))
            logger.info("Project memory updated: %s", path)
            return path
        except Exception as e:
            logger.warning("Failed to append project memory %s: %s", path, e)
            raise WorkspaceError(f"Failed to update project memory: {e}") from e

    def update_header(self, workspace: str, **fields) -> None:
        """Aktualisiert die Projekt-Infos im Kopf der memory.md."""
        path = self.memory_path(workspace)
        if not self._fs.file_exists(path):
            self._fs.write_file(path, self._header(workspace, Path(workspace).name))
        content = self._fs.read_file(path)
        for key, value in fields.items():
            pattern = f"- **{key}**: "
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if line.startswith(pattern):
                    lines[i] = f"{pattern}{value}"
                    break
            else:
                lines.insert(2, f"{pattern}{value}")
            content = "\n".join(lines)
        self._fs.write_file(path, content)

    def _header(self, workspace: str, name: str) -> str:
        return (
            f"# Gedächtnis: {name}\n\n"
            "> Automatisch geführte Projekt-Notizen für Kontext bei Rückfragen.\n\n"
            "## Projekt\n"
            f"- **Name**: {name}\n"
            f"- **Workspace**: {workspace}\n\n"
            "## Verlauf\n"
        )
