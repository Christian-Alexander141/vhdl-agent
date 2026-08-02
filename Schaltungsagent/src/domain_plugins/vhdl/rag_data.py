from src.domain.models import (
    KnowledgeBundle, CodingRule, ReferenceDesign, DocumentRef,
)


class VHDLRAGData:
    DOMAIN = "vhdl"
    KEYWORDS = ["vhdl", "counter", "zaehler", "zähler", "hamming", "fpga", "register"]

    TEMPLATE_MAP: dict[str, list[str]] = {
        "counter": [
            "counter", "zaehler", "zähler", "count", "zählen", "zaehlen",
        ],
        "hamming": [
            "hamming", "fehlerkorrektur", "ecc", "error correction",
            "decoder", "dekoder",
        ],
    }

    @classmethod
    def get_coding_rules(cls) -> list[CodingRule]:
        return [
            CodingRule(
                category="naming",
                rule="Signale und Variablen in Großbuchstaben (z.B. CLK, RESET, DATA_IN)",
                severity="warning",
            ),
            CodingRule(
                category="structure",
                rule="Jede Entity benötigt eine zugehörige Architecture",
                severity="error",
            ),
            CodingRule(
                category="port",
                rule="Clock-Signal immer als ersten Port definieren",
                severity="info",
            ),
            CodingRule(
                category="reset",
                rule="Reset-Signal als zweiten Port definieren, entweder synchronous oder asynchronous",
                severity="info",
            ),
        ]

    @classmethod
    def get_reference_designs(cls) -> list[ReferenceDesign]:
        return [
            ReferenceDesign(
                name="counter",
                description="N-bit counter with synchronous reset and enable",
                language="vhdl",
                code="",
            ),
            ReferenceDesign(
                name="hamming_decoder",
                description="Hamming code error correction decoder (7,4)",
                language="vhdl",
                code="",
            ),
        ]

    @classmethod
    def get_standards(cls) -> list[DocumentRef]:
        return [
            DocumentRef(
                title="IEEE 1076-2019",
                source="IEEE",
                content="VHDL Language Reference Manual",
            ),
            DocumentRef(
                title="IEEE 1164-1993",
                source="IEEE",
                content="Standard Multivalue Logic System for VHDL",
            ),
        ]

    @classmethod
    def get_knowledge(cls, request: str) -> KnowledgeBundle:
        return KnowledgeBundle(
            coding_rules=cls.get_coding_rules(),
            reference_designs=cls.get_reference_designs(),
            standards=cls.get_standards(),
        )
