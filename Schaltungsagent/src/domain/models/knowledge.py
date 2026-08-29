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


class TemplateMetadata(BaseModel):
    """Metadaten eines Templates für qualifizierte Auswahl und sichere Injektion."""
    template_id: str = ""
    purpose: str = ""
    interfaces: list[str] = Field(default_factory=list)
    clock_hz: int = 0
    reset_type: str = ""  # "synchronous" | "asynchronous" | "none"
    fpga_family: str = ""  # "xilinx_spartan7" | "gatemate" | ""
    board: str = ""  # "arty_s7_50" | "gatemate_a1" | ""
    vhdl_version: str = "2008"
    verified: bool = False
    synthesized: bool = False
    hardware_tested: bool = False
    keywords: list[str] = Field(default_factory=list)
    score: float = 0.0
    status: str = "none"  # "none" | "matched" | "injected" | "rejected" | "unsuitable"


class KnowledgeBundle(BaseModel):
    coding_rules: list[CodingRule] = Field(default_factory=list)
    reference_designs: list[ReferenceDesign] = Field(default_factory=list)
    examples: list[ReferenceDesign] = Field(default_factory=list)
    standards: list[DocumentRef] = Field(default_factory=list)
    documentation: list[DocumentRef] = Field(default_factory=list)
    raw_context: list[str] = Field(default_factory=list)

    # Template-Matching-Felder (strukturiert)
    matched_template: str | None = None
    template_status: str = "none"  # "none" | "matched" | "injected" | "rejected" | "unsuitable"
    template_score: float = 0.0
    template_metadata: TemplateMetadata | None = None

    def is_empty(self) -> bool:
        return not any([
            self.coding_rules, self.reference_designs, self.examples,
            self.standards, self.documentation, self.raw_context,
        ])

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
