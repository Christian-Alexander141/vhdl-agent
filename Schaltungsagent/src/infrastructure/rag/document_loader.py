from pathlib import Path
from typing import Any

from langchain_core.documents import Document

SUPPORTED_TEXT_SUFFIXES = {
    ".txt", ".md", ".mdx", ".json", ".csv", ".html", ".xml",
    ".yml", ".yaml", ".log", ".vhd", ".vhdl",
}
SUPPORTED_PDF_SUFFIXES = {".pdf"}


class DocumentLoader:
    def load(self, data_dir: str | Path) -> list[Document]:
        source_dir = Path(data_dir)
        if not source_dir.exists():
            return []
        documents = []
        for file_path in sorted(source_dir.rglob("*")):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix in SUPPORTED_TEXT_SUFFIXES:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
            elif suffix in SUPPORTED_PDF_SUFFIXES:
                try:
                    content = self._extract_pdf_text(file_path)
                except Exception:
                    continue
            else:
                continue
            if content.strip():
                documents.append(
                    Document(
                        page_content=content,
                        metadata={"source": str(file_path.relative_to(source_dir))},
                    )
                )
        return documents

    @staticmethod
    def _extract_pdf_text(file_path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        reader = PdfReader(str(file_path))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n\n".join(parts)
