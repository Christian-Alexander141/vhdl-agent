from abc import ABC, abstractmethod


class FileSystemService(ABC):
    @abstractmethod
    def create_workspace(self, task_id: str, domain: str = "vhdl") -> str:
        ...

    @abstractmethod
    def write_file(self, path: str, content: str) -> str:
        ...

    @abstractmethod
    def read_file(self, path: str) -> str:
        ...

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        ...

    @abstractmethod
    def list_files(self, workspace_path: str, pattern: str = "**/*") -> list[str]:
        ...

    @abstractmethod
    def delete_workspace(self, task_id: str) -> None:
        ...

    @abstractmethod
    def workspace_path(self, task_id: str) -> str:
        ...

    @abstractmethod
    def list_workspaces(self) -> list[str]:
        """Listet die Namen aller vorhandenen Projekt-Workspaces."""
        ...
