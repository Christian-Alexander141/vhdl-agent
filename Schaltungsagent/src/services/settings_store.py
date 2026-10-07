"""Bearbeiten der Laufzeit-Einstellungen über das Dashboard.

Die Einstellungen werden typgeprüft auf die Settings-Dataclasses angewendet.
Persistiert werden nur die tatsächlich geänderten Felder: Die bestehende
config.yaml wird gelesen, an diesen Stellen ergänzt und zurückgeschrieben,
sodass alle übrigen Abschnitte erhalten bleiben.
"""
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path

import yaml

# Abschnitte, die über das Dashboard geändert werden dürfen.
EDITABLE_SECTIONS = (
    "opencode", "llm", "synthesis", "gates", "hardware_test",
    "limits", "knowledge", "ghdl", "vivado", "flash",
)

# Felder, die bewusst nicht über das Dashboard änderbar sind.
READ_ONLY_FIELDS = {
    ("opencode", "use_docker"),          # veraltet, siehe create_opencode_service
    ("opencode", "docker_host_workspace"),
}

CHOICES = {
    ("opencode", "docker_isolation"): ("per_task", "shared"),
    ("opencode", "docker_network"): ("bridge", "none", "host"),
    ("llm", "provider"): ("ollama", "openai", "anthropic", "stub"),
    ("flash", "method"): ("vivado", "openfpgaloader"),
}

RANGES = {
    ("gates", "min_module_coverage"): (0.0, 1.0),
    ("limits", "max_parallel_workers"): (1, 16),
    ("opencode", "max_repair_iterations"): (1, 50),
    ("opencode", "default_timeout"): (30, 7200),
    ("opencode", "plan_timeout_seconds"): (30, 7200),
    ("hardware_test", "baudrate"): (300, 4_000_000),
    ("hardware_test", "timeout_seconds"): (0.1, 600.0),
}

# Wirken sofort; alles andere wird beim nächsten Start übernommen.
LIVE_SECTIONS = {"opencode"}


class SettingsValidationError(ValueError):
    pass


def editable_settings(settings) -> dict:
    """Aktuelle Werte aller editierbaren Abschnitte plus Metadaten fürs UI."""
    data = {}
    for section in EDITABLE_SECTIONS:
        value = getattr(settings, section, None)
        if is_dataclass(value):
            data[section] = asdict(value)
    data["_meta"] = {
        "choices": {f"{s}.{f}": list(v) for (s, f), v in CHOICES.items()},
        "read_only": [f"{s}.{f}" for s, f in sorted(READ_ONLY_FIELDS)],
        "live_sections": sorted(LIVE_SECTIONS),
    }
    return data


def _coerce(section: str, name: str, current, value):
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "1", "yes", "on", "false", "0", "no", "off"):
            return value.lower() in ("true", "1", "yes", "on")
        raise SettingsValidationError(f"{section}.{name} erwartet true/false")
    if isinstance(current, int):
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise SettingsValidationError(f"{section}.{name} erwartet eine ganze Zahl") from None
    elif isinstance(current, float):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise SettingsValidationError(f"{section}.{name} erwartet eine Zahl") from None
    elif isinstance(current, (list, dict)):
        if not isinstance(value, type(current)):
            raise SettingsValidationError(f"{section}.{name} hat den falschen Typ")
        return value
    else:
        text = "" if value is None else str(value).strip()
        choices = CHOICES.get((section, name))
        if choices and text not in choices:
            raise SettingsValidationError(f"{section}.{name} muss eines von {', '.join(choices)} sein")
        return text
    low, high = RANGES.get((section, name), (None, None))
    if low is not None and not low <= number <= high:
        raise SettingsValidationError(f"{section}.{name} muss zwischen {low} und {high} liegen")
    return number


def apply_settings_update(settings, payload: dict) -> list[tuple[str, str, object]]:
    """Validiert ``payload`` vollständig und wendet es erst dann an.

    Gibt die tatsächlich geänderten Felder zurück. Unbekannte Abschnitte
    oder Felder sind ein Fehler, damit Tippfehler nicht still verpuffen.
    Nicht-Abschnitts-Schlüssel (z. B. ein altes ``theme``) werden ignoriert.
    """
    planned: list[tuple[object, str, str, object]] = []
    for section, values in (payload or {}).items():
        if not isinstance(values, dict):
            continue
        if section not in EDITABLE_SECTIONS:
            raise SettingsValidationError(f"Abschnitt '{section}' ist nicht editierbar")
        target = getattr(settings, section)
        known = {f.name for f in fields(target)}
        for name, value in values.items():
            if name not in known:
                raise SettingsValidationError(f"Unbekannte Einstellung {section}.{name}")
            if (section, name) in READ_ONLY_FIELDS:
                continue
            new_value = _coerce(section, name, getattr(target, name), value)
            if new_value != getattr(target, name):
                planned.append((target, section, name, new_value))

    for target, _, name, value in planned:
        setattr(target, name, value)
    return [(section, name, value) for _, section, name, value in planned]


def persist_settings_update(config_path: str | Path, changes: list[tuple[str, str, object]]) -> None:
    """Schreibt nur die geänderten Felder in die bestehende config.yaml (atomar)."""
    if not changes:
        return
    path = Path(config_path)
    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for section, name, value in changes:
        data.setdefault(section, {})[name] = value
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    temporary.replace(path)


def restart_required(changes: list[tuple[str, str, object]]) -> list[str]:
    return sorted({f"{s}.{n}" for s, n, _ in changes if s not in LIVE_SECTIONS})
