import logging
from typing import Callable
from .models import Event, EventType
from .ports import EventPublisher

Listener = Callable[[Event], None]

logger = logging.getLogger(__name__)


class EventBus(EventPublisher):
    def __init__(self):
        self._listeners: list[Listener] = []
        self._event_log: list[Event] = []

    def on_event(self, listener: Listener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def publish(self, event: Event) -> None:
        self.emit(event)

    def emit(self, event: Event) -> None:
        self._event_log.append(event)
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Listener failed for event %s", event.event_type)

    def publish_event(
        self,
        event_type: EventType,
        task_id: str = "",
        payload: dict | None = None,
    ) -> Event:
        return self.emit_event(event_type, task_id, payload)

    def emit_event(
        self,
        event_type: EventType,
        task_id: str = "",
        payload: dict | None = None,
    ) -> Event:
        event = Event(
            event_type=event_type,
            task_id=task_id,
            payload=payload or {},
        )
        self.emit(event)
        return event

    def get_events(self, since_index: int = 0) -> list[Event]:
        return self._event_log[since_index:]

    def clear(self) -> None:
        self._event_log.clear()
