from pydantic import BaseModel
from typing import Optional

class TaskRequest(BaseModel):
    user_request: str
    domain: str = "vhdl"

class FileArtifact(BaseModel):
    name: str
    content: str

class ArtifactResult(BaseModel):
    files: list[FileArtifact]
    status: str = "generated"


class OpenCodeInstruction(BaseModel):
    project_path: str
    instruction: str
    max_iterations: int = 5

class OpenCodeResult(BaseModel):
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0

class TaskResult(BaseModel):
    task_id: str
    status: str
    files: list[str]
    opencode_result: Optional[OpenCodeResult] = None
    history: list[str]
