from pathlib import Path
from typing import Any

from langchain_core.documents import Document

SUPPORTED_TEXT_SUFFIXES = {
    ".txt", ".md", ".mdx", ".json", ".csv", ".html", ".xml",
    ".yml", ".yaml", ".log", ".vhd", ".vhdl",
}


class DocumentLoader:
    def load(self, data_dir: str | Path) -> list[Document]:
        source_dir = Path(data_dir)
        if not source_dir.exists():
            return []
        documents = []
        for file_path in sorted(source_dir.rglob("*")):
            if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_TEXT_SUFFIXES:
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if content.strip():
                    documents.append(
                        Document(
                            page_content=content,
                            metadata={"source": str(file_path.relative_to(source_dir))},
                        )
                    )
            except Exception:
                continue
        return documents
