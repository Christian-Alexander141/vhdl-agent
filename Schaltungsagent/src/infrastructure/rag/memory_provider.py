import uuid
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_MEMORY_DIR = Path(__file__).resolve().parents[3] / "memory"


class MemoryProvider:
    def __init__(self, memory_dir: str | Path | None = None):
        self._memory_dir = Path(memory_dir) if memory_dir else DEFAULT_MEMORY_DIR

    def create_session(self, chat_id: str | None = None) -> dict:
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        resolved_id = chat_id or (
            f"chat-{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{uuid.uuid4().hex[:8]}"
        )
        chat_dir = self._memory_dir / resolved_id
        chat_dir.mkdir(parents=True, exist_ok=True)
        soul_path = chat_dir / "soul.md"
        if not soul_path.exists():
            soul_path.write_text(
                f"# Soul Memory\n\nChat-ID: {resolved_id}\n\n",
                encoding="utf-8",
            )
        return {
            "chat_id": resolved_id,
            "memory_dir": str(self._memory_dir),
            "memory_file": str(soul_path),
        }

    def append_exchange(
        self,
        chat_id: str,
        user_message: str,
        assistant_message: str,
    ) -> Path:
        session = self.create_session(chat_id=chat_id)
        soul_path = Path(session["memory_file"])
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        entry = f"\n## {timestamp}\n\n**Assistant:** {assistant_message.strip()}\n"
        with soul_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return soul_path

    def read_memory(self, chat_id: str) -> str:
        session = self.create_session(chat_id=chat_id)
        memory_file = Path(session["memory_file"])
        if memory_file.exists():
            return memory_file.read_text(encoding="utf-8")
        return ""
