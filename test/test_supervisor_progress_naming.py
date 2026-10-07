import asyncio
import time

from src.agents.supervisor import SupervisorAgent
from src.agents.architecture import ArchitectureAgent
from src.domain.agents import AgentResult, AgentStatus, AgentTask
from src.domain.event_bus import EventBus
from src.domain.models import DesignStage, DesignState, ModuleInfo
from src.services.artifact_generator import VHDLArtifactGenerator
from src.services.project_namer import slugify

TEST_LOOP = asyncio.new_event_loop()


class MemoryFileSystem:
    def __init__(self):
        self.files = {}

    def workspace_path(self, project_id):
        return f"/projects/{project_id}"

    def file_exists(self, path):
        return path in self.files

    def read_file(self, path):
        return self.files[path]

    def write_file(self, path, content):
        self.files[path] = content


def make_supervisor(filesystem=None, config=None):
    return SupervisorAgent(
        llm_service=None,
        filesystem_service=filesystem or MemoryFileSystem(),
        event_publisher=EventBus(),
        project_memory=None,
        config=config,
    )


def run_async(coroutine):
    asyncio.set_event_loop(TEST_LOOP)
    return TEST_LOOP.run_until_complete(coroutine)


def test_project_and_entity_names_describe_the_hardware():
    request = "Optimierter Prompt für den 4 Bit Addierer"

    assert slugify(request) == "4-bit-addierer"
    assert slugify("Aufgabe 1: Erstelle einen synthetisierbaren 4-Bit Addierer") == "4-bit-addierer"
    assert slugify("Projektname: 4-bit-addierer") == "4-bit-addierer"
    assert VHDLArtifactGenerator._extract_entity_name(
        "Entwickle einen synthetisierbaren 4-Bit Addierer"
    ) == "adder"

    architecture_agent = ArchitectureAgent(None)
    architecture = architecture_agent._parse_architecture_yaml(
        "modules:\n  - name: synthetisierbaren\n    type: combinational\n",
        request,
    )
    assert architecture["modules"][0].name == "adder"


def test_completed_project_restarts_only_for_actionable_feedback():
    filesystem = MemoryFileSystem()
    supervisor = make_supervisor(filesystem)
    state = DesignState(current_stage=DesignStage.COMPLETED)
    state.metadata["last_completed_request"] = "Build an adder"
    state_path = "/projects/adder/design_state.yaml"
    filesystem.files[state_path] = state.to_yaml()

    neutral = run_async(supervisor._load_or_create_design_state(
        "adder", {"request": "Hardware-Test bestanden, danke."}
    ))
    revision = run_async(supervisor._load_or_create_design_state(
        "adder", {"request": "Der Ausgang ist falsch, bitte korrigieren."}
    ))

    assert neutral.current_stage == DesignStage.COMPLETED
    assert revision.current_stage == DesignStage.IMPLEMENTING
    assert SupervisorAgent._is_hardware_revision_request("Die LED leuchtet nicht.")
    assert SupervisorAgent._is_hardware_revision_request(
        "Statt LED 3 soll LED 4 blinken."
    )


def test_supervisor_emits_heartbeat_during_blocking_stage_work():
    supervisor = make_supervisor(config={"heartbeat_interval_seconds": 0.01})
    supervisor._current_task = AgentTask(
        id="task-1", type="supervise", project_id="project-1"
    )

    async def blocking_analysis():
        time.sleep(0.15)
        return AgentResult(task_id="task-1", status=AgentStatus.COMPLETED)

    supervisor._run_analysis = blocking_analysis
    run_async(supervisor._execute_stage(DesignStage.ANALYZING))

    event_types = [event.event_type.value for event in supervisor.event_bus.get_events()]
    assert "AGENT_HEARTBEAT" in event_types


def test_successful_flash_completes_without_hardware_test_stage():
    filesystem = MemoryFileSystem()
    supervisor = make_supervisor(filesystem)
    supervisor._current_task = AgentTask(
        id="task-1",
        type="supervise",
        project_id="project-1",
        inputs={"request": "Build an adder"},
    )
    supervisor._design_state = DesignState(current_stage=DesignStage.FPGA_PROGRAMMING)
    executed_stages = []

    async def successful_stage(stage):
        executed_stages.append(stage)
        return AgentResult(task_id="task-1", status=AgentStatus.COMPLETED)

    supervisor._execute_stage = successful_stage
    result = run_async(supervisor._run_autonomous_loop())

    assert result.status == AgentStatus.COMPLETED
    assert supervisor._design_state.current_stage == DesignStage.COMPLETED
    assert executed_stages == [DesignStage.FPGA_PROGRAMMING]
    assert "Hardware" in result.outputs["message"]