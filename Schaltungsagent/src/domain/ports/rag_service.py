from abc import ABC, abstractmethod
from ..models import KnowledgeBundle


class RAGService(ABC):
    @abstractmethod
    def retrieve_knowledge(
        self,
        request: str,
        domain: str = "vhdl",
    ) -> KnowledgeBundle:
        ...
