from pydantic import BaseModel, Field


class CodingRule(BaseModel):
    category: str = ""
    rule: str = ""
    severity: str = "info"


class ReferenceDesign(BaseModel):
    name: str = ""
    description: str = ""
    code: str = ""
    language: str = "vhdl"


class DocumentRef(BaseModel):
    title: str = ""
    source: str = ""
    content: str = ""


class KnowledgeBundle(BaseModel):
    coding_rules: list[CodingRule] = Field(default_factory=list)
    reference_designs: list[ReferenceDesign] = Field(default_factory=list)
    examples: list[ReferenceDesign] = Field(default_factory=list)
    standards: list[DocumentRef] = Field(default_factory=list)
    documentation: list[DocumentRef] = Field(default_factory=list)
    raw_context: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not any([
            self.coding_rules, self.reference_designs, self.examples,
            self.standards, self.documentation, self.raw_context,
        ])

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
