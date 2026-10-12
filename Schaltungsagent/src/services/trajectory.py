"""Lauf-Trajektorien außerhalb des Workspaces (Trainingsdaten für Fehlerreparatur).

Je Lauf eine JSONL-Datei unter ``<runs_dir>/<projekt>/<zeitstempel>.jsonl``:
Anforderung, Phasenergebnisse, vorgefilterte Diagnosen (Kernzeilen, Fehlerklasse,
Herkunft), Reparaturen (Maßnahme, Ziel, Ergebnis, Befund, Diff) und Abschluss.
Das Verzeichnis liegt bewusst nicht im Workspace: OpenCode durchsucht den
Workspace, wachsende Protokolle würden dort Suchtreffer und Kontext aufblähen.

Absolute Pfade, Home-Verzeichnis und Rechnername werden ersetzt; das Feld
``origin`` erlaubt, System- und Werkzeugfehler (``tool``, ``hardware``) beim
Auswerten auszufiltern.
"""
from __future__ import annotations

import difflib
import json
import logging
import os
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_DIFF_CHARS = 60_000


class Scrubber:
    """Ersetzt Workspace-Pfad, Home-Verzeichnis, Benutzer- und Rechnername."""

    def __init__(self, workspace: str | Path):
        replacements = [(str(Path(workspace).resolve()), "<workspace>"), (str(workspace), "<workspace>")]
        home = str(Path.home())
        if home not in ("", "/"):
            replacements.append((home, "~"))
        self._replacements = sorted({r for r in replacements if r[0]}, key=lambda r: -len(r[0]))
        names = {socket.gethostname(), os.environ.get("USER", ""), os.environ.get("LOGNAME", "")}
        names = {n for n in names if len(n) >= 3}
        self._names = re.compile(r"\b(" + "|".join(map(re.escape, sorted(names, key=len, reverse=True))) + r")\b") if names else None

    def text(self, value: str) -> str:
        for old, new in self._replacements:
            value = value.replace(old, new)
        if self._names:
            value = self._names.sub("<host>", value)
        return value

    def __call__(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {str(k): self(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self(v) for v in value]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return self.text(str(value))


def unified_diff(before: dict[str, str], after: dict[str, str]) -> str:
    """Diff zweier Dateistände {relativer Pfad: Inhalt}; gekürzt auf _MAX_DIFF_CHARS."""
    parts = []
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        parts.extend(difflib.unified_diff(
            (old or "").splitlines(keepends=True), (new or "").splitlines(keepends=True),
            fromfile=f"a/{name}" if old is not None else "/dev/null",
            tofile=f"b/{name}" if new is not None else "/dev/null",
        ))
    diff = "".join(parts)
    if len(diff) > _MAX_DIFF_CHARS:
        diff = diff[:_MAX_DIFF_CHARS] + "\n[... gekürzt]\n"
    return diff


class TrajectoryRecorder:
    """Schreibt die Ereignisse eines Laufs; Fehler beim Schreiben brechen den Lauf nie ab."""

    def __init__(self, runs_dir: str | Path, project_id: str, workspace: str | Path):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = Path(runs_dir).expanduser() / project_id / f"{stamp}.jsonl"
        self._scrub = Scrubber(workspace)
        self._seq = 0

    def record(self, kind: str, **data: Any) -> None:
        self._seq += 1
        entry = {"seq": self._seq, "at": datetime.now(timezone.utc).isoformat(), "kind": kind, **data}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(self._scrub(entry), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Trajektorie nicht geschrieben (%s): %s", self.path, exc)
