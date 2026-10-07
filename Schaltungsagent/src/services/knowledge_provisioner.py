"""Knowledge provisioning: copies curated knowledge files into project workspaces."""
from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeReceipt:
    version: str
    files: dict[str, str]  # relative_path -> sha256


class KnowledgeProvisioner:
    """Copies versioned knowledge files (AGENTS.md, skills, board facts) into a workspace."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._source_root = Path(__file__).resolve().parents[1] / "knowledge"
        self._skills_dir_name = settings.opencode.skills_dir

    def provision(
        self,
        workspace: str,
        board_id: str | None = None,
    ) -> KnowledgeReceipt:
        """Write knowledge files into workspace. Idempotent: second run produces same hashes."""
        if not self._settings.knowledge.enabled:
            logger.info("Knowledge provisioning disabled; skipping")
            return KnowledgeReceipt(version="0", files={})

        if not self._source_root.is_dir():
            logger.warning("Knowledge source directory not found: %s", self._source_root)
            return KnowledgeReceipt(version="0", files={})

        ws = Path(workspace)
        ws.mkdir(parents=True, exist_ok=True)

        files_written: dict[str, str] = {}

        # 1. AGENTS.md from template
        agents_tpl = self._source_root / "AGENTS.md.tpl"
        if agents_tpl.is_file():
            self._render_agents_md(agents_tpl, ws, board_id)
            files_written["AGENTS.md"] = self._sha256(ws / "AGENTS.md")

        # 2. Skills directory
        skills_src = self._source_root / "skills"
        if skills_src.is_dir():
            skills_dst = ws / self._skills_dir_name
            self._copy_tree(skills_src, skills_dst)
            for f in skills_dst.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(ws)
                    files_written[str(rel)] = self._sha256(f)

        # 3. Board facts
        board_id = board_id or self._settings.synthesis.default_fpga
        board_src = self._source_root / "boards" / f"{board_id}.yaml"
        if board_src.is_file():
            board_dst = ws / "knowledge" / "board.yaml"
            board_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(board_src, board_dst)
            files_written["knowledge/board.yaml"] = self._sha256(board_dst)
        else:
            logger.info("No board facts for %s; skipping", board_id)

        # 4. Version file
        version = self._read_version()
        version_path = ws / "knowledge" / "VERSION"
        version_path.parent.mkdir(parents=True, exist_ok=True)
        version_path.write_text(version, encoding="utf-8")
        files_written["knowledge/VERSION"] = self._sha256(version_path)

        logger.info("Knowledge provisioned: %d files, version=%s", len(files_written), version)
        return KnowledgeReceipt(version=version, files=files_written)

    def _render_agents_md(self, template: Path, workspace: Path, board_id: str | None) -> None:
        content = template.read_text(encoding="utf-8")
        skills_list = self._collect_skill_ids()
        skills_dir = self._skills_dir_name
        content = content.replace("{{skills_list}}", "\n".join(f"- `{sid}`" for sid in skills_list))
        content = content.replace("{{skills_dir}}", skills_dir)
        content = content.replace("{{board_id}}", board_id or "unknown")
        (workspace / "AGENTS.md").write_text(content, encoding="utf-8")

    def _collect_skill_ids(self) -> list[str]:
        skills_src = self._source_root / "skills"
        if not skills_src.is_dir():
            return []
        ids = [d.name for d in skills_src.iterdir() if d.is_dir()]
        ids.sort()
        return ids

    def _copy_tree(self, src: Path, dst: Path) -> None:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    def _read_version(self) -> str:
        version_file = self._source_root / "VERSION"
        if version_file.is_file():
            return version_file.read_text(encoding="utf-8").strip()
        return "1"

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()