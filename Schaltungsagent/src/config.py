import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    provider: str = "stub"
    model: str = "gpt-oss:120b-cloud"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.1
    max_tokens: int = 4096


@dataclass
class RAGConfig:
    enabled: bool = True
    vector_store: str = "qdrant"
    vector_store_path: str = "./memory/qdrant"
    embedding_model: str = "jina-embeddings-v5-text-small"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_results: int = 5
    data_dir: str = "./Dateien"
    memory_dir: str = "./memory"


@dataclass
class WorkspaceConfig:
    base_dir: str = "./projects"
    cleanup_on_failure: bool = False
    cleanup_ttl_hours: int = 72
    keep_logs: bool = True
    max_workspaces: int = 100


@dataclass
class OpenCodeConfig:
    binary: str = "opencode"
    default_timeout: int = 600
    max_repair_iterations: int = 5
    use_docker: bool = False
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
    llm: LLMConfig = field(default_factory=LLMConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    opencode: OpenCodeConfig = field(default_factory=OpenCodeConfig)
    ghdl: GHDLConfig = field(default_factory=GHDLConfig)
    vivado: VivadoConfig = field(default_factory=VivadoConfig)
    flash: FlashConfig = field(default_factory=FlashConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    domains: DomainsConfig = field(default_factory=DomainsConfig)
    eda_tools: EdaToolsConfig = field(default_factory=EdaToolsConfig)
    synthesis: SynthesisConfig = field(default_factory=SynthesisConfig)

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

    if "llm" in data:
        settings.llm = LLMConfig(**data["llm"])
    if "rag" in data:
        settings.rag = RAGConfig(**data["rag"])
    if "workspace" in data:
        settings.workspace = WorkspaceConfig(**data["workspace"])
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
