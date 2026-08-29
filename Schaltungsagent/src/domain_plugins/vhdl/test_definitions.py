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
    run_flags: list[str] = field(default_factory=lambda: ["-r", "--stop-time=20us"])

    def analyze_command(self, file: str) -> list[str]:
        return [self.simulator] + self.analyze_flags + [file]

    def elaborate_command(self, entity: str) -> list[str]:
        return [self.simulator] + self.elaborate_flags + [entity]

    def run_command(self, entity: str) -> list[str]:
        # GHDL erwartet Simulationsoptionen (z. B. --stop-time) NACH der
        # Top-Level-Einheit: ghdl -r <entity> --stop-time=...
        mode_flags = [f for f in self.run_flags if not f.startswith("--")]
        option_flags = [f for f in self.run_flags if f.startswith("--")]
        return [self.simulator] + mode_flags + [entity] + option_flags


class VHDLTestDefinitions:
    DEFAULT = VHDLTestDefinition(name="default")
    ARTY_RUNNING_LIGHT = VHDLTestDefinition(
        name="arty_running_light",
        run_flags=["-r", "--stop-time=50us"]
    )

    @classmethod
    def get_test_definition(cls, name: str = "default") -> VHDLTestDefinition:
        if name == "arty_running_light":
            return cls.ARTY_RUNNING_LIGHT
        return cls.DEFAULT
