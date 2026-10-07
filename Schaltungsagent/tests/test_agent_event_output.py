from src.agents.hdl import HDLAgent
from src.domain.event_bus import EventBus


def test_agent_events_include_agent_name_and_opencode_output():
    event_bus = EventBus()
    agent = HDLAgent(
        llm_service=None,
        opencode_service=None,
        filesystem_service=None,
        event_publisher=event_bus,
    )

    agent.emit_event("OPENCODE_COMPLETED", {
        "task_id": "task-1",
        "stdout": "changed src/counter.vhd",
        "stderr": "",
    })

    event = event_bus.get_events()[0]
    assert event.payload["agent"] == "HDLAgent"
    assert event.payload["stdout"] == "changed src/counter.vhd"
