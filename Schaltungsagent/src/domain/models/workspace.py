from pydantic import BaseModel, Field
from typing import Any


class Workspace(BaseModel):
    id: str = ""
    root: str = ""
    source_files: list[str] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
    test_results: dict = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
