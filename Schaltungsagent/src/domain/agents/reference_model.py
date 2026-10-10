"""Differentieller Test gegen ein ausführbares Python-Referenzmodell.

Ein Agent schreibt *vor* der Implementierung aus PROMPT.md ein kleines
Python-Modell (``model/reference_model.py``) samt Selbsttest. Dieses Modul
erzeugt daraus deterministisch Reizfolgen, berechnet die erwarteten Ausgaben
Takt für Takt und schreibt eine VHDL-Testbench, die den Entwurf damit
vergleicht. Erwartungswerte werden so berechnet statt von einem Sprachmodell
geschätzt; zuvor (Golden-Vektoren im Manifest) waren sie im Benchmark
widersprüchlich und verwarfen einen korrekten Entwurf.

Herkunft der Idee (siehe docs/doku.html, Abschnitt 16): Referenzmodell als
Prüfgrundlage nach FPGAgent (arXiv:2608.23630), Python als Zwischenstufe nach
VeriMoA (arXiv:2510.27617), programmbasierte Prüfung nach AutoBench und PRO-V
(arXiv:2506.12200), Vergleich Implementierung/Modell als differentielles
Testen (McKeeman 1998). Eigener Beitrag: Einbettung in die Gates des MAS,
deterministische Stimulus-Erzeugung, VHDL-Vergleichsbench ohne Co-Simulation.
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.domain.agents.contract_check import ContractChecker

MODEL_DIR = "model"
MODEL_FILE = f"{MODEL_DIR}/reference_model.py"
MODEL_TEST_FILE = f"{MODEL_DIR}/test_reference_model.py"
CLOCK_PERIOD_NS = 10
DEFAULT_CYCLES = 400
MAX_CYCLES = 50_000          # 1 ms Simulationszeit des Validators / 10 ns Takt = 100 000
EXHAUSTIVE_INPUT_BITS = 12   # kombinatorisch: bis 4096 Eingangskombinationen vollständig
MODEL_TIMEOUT_S = 120

_VECTOR_TYPES = {"std_logic_vector", "std_ulogic_vector", "unsigned", "signed"}
_SCALAR_TYPES = {"std_logic", "std_ulogic"}


@dataclass(frozen=True)
class ModelPort:
    name: str
    direction: str   # "in" | "out"
    width: int
    base: str        # std_logic, std_logic_vector, unsigned, signed ...

    @property
    def scalar(self) -> bool:
        return self.base in _SCALAR_TYPES

    @property
    def signed(self) -> bool:
        return self.base == "signed"

    def vhdl_type(self) -> str:
        return self.base if self.scalar else f"{self.base}({self.width - 1} downto 0)"


def is_clock(name: str) -> bool:
    """Takteingang? Bewusst streng: 'clk_en' oder 'clk_div_en' sind Enables, kein Takt."""
    lowered = name.lower()
    return lowered in ("clk", "clock", "clk_i", "clk_in", "i_clk", "clock_i") or lowered.endswith(("_clk", "_clock"))


def is_reset(name: str) -> bool:
    return bool(re.search(r"(^|_)(n?rst|n?reset)(_?n)?($|_)", name.lower()))


def reset_active_low(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(("_n", "rstn", "resetn")) or lowered.startswith(("n_", "nrst", "nreset"))


def entity_ports(workspace: str, top: str) -> tuple[list[ModelPort] | None, str]:
    """Ports der tatsächlich implementierten Top-Entity (Breiten mit aufgelösten Generics)."""
    path = Path(workspace) / "src" / f"{top}.vhd"
    checker = ContractChecker()
    info = checker._parse_entity(path) if path.is_file() else None
    if not info:
        return None, f"Entity {top} nicht in src/{top}.vhd gefunden"
    ports: list[ModelPort] = []
    for port in info["ports"]:
        base = ContractChecker._base_type(port["type"])
        if port["direction"] not in ("in", "out"):
            return None, f"Port {port['name']}: Richtung {port['direction']} wird nicht unterstützt"
        if base not in _VECTOR_TYPES | _SCALAR_TYPES:
            return None, f"Port {port['name']}: Typ {port['type']} wird nicht unterstützt"
        width = ContractChecker._width(port["type"], info["generics"])
        if width is None:
            return None, f"Port {port['name']}: Breite von {port['type']} nicht bestimmbar"
        ports.append(ModelPort(port["name"], port["direction"], width, base))
    return ports, ""


def model_interface_text(ports: list[ModelPort]) -> str:
    rows = []
    for p in ports:
        kind = "Bit (0/1)" if p.scalar else (
            f"{p.width}-Bit-Zahl mit Vorzeichen" if p.signed else f"{p.width}-Bit-Zahl ohne Vorzeichen")
        role = " (Takt – NICHT in inputs)" if p.direction == "in" and is_clock(p.name) else ""
        rows.append(f"  {p.direction:<3} {p.name}: {kind}{role}")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Stimulus
# ---------------------------------------------------------------------------

def generate_stimulus(ports: list[ModelPort], cycles: int, seed: int = 0) -> list[dict[str, int]]:
    """Deterministische Reizfolge.

    Getaktet: Reset in den ersten zwei Takten und einmal bei ~60 %; übrige
    Eingänge werden über zufällig lange Abschnitte gehalten, damit auch
    Zähler und Zeitgeber ihre Endwerte erreichen. Kombinatorisch: bis
    EXHAUSTIVE_INPUT_BITS vollständig, sonst zufällig.
    """
    rng = random.Random(seed)
    inputs = [p for p in ports if p.direction == "in" and not is_clock(p.name)]
    clocked = any(p.direction == "in" and is_clock(p.name) for p in ports)

    if not clocked:
        total = sum(p.width for p in inputs)
        if total <= EXHAUSTIVE_INPUT_BITS:
            vectors = []
            for value in range(1 << total):
                row, shift = {}, 0
                for p in inputs:
                    row[p.name] = _from_bits((value >> shift) & ((1 << p.width) - 1), p)
                    shift += p.width
                vectors.append(row)
            return vectors
        return [{p.name: _random_value(rng, p) for p in inputs} for _ in range(max(cycles, 1000))]

    reset_windows = {0, 1, int(cycles * 0.6), int(cycles * 0.6) + 1}
    current: dict[str, int] = {}
    hold: dict[str, int] = {}
    vectors = []
    for cycle in range(cycles):
        row = {}
        for p in inputs:
            if is_reset(p.name):
                active = cycle in reset_windows
                row[p.name] = (0 if active else 1) if reset_active_low(p.name) else (1 if active else 0)
                continue
            if hold.get(p.name, 0) <= 0:
                current[p.name] = _random_value(rng, p)
                hold[p.name] = rng.randint(1, 24 if p.width == 1 else 12)
            hold[p.name] -= 1
            row[p.name] = current[p.name]
        vectors.append(row)
    return vectors


def _random_value(rng: random.Random, p: ModelPort) -> int:
    if p.width == 1:
        bias = 0.8 if re.search(r"(^|_)(en|enable|start|valid|go)($|_)", p.name.lower()) else 0.5
        return 1 if rng.random() < bias else 0
    value = rng.getrandbits(p.width)
    return _from_bits(value, p)


def _from_bits(value: int, p: ModelPort) -> int:
    if p.signed and value >= 1 << (p.width - 1):
        return value - (1 << p.width)
    return value


def _to_bits(value: int, p: ModelPort) -> str:
    return format(value & ((1 << p.width) - 1), f"0{p.width}b")


# ---------------------------------------------------------------------------
# Modell ausführen (eigener Prozess: Modellcode stammt von einem Sprachmodell)
# ---------------------------------------------------------------------------

_RUNNER = r'''
import importlib.util, json, sys, traceback
sys.path.insert(0, ".")
def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
mode = sys.argv[1]
try:
    if mode == "meta":
        mod = load("reference_model", "reference_model.py")
        print(json.dumps({"cycles": getattr(mod.ReferenceModel, "SUGGESTED_CYCLES", None)}))
    elif mode == "selftest":
        mod = load("test_reference_model", "test_reference_model.py")
        tests = [n for n in dir(mod) if n.startswith("test_") and callable(getattr(mod, n))]
        failed = []
        for name in tests:
            try:
                getattr(mod, name)()
            except Exception as exc:
                failed.append(f"{name}: {type(exc).__name__}: {exc}")
        print(json.dumps({"tests": len(tests), "failed": failed}))
    else:
        mod = load("reference_model", "reference_model.py")
        stimulus = json.load(sys.stdin)
        model = mod.ReferenceModel()
        model.reset()
        outputs = []
        for row in stimulus:
            result = model.step(dict(row))
            outputs.append({str(k): int(v) for k, v in dict(result).items()})
        print(json.dumps({"outputs": outputs}))
except Exception:
    print(json.dumps({"error": traceback.format_exc()[-1500:]}))
'''


def _run(workspace: str, mode: str, payload: object | None = None) -> dict:
    model_dir = Path(workspace) / MODEL_DIR
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _RUNNER, mode],
            input=json.dumps(payload) if payload is not None else "",
            capture_output=True, text=True, cwd=model_dir, timeout=MODEL_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"Referenzmodell ({mode}) nach {MODEL_TIMEOUT_S} s abgebrochen"}
    lines = [line for line in proc.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        return {"error": (proc.stderr or proc.stdout or "keine Ausgabe")[-1500:]}
    return json.loads(lines[-1])


def run_selftest(workspace: str) -> tuple[bool, str]:
    if not (Path(workspace) / MODEL_TEST_FILE).is_file():
        return False, f"{MODEL_TEST_FILE} fehlt"
    result = _run(workspace, "selftest")
    if "error" in result:
        return False, result["error"]
    if result["tests"] == 0:
        return False, "Selbsttest enthält keine test_-Funktionen"
    if result["failed"]:
        return False, "; ".join(result["failed"])[:1500]
    return True, f"{result['tests']} Selbsttests bestanden"


def run_model(workspace: str, ports: list[ModelPort], stimulus: list[dict]) -> tuple[list[dict] | None, str]:
    result = _run(workspace, "run", stimulus)
    if "error" in result:
        return None, result["error"]
    outputs = result["outputs"]
    expected_names = {p.name.lower(): p for p in ports if p.direction == "out"}
    normalized = []
    for cycle, row in enumerate(outputs):
        lowered = {k.lower(): v for k, v in row.items()}
        missing = sorted(set(expected_names) - set(lowered))
        if missing:
            return None, f"Takt {cycle}: Modell liefert keine Werte für {', '.join(missing)}"
        out = {}
        for key, p in expected_names.items():
            value = lowered[key]
            low, high = (-(1 << (p.width - 1)), (1 << (p.width - 1)) - 1) if p.signed else (0, (1 << p.width) - 1)
            if not low <= value <= high:
                return None, f"Takt {cycle}: {p.name}={value} passt nicht in {p.width} Bit"
            out[p.name] = value
        normalized.append(out)
    return normalized, ""


def suggested_cycles(workspace: str) -> int:
    result = _run(workspace, "meta")
    cycles = result.get("cycles") if isinstance(result, dict) else None
    if isinstance(cycles, int) and cycles > 0:
        return min(cycles, MAX_CYCLES)
    return DEFAULT_CYCLES


# ---------------------------------------------------------------------------
# VHDL-Vergleichs-Testbench
# ---------------------------------------------------------------------------

def build_model_testbench(top: str, ports: list[ModelPort], stimulus: list[dict], expected: list[dict]) -> str:
    """Testbench mit eingebetteten Vektoren (keine Datei-I/O, keine Pfadabhängigkeit)."""
    clock = next((p for p in ports if p.direction == "in" and is_clock(p.name)), None)
    inputs = [p for p in ports if p.direction == "in" and p is not clock]
    outputs = [p for p in ports if p.direction == "out"]
    # Bitlayout einer Zeile: Eingänge, dann erwartete Ausgänge (links = höchstes Bit).
    layout: dict[str, tuple[int, int]] = {}
    position = sum(p.width for p in inputs + outputs)
    for p in inputs + outputs:
        layout[p.name] = (position - 1, position - p.width)
        position -= p.width
    total = sum(p.width for p in inputs + outputs)
    in_bits = sum(p.width for p in inputs)

    def slice_of(p: ModelPort, row: str = "ROWS(i)") -> str:
        hi, lo = layout[p.name]
        return f"{row}({hi})" if p.scalar else f"{row}({hi} downto {lo})"

    rows = []
    for stim, exp in zip(stimulus, expected):
        bits = "".join(_to_bits(stim[p.name], p) for p in inputs) + "".join(_to_bits(exp[p.name], p) for p in outputs)
        rows.append(f'        "{bits}"')
    if len(rows) == 1:  # VHDL-Aggregat mit einem Element braucht benannte Zuordnung
        rows[0] = "        0 => " + rows[0].strip()

    signals = "\n".join(f"    signal {p.name} : {p.vhdl_type()};" for p in ports if p is not clock)
    port_map = ",\n".join(f"            {p.name} => {p.name}" for p in ports)
    drive = "\n".join(
        f"            {p.name} <= {slice_of(p) if p.scalar or p.base == 'std_logic_vector' or p.base == 'std_ulogic_vector' else f'{p.base}({slice_of(p)})'};"
        for p in inputs
    )
    checks = []
    for p in outputs:
        got = p.name if p.scalar or p.base in ("std_logic_vector", "std_ulogic_vector") else f"std_logic_vector({p.name})"
        image = f"std_logic'image({p.name})" if p.scalar else f"to_string({got})"
        exp_image = f"std_logic'image({slice_of(p)})" if p.scalar else f"to_string({slice_of(p)})"
        inputs_image = f'" inputs=" & to_string(ROWS(i)({total - 1} downto {total - in_bits}))' if in_bits else '""'
        checks.append(
            f"            assert {got} = {slice_of(p)}\n"
            f"                report \"MODEL_MISMATCH cycle=\" & integer'image(i) & \" port={p.name} expected=\" & {exp_image}\n"
            f"                    & \" got=\" & {image} & {inputs_image}\n"
            f"                severity error;"
        )
    if clock:
        step = "            wait until rising_edge(clk_tb);\n            wait for 1 ns;"
        clock_decl = (
            "    signal clk_tb : std_logic := '0';\n"
            "    signal done   : boolean := false;"
        )
        clock_gen = f"    clk_tb <= not clk_tb after {CLOCK_PERIOD_NS // 2} ns when not done else '0';\n"
        port_map = port_map.replace(f"{clock.name} => {clock.name}", f"{clock.name} => clk_tb")
        finish = "        done <= true;\n"
    else:
        step = f"            wait for {CLOCK_PERIOD_NS} ns;"
        clock_decl, clock_gen, finish = "", "", ""

    return f"""-- Automatisch erzeugt aus model/reference_model.py (differentieller Test, nicht bearbeiten).
