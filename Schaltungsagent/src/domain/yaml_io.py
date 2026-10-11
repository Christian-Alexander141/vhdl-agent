"""Schnelles YAML für den Projektzustand.

design_state.yaml wird bei jedem Phasenwechsel geschrieben und vor jedem
OpenCode-Auftrag gelesen. Mit dem reinen Python-Parser dauerte das im Lauf
led-pattern-display (1,27 MB Zustand) je 6,7 s; die C-Variante (libyaml) ist
um ein Vielfaches schneller und liefert dieselben Daten.
"""
from __future__ import annotations

import yaml

_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_Dumper = getattr(yaml, "CSafeDumper", yaml.SafeDumper)


def load(text: str):
    return yaml.load(text, Loader=_Loader)


def dump(data, **kwargs) -> str:
    kwargs.setdefault("sort_keys", False)
    kwargs.setdefault("default_flow_style", False)
    return yaml.dump(data, Dumper=_Dumper, **kwargs)
