import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field





@dataclass
class WorkspaceConfig:
    base_dir: str = "./projects"
    cleanup_on_failure: bool = False
    cleanup_temp_files: bool = True
    cleanup_ttl_hours: int = 72
    keep_logs: bool = True
    max_workspaces: int = 100


@dataclass
class LimitsConfig:
    max_prompt_bytes: int = 200_000
    # Unabhängige Module, die gleichzeitig von HDL-Workern implementiert
    # werden. 1 = sequentiell (ressourcenschonend für lokales OpenCode).
    max_parallel_workers: int = 2


@dataclass
class KnowledgeConfig:
    enabled: bool = True


@dataclass
class OpenCodeConfig:
    binary: str = "opencode"
    model: str = "opencode/mimo-v2.6-flash-free"
    fallback_model: str = "opencode/mimo-v2.6-flash-free"
    default_timeout: int = 600
    plan_timeout_seconds: int = 180
    skills_dir: str = ".opencode/skills"
    max_repair_iterations: int = 5
    # Ausführung: test_mode=true führt OpenCode nativ auf dem Host aus (GHDL
    # steht den Workern dann direkt zur Verfügung). Docker-Isolation ist für
    # den Produktivbetrieb vorgesehen und wird erst wieder aufgenommen, wenn
    # das MAS einem einzelnen OpenCode (gleiches Modell) überlegen ist.
    test_mode: bool = False
    # "modular": ein OpenCode-Aufruf je Modul/Testbench (TaskGraph, parallel).
    # "single_session": ein OpenCode-Aufruf implementiert das ganze Projekt
    #   mit gemeinsamem Kontext; die Gates, Reparatur und Hardware-Stufen des
    #   MAS bleiben unverändert.
    implementation_mode: str = "modular"
    # "persistent": echte Läufe – bei Fehlern eskalieren (reparieren → Modul neu
    #   schreiben → Architektur überarbeiten → Fallback-Modell) statt aufzugeben.
    # "standard": knappe Grenzen wie bisher (Benchmarks, Vergleichbarkeit).
    repair_policy: str = "persistent"
    # Veraltet: wird ignoriert; Docker gilt immer, wenn test_mode false ist.
    use_docker: bool = True
    # "per_task": eigener Container je Auftrag (docker run --rm), nur das
    #             Projektverzeichnis ist eingebunden (empfohlen).
    # "shared":   docker exec in einen laufenden Container (docker_container),
    #             der projects/ unter docker_workspace eingebunden hat.
    docker_isolation: str = "per_task"
    docker_image: str = "ghcr.io/anomalyco/opencode:latest"
    docker_binary: str = "opencode"
    docker_network: str = "bridge"
    docker_memory: str = ""        # z. B. "4g"; leer = kein Limit
    docker_cpus: str = ""          # z. B. "2"; leer = kein Limit
    # Host-Verzeichnis mit OpenCode-Zugangsdaten, wird schreibgeschützt
    # eingebunden (z. B. ~/.local/share/opencode). Leer = keine Zugangsdaten.
    docker_auth_dir: str = ""
    docker_container: str = "opencode-agent"
    docker_workspace: str = "/workspace"
    docker_host_workspace: str = "./projects"


@dataclass
class GHDLConfig:
    binary: str = "ghdl"
    timeout_seconds: int = 60


@dataclass
class VivadoConfig:
    binary: str = "vivado"
    settings_script: str = ""
    timeout_seconds: int = 600


@dataclass
class FlashConfig:
    method: str = "vivado_jtag"
    timeout_seconds: int = 120


@dataclass
class DashboardConfig:
    host: str = "0.0.0.0"
    port: int = 8088
    websocket_path: str = "/ws"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "structured"
    output: str = "console"
    log_dir: str = "./logs"


@dataclass
class DomainsConfig:
    default: str = "vhdl"
    search_paths: list = field(default_factory=lambda: ["./src/domain_plugins"])
    paths: dict = field(default_factory=lambda: {"vhdl": "./src/domain_plugins/vhdl"})


@dataclass
class EdaToolsConfig:
    # Expliziter Pfad zum ModelSim-Binary (vsim oder vsim.exe unter Wine),
    # z. B. ~/.wine/drive_c/intelFPGA/18.1/modelsim_ase/win32aloem/vsim.exe.
    # Leer = automatische Erkennung (PATH bzw. Wine-Prefix-Suche).
    modelsim_binary: str = ""
    # Befehl, mit dem ein Windows-Binary (vsim.exe) gestartet wird.
    modelsim_wine: str = "wine"


@dataclass
class SynthesisConfig:
    # Synthese nach erfolgreicher Validierung automatisch ausführen.
    enabled: bool = True
    # Standard-Ziel-FPGA (Schlüssel aus fpgas.yaml, z. B. arty_s7_50).
    default_fpga: str = "arty_s7_50"
    # Zeitlimit pro Synthese-Schritt.
    timeout_seconds: int = 120


@dataclass
class HardwareTestConfig:
    # Serieller Port der USB-UART-Brücke (z. B. /dev/ttyUSB1). Leer = keine
    # echte Hardware: Hardwaretests werden übersprungen, nie als bestanden
    # gemeldet.
    uart_port: str = ""
    baudrate: int = 115200
    timeout_seconds: float = 5.0
    # UART-Echo-Brücke ins Top-Level einbauen: "auto" nur bei echtem
    # Hardwaretest (uart_port gesetzt), definierten hardware_tests oder wenn
    # die Anforderung UART erwähnt; "always" / "off" erzwingen es.
    uart_integration: str = "auto"


