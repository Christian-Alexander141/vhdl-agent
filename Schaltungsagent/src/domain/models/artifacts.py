from pydantic import BaseModel, Field


class FileArtifact(BaseModel):
    name: str = ""
    content: str = ""
    path: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ArtifactBundle(BaseModel):
    files: list[FileArtifact] = Field(default_factory=list)
    status: str = "generated"
    metadata: dict = Field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
