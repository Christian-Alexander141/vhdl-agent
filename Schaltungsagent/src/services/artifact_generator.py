import re
import logging
from src.domain.ports import ArtifactGenerator
from src.domain.models import KnowledgeBundle, ArtifactBundle, FileArtifact
from src.domains.vhdl.templates import VHDLTemplates

logger = logging.getLogger(__name__)


class VHDLArtifactGenerator(ArtifactGenerator):
    def __init__(self):
        self._templates = VHDLTemplates()

    def generate(
        self,
        request: str,
        analysis: str,
        knowledge: KnowledgeBundle,
        domain: str = "vhdl",
    ) -> ArtifactBundle:
        logger.info("Generating artifacts for request (domain=%s)", domain)
        request_lower = request.lower()

        matched_template = None
        for ctx in knowledge.raw_context:
            if ctx.startswith("matched_template:"):
                matched_template = ctx.split(":", 1)[1].strip()

        if matched_template and matched_template in self._templates.TEMPLATES:
            return self._generate_from_template(matched_template, request)

        return self._generate_fallback(request, analysis)

    def _generate_from_template(
        self, template_name: str, request: str
    ) -> ArtifactBundle:
        files: list[FileArtifact] = []

        if template_name == "counter":
            name = self._extract_entity_name(request, "counter")
            width = self._extract_width(request, 8)

            files.append(FileArtifact(
                name=f"{name}.vhd",
                content=self._templates.render(
                    "counter", "entity", name=name, msb=width - 1, additional_ports=""
                )
                + "\n"
                + self._templates.render(
                    "counter", "architecture", name=name, msb=width - 1
                ),
                path=f"src/{name}.vhd",
                description=f"{name} entity and architecture",
            ))
            files.append(FileArtifact(
                name=f"{name}_tb.vhd",
                content=(
                    self._templates.render("counter", "tb_entity", name=name)
                    + "\n"
                    + self._templates.render(
                        "counter", "tb_architecture", name=name, msb=width - 1
                    )
                ),
                path=f"tests/{name}_tb.vhd",
                description=f"Testbench for {name}",
            ))

        elif template_name == "hamming":
            files.append(FileArtifact(
                name="hamming_decoder.vhd",
                content=self._templates.render("hamming", "decoder"),
                path="src/hamming_decoder.vhd",
                description="Hamming decoder entity and architecture",
            ))
            files.append(FileArtifact(
                name="hamming_decoder_tb.vhd",
                content=self._templates.render("hamming", "testbench"),
                path="tests/hamming_decoder_tb.vhd",
                description="Testbench for hamming decoder",
            ))

        logger.info("Generated %d files from template '%s'", len(files), template_name)
        return ArtifactBundle(files=files, status="generated",
                              metadata={"template": template_name})

    def _generate_fallback(self, request: str, analysis: str) -> ArtifactBundle:
        logger.info("No template matched, generating fallback")
        return ArtifactBundle(
            files=[],
            status="no_match",
            metadata={"request": request, "analysis": analysis},
        )

    @staticmethod
    def _extract_entity_name(request: str, default: str = "counter") -> str:
        request_lower = request.lower()
        for word in request_lower.split():
            if word.isidentifier() and word not in (
                "vhdl", "counter", "a", "an", "the", "bit", "mit", "und", "oder",
            ):
                return word
        match = re.search(r'(?:einen|eine|ein)\s+(\w+)', request_lower)
        if match:
            return match.group(1)
        return default

    @staticmethod
    def _extract_width(request: str, default: int = 8) -> int:
        match = re.search(r'(\d+)\s*(?:bit|bits)', request.lower())
        if match:
            width = int(match.group(1))
            if width > 0:
                return width
        return default
