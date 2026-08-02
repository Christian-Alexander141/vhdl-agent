from dataclasses import dataclass, field


@dataclass
class VHDLTestDefinition:
    name: str = ""
    entity: str = ""
    architecture: str = "Behavioral"
    testbench_suffix: str = "_tb"
    simulator: str = "ghdl"
    analyze_flags: list[str] = field(default_factory=lambda: ["-a"])
    elaborate_flags: list[str] = field(default_factory=lambda: ["-e"])
    run_flags: list[str] = field(default_factory=lambda: ["-r", "--stop-time=1us"])

    def analyze_command(self, file: str) -> list[str]:
        return [self.simulator] + self.analyze_flags + [file]

    def elaborate_command(self, entity: str) -> list[str]:
        return [self.simulator] + self.elaborate_flags + [entity]

    def run_command(self, entity: str) -> list[str]:
        return [self.simulator] + self.run_flags + [entity]


class VHDLTestDefinitions:
    DEFAULT = VHDLTestDefinition(name="default")

    @classmethod
    def get_test_definition(cls, name: str = "default") -> VHDLTestDefinition:
        return cls.DEFAULT
