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
    default_timeout: int = 300
    max_repair_iterations: int = 5


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
    search_paths: list = field(default_factory=lambda: ["./src/domains"])
    paths: dict = field(default_factory=lambda: {"vhdl": "./src/domains/vhdl"})


@dataclass
class Settings:
    llm: LLMConfig = field(default_factory=LLMConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    opencode: OpenCodeConfig = field(default_factory=OpenCodeConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    domains: DomainsConfig = field(default_factory=DomainsConfig)

    _config_dir: str = ""

    @property
    def base_dir(self) -> Path:
        return Path(self._config_dir)


def load_config(config_path: str | None = None) -> Settings:
    if config_path is None:
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
    if "dashboard" in data:
        settings.dashboard = DashboardConfig(**data["dashboard"])
    if "logging" in data:
        settings.logging = LoggingConfig(**data["logging"])
    if "domains" in data:
        domains_data = data["domains"]
        settings.domains = DomainsConfig(
            default=domains_data.get("default", "vhdl"),
            search_paths=domains_data.get("search_paths", ["./src/domains"]),
            paths=domains_data.get("paths", {"vhdl": "./src/domains/vhdl"}),
        )

    return settings
