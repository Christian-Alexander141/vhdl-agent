from src.domain.models import (
    KnowledgeBundle, CodingRule, ReferenceDesign, DocumentRef, TemplateMetadata,
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
        "arty_running_light": [
            "arty", "s7", "running light", "lauflicht", "led running",
            "led lauflicht", "arty s7", "arty s7-50", "spartan-7",
            "xc7s50", "clock divider", "taktteiler",
        ],
    }

    # Strukturierte Metadaten für jedes Template.
    # Insgesamt fließen diese in die qualifizierte Auswahl und sichere Injektion.
    TEMPLATE_REGISTRY: dict[str, TemplateMetadata] = {
        "counter": TemplateMetadata(
            template_id="counter",
            purpose="N-Bit Zaehler mit Synchron-Reset und Enable",
            interfaces=["CLK", "RESET", "ENABLE", "COUNT"],
            clock_hz=100_000_000,
            reset_type="asynchronous",
            fpga_family="",
            board="",
            vhdl_version="2008",
            verified=True,
            synthesized=True,
            hardware_tested=False,
            keywords=["counter", "zaehler", "zähler", "count", "zählen", "zaehlen",
                       "n-bit", "enable", "synchron"],
        ),
        "hamming": TemplateMetadata(
            template_id="hamming",
            purpose="Hamming(7,4) Fehlerkorrektur-Decoder mit Erkennung/Korrektur",
            interfaces=["CLK", "RESET", "DATA_IN", "DATA_OUT", "ERROR_DETECT", "ERROR_CORRECT"],
            clock_hz=100_000_000,
            reset_type="asynchronous",
            fpga_family="",
            board="",
            vhdl_version="2008",
            verified=True,
            synthesized=True,
            hardware_tested=False,
            keywords=["hamming", "fehlerkorrektur", "ecc", "error correction",
                       "decoder", "dekoder", "7,4", "syndrom"],
        ),
        "arty_running_light": TemplateMetadata(
            template_id="arty_running_light",
            purpose="LED-Lauflicht fuer Arty S7-50 mit Clock-Divider",
            interfaces=["CLK", "RESET", "LED"],
            clock_hz=100_000_000,
            reset_type="asynchronous",
            fpga_family="xilinx_spartan7",
            board="arty_s7_50",
            vhdl_version="2008",
            verified=True,
            synthesized=True,
            hardware_tested=True,
            keywords=["arty", "s7", "running light", "lauflicht", "led running",
                       "led lauflicht", "arty s7", "arty s7-50", "spartan-7",
                       "xc7s50", "clock divider", "taktteiler", "led"],
        ),
    }

    @classmethod
    def get_template_metadata(cls, template_name: str) -> TemplateMetadata | None:
        return cls.TEMPLATE_REGISTRY.get(template_name)

    @classmethod
    def get_coding_rules(cls) -> list[CodingRule]:
        return [
            CodingRule(
                category="naming",
                rule="Signale und Variablen in Grossbuchstaben (z.B. CLK, RESET, DATA_IN)",
                severity="warning",
            ),
            CodingRule(
                category="structure",
                rule="Jede Entity benoetigt eine zugehoerige Architecture",
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
