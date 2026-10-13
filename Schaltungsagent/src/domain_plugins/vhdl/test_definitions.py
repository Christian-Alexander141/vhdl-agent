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
    run_flags: list[str] = field(default_factory=lambda: ["-r", "--stop-time=1ms"])
    # Globale GHDL-Optionen: duerfen NICHT hinter der Einheit stehen
    # (ghdl -r <entity> --std=08 liefert "cannot find entity").
    # AGENTS.md Abschnitt 4 dokumentiert --std=08 als Pipeline-Standard;
    # die Testbenches nutzen VHDL-2008 (externe Namen, to_string).
    global_flags: list[str] = field(default_factory=lambda: ["--std=08"])

    def analyze_command(self, file: str) -> list[str]:
        return [self.simulator] + self.analyze_flags + self.global_flags + [file]

    def elaborate_command(self, entity: str) -> list[str]:
        return [self.simulator] + self.elaborate_flags + self.global_flags + [entity]

    def run_command(self, entity: str) -> list[str]:
        # GHDL erwartet Simulationsoptionen (z. B. --stop-time) NACH der
        # Top-Level-Einheit: ghdl -r <entity> --stop-time=...
        mode_flags = [f for f in self.run_flags if not f.startswith("--")]
        option_flags = [f for f in self.run_flags if f.startswith("--")]
        return [self.simulator] + mode_flags + self.global_flags + [entity] + option_flags


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
