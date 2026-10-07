from abc import ABC, abstractmethod
from ..models import ArtifactBundle


class ArtifactGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        request: str,
        analysis: str,
        domain: str = "vhdl",
    ) -> ArtifactBundle:
        ...
