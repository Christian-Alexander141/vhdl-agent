from dataclasses import dataclass, field


@dataclass
class VHDLBuildDefinition:
    compiler: str = "ghdl"
    file_extensions: list[str] = field(default_factory=lambda: [".vhd", ".vhdl"])
    analyze_flags: list[str] = field(default_factory=lambda: ["-a"])
    elaborate_flags: list[str] = field(default_factory=lambda: ["-e"])
    run_flags: list[str] = field(default_factory=lambda: ["-r", "--stop-time=1us"])
    library: str = "work"


class VHDLBuildDefinitions:
    DEFAULT = VHDLBuildDefinition()

    @classmethod
    def get_build_definition(cls) -> VHDLBuildDefinition:
        return cls.DEFAULT
