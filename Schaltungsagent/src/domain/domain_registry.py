import os
import importlib
import inspect
import logging
from pathlib import Path
from typing import Any

from .ports import (
    ArtifactGenerator,
    ValidationService,
)

logger = logging.getLogger(__name__)


class DomainRegistry:
    _domains: dict[str, dict[str, Any]] = {}

    @classmethod
    def discover(cls, search_paths: list[str]) -> dict[str, dict[str, Any]]:
        cls._domains = {}
        for search_path in search_paths:
            base = Path(search_path)
            if not base.exists():
                continue
            for entry in sorted(base.iterdir()):
                if not entry.is_dir() or entry.name.startswith("_"):
                    continue
                domain_name = entry.name
                if domain_name in cls._domains:
                    continue
                try:
                    domain_info = cls._load_domain(domain_name, entry)
                    if domain_info:
                        cls._domains[domain_name] = domain_info
                        logger.info("Discovered domain: %s", domain_name)
                except Exception as e:
                    logger.warning("Failed to load domain '%s': %s", domain_name, e)
        return cls._domains

    @classmethod
    def _load_domain(cls, name: str, path: Path) -> dict[str, Any] | None:
        module_path = f"src.domain_plugins.{name}"
        try:
            mod = importlib.import_module(module_path)
        except ImportError:
            return None

        info: dict[str, Any] = {
            "name": name,
            "path": str(path),
        }

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if not inspect.isclass(attr):
                continue
            if "RAGData" in attr_name:
                info["rag_data"] = attr
            elif "Templates" in attr_name:
                info["templates"] = attr
            elif "Prompts" in attr_name:
                info["prompts"] = attr
            elif "TestDefinitions" in attr_name:
                info["test_definitions"] = attr
            elif "BuildDefinitions" in attr_name:
                info["build_definitions"] = attr
            elif "ArtifactGenerator" in attr_name:
                info["artifact_generator_class"] = attr
            elif "Validator" in attr_name:
                info["validator_class"] = attr
            elif "BuildService" in attr_name:
                info["build_service_class"] = attr

        return info if info else None

    @classmethod
    def get_domain(cls, name: str) -> dict[str, Any] | None:
        return cls._domains.get(name)

    @classmethod
    def list_domains(cls) -> list[str]:
        return list(cls._domains.keys())

    @classmethod
    def has_domain(cls, name: str) -> bool:
        return name in cls._domains

    @classmethod
    def get_rag_data(cls, domain: str):
        info = cls._domains.get(domain)
        if info and "rag_data" in info:
            return info["rag_data"]
        return None

    @classmethod
    def get_templates(cls, domain: str):
        info = cls._domains.get(domain)
        if info and "templates" in info:
            return info["templates"]
        return None

    @classmethod
    def get_prompts(cls, domain: str):
        info = cls._domains.get(domain)
        if info and "prompts" in info:
            return info["prompts"]
        return None

    @classmethod
    def get_test_definitions(cls, domain: str):
        info = cls._domains.get(domain)
        if info and "test_definitions" in info:
            return info["test_definitions"]
        return None

    @classmethod
    def get_build_definitions(cls, domain: str):
        info = cls._domains.get(domain)
        if info and "build_definitions" in info:
            return info["build_definitions"]
        return None

    @classmethod
    def get_artifact_generator(cls, domain: str) -> type[ArtifactGenerator] | None:
        info = cls._domains.get(domain)
        if info and "artifact_generator_class" in info:
            return info["artifact_generator_class"]
        return None

    @classmethod
    def get_validator(cls, domain: str) -> type[ValidationService] | None:
        info = cls._domains.get(domain)
        if info and "validator_class" in info:
            return info["validator_class"]
        return None

    @classmethod
    def create_artifact_generator(cls, domain: str) -> ArtifactGenerator | None:
        generator_class = cls.get_artifact_generator(domain)
        if generator_class:
            try:
                return generator_class()
            except Exception as e:
                logger.warning("Failed to create artifact generator for %s: %s", domain, e)
        return None

    @classmethod
    def create_validator(cls, domain: str) -> ValidationService | None:
        validator_class = cls.get_validator(domain)
        if validator_class:
            try:
                return validator_class()
            except Exception as e:
                logger.warning("Failed to create validator for %s: %s", domain, e)
        return None

    @classmethod
    def get_all_domain_info(cls, domain: str) -> dict[str, Any]:
        info: dict[str, Any] = {
            "name": domain,
            "rag_data": cls.get_rag_data(domain),
            "templates": cls.get_templates(domain),
            "prompts": cls.get_prompts(domain),
            "test_definitions": cls.get_test_definitions(domain),
            "build_definitions": cls.get_build_definitions(domain),
            "artifact_generator": cls.get_artifact_generator(domain),
            "validator": cls.get_validator(domain),
        }
        return {k: v for k, v in info.items() if v is not None}
