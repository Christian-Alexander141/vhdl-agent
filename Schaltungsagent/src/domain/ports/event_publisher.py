from abc import ABC, abstractmethod
from ..models import Event, EventType


class EventPublisher(ABC):
    @abstractmethod
    def publish(self, event: Event) -> None:
        ...

    @abstractmethod
    def publish_event(
        self,
        event_type: EventType,
        task_id: str = "",
        payload: dict | None = None,
    ) -> Event:
        ...