@dataclass
class VerificationGateConfig:
    # Mindestanteil der Architekturmodule, die von einer simulierten
    # Testbench erreicht werden müssen, bevor synthetisiert wird.
    min_module_coverage: float = 1.0
    # Contract-Verletzungen (Ports, Richtung, Breite) blockieren den Static Check.
    enforce_contracts: bool = True
    # Timing-Gate: WNS/WHS müssen >= 0 sein; fehlende Reports blockieren.
    require_timing_closure: bool = True
    # Mutationsanalyse: Anteil absichtlich fehlerhafter Entwurfsvarianten, den die
    # Testbenches erkennen müssen (0 = aus). < 1, weil äquivalente Mutanten nie
    # erkennbar sind; nach einem Nachbesserungsversuch nur noch Warnung.
    min_mutation_score: float = 0.6
    max_mutants: int = 10


@dataclass
class FpgaConfig:
    # Ein Eintrag aus der FPGA-Registry (fpgas.yaml).
    family: str = ""
    part: str = ""
    toolchain: str = ""
    wiki: str = ""
    clock_hz: int = 100_000_000
    programmer: str = "vivado"  # "vivado" oder "openfpgaloader"
    board_name: str = ""  # Board-Name für den Programmer (z.B. "arty_s7" für openFPGALoader)


@dataclass
class Settings:
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    knowledge: KnowledgeConfig = field(default_factory=KnowledgeConfig)
    opencode: OpenCodeConfig = field(default_factory=OpenCodeConfig)
    ghdl: GHDLConfig = field(default_factory=GHDLConfig)
    vivado: VivadoConfig = field(default_factory=VivadoConfig)
    flash: FlashConfig = field(default_factory=FlashConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    domains: DomainsConfig = field(default_factory=DomainsConfig)
    eda_tools: EdaToolsConfig = field(default_factory=EdaToolsConfig)
    synthesis: SynthesisConfig = field(default_factory=SynthesisConfig)
    hardware_test: HardwareTestConfig = field(default_factory=HardwareTestConfig)
    gates: VerificationGateConfig = field(default_factory=VerificationGateConfig)

    _config_dir: str = ""

    @property
    def base_dir(self) -> Path:
        return Path(self._config_dir)

    def resolve_path(self, path: str) -> str:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self.base_dir / p
        return str(p)


def load_config(config_path: str | None = None) -> Settings:
    if config_path is None:
        repo_root = Path(__file__).resolve().parents[2]
        root_config = repo_root / "config.yaml"
        if root_config.exists():
            config_path = str(root_config)
        else:
            config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

    settings = Settings()
    settings._config_dir = os.path.dirname(os.path.abspath(config_path))

    path = Path(config_path)
    if not path.exists():
        return settings

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data:
        return settings

    if "workspace" in data:
        settings.workspace = WorkspaceConfig(**data["workspace"])
    if "limits" in data:
        settings.limits = LimitsConfig(**data["limits"])
    if "knowledge" in data:
        settings.knowledge = KnowledgeConfig(**data["knowledge"])
    if "opencode" in data:
        settings.opencode = OpenCodeConfig(**data["opencode"])
    if "ghdl" in data:
        settings.ghdl = GHDLConfig(**data["ghdl"])
    if "vivado" in data:
        settings.vivado = VivadoConfig(**data["vivado"])
    if "flash" in data:
        settings.flash = FlashConfig(**data["flash"])
    if "dashboard" in data:
        settings.dashboard = DashboardConfig(**data["dashboard"])
    if "logging" in data:
        settings.logging = LoggingConfig(**data["logging"])
    if "domains" in data:
        domains_data = data["domains"]
        settings.domains = DomainsConfig(
            default=domains_data.get("default", "vhdl"),
            search_paths=domains_data.get("search_paths", ["./src/domain_plugins"]),
            paths=domains_data.get("paths", {"vhdl": "./src/domain_plugins/vhdl"}),
        )
    if "eda_tools" in data:
        settings.eda_tools = EdaToolsConfig(**data["eda_tools"])
    if "synthesis" in data:
        settings.synthesis = SynthesisConfig(**data["synthesis"])
    if "hardware_test" in data:
        settings.hardware_test = HardwareTestConfig(**data["hardware_test"])
    if "gates" in data:
        settings.gates = VerificationGateConfig(**data["gates"])

    if os.environ.get("VHDL_AGENT_TEST_MODE", "").lower() in {"1", "true", "yes", "on"}:
        settings.opencode.test_mode = True

    return settings


def load_fpga_registry(registry_path: str | None = None) -> dict[str, FpgaConfig]:
    """Lädt die FPGA-Registry (fpgas.yaml) in eine Dict von FpgaConfig.

    Standard: Schaltungsagent/src/data/fpgas.yaml (App-interne Referenzdaten,
    kein Benutzer-Config). Fehlende Datei ergibt eine leere Registry.
    """
    if registry_path is None:
        registry_path = str(
            Path(__file__).resolve().parent / "data" / "fpgas.yaml"
        )
    path = Path(registry_path)
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    fpgas = data.get("fpgas", {}) or {}
    return {name: FpgaConfig(**cfg) for name, cfg in fpgas.items()}
