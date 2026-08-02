from abc import ABC, abstractmethod
from ..models import KnowledgeBundle, ArtifactBundle


class ArtifactGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        request: str,
        analysis: str,
        knowledge: KnowledgeBundle,
        domain: str = "vhdl",
    ) -> ArtifactBundle:
        ...
