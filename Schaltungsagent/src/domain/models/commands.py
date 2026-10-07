from dataclasses import dataclass, field
from typing import Any


@dataclass
class Command:
    command_id: str = ""
    task_id: str = ""
    payload: dict = field(default_factory=dict)


@dataclass
class RunTaskCommand(Command):
    request: str = ""
    domain: str = "vhdl"


@dataclass
class AnalyzeTaskCommand(Command):
    request: str = ""
    domain: str = "vhdl"


@dataclass
class GenerateArtifactsCommand(Command):
    request: str = ""
    analysis: str = ""
    domain: str = "vhdl"


@dataclass
class PrepareWorkspaceCommand(Command):
    task_id: str = ""
    domain: str = "vhdl"


@dataclass
class RunAgentCommand(Command):
    workspace: str = ""
    instruction: str = ""


@dataclass
class TestCommand(Command):
    workspace: str = ""
    iteration: int = 0


@dataclass
class RepairCommand(Command):
    workspace: str = ""
    error: str = ""
    iteration: int = 0


@dataclass
class ValidateCommand(Command):
    task_data: dict = field(default_factory=dict)