-- Je Zeile: Eingänge, danach die vom Referenzmodell berechneten Ausgänge.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity {top}_model_tb is
end entity;

architecture sim of {top}_model_tb is
    type row_t is array (natural range <>) of std_logic_vector({total - 1} downto 0);
    constant ROWS : row_t := (
{(","+chr(10)).join(rows)}
    );
{clock_decl}
{signals}
begin
    dut: entity work.{top}
        port map (
{port_map}
        );
{clock_gen}
    stimulus: process
    begin
        for i in ROWS'range loop
{drive}
{step}
{chr(10).join(checks)}
        end loop;
        report "{_complete_marker()}" severity note;
{finish}        wait;
    end process;
end architecture;
"""


def _complete_marker() -> str:
    from src.infrastructure.validation.ghdl_validator import TB_COMPLETE_MARKER
    return TB_COMPLETE_MARKER


def model_testbench_path(top: str) -> str:
    return f"tests/{top}_model_tb.vhd"


def write_model_testbench(workspace: str, top: str, seed: int = 0) -> dict:
    """Erzeugt bzw. aktualisiert tests/<top>_model_tb.vhd. Liefert einen Status für design_state.

    status: "written" | "skipped" (kein/ungültiges Modell, nicht unterstützte Ports) | "model_error".
    Ein ungültiges Modell blockiert nichts; es fehlt dann nur der differentielle Test.
    """
    ws = Path(workspace)
    if not (ws / MODEL_FILE).is_file():
        return {"status": "skipped", "reason": "kein Referenzmodell vorhanden"}
    ports, reason = entity_ports(workspace, top)
    if ports is None:
        return {"status": "skipped", "reason": reason}
    ok, detail = run_selftest(workspace)
    if not ok:
        return {"status": "model_error", "reason": f"Selbsttest des Referenzmodells fehlgeschlagen: {detail}"}
    stimulus = generate_stimulus(ports, suggested_cycles(workspace), seed=seed)
    expected, error = run_model(workspace, ports, stimulus)
    if expected is None:
        return {"status": "model_error", "reason": f"Referenzmodell nicht ausführbar: {error}"}
    path = ws / model_testbench_path(top)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_model_testbench(top, ports, stimulus, expected), encoding="utf-8")
    return {"status": "written", "file": model_testbench_path(top), "cycles": len(stimulus), "selftest": detail}


def mismatch_line(output: str) -> str:
    """Erste MODEL_MISMATCH-Meldung aus einer Simulationsausgabe (für Diagnose und Reparatur)."""
    match = re.search(r"MODEL_MISMATCH[^\n]*", output or "")
    return match.group(0).strip() if match else ""
