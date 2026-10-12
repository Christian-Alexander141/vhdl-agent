"""Vergleich: einzelnes OpenCode vs. MAS (gleiches Modell, gleiches Abnahmekriterium).

Für jeden Prompt in benchmark/prompts/*.md laufen die gewählten Varianten:

  single      ein nativer OpenCode-Lauf auf dem ganzen Projekt
  mas         MAS mit modularer Implementierung (ein Worker je Modul)
  mas-single  MAS mit implementation_mode=single_session

Alle Varianten werden mit demselben GHDLValidator bewertet (analysieren,
elaborieren, jede tests/*_tb.vhd simulieren, TB_COMPLETE-Marker, keine
fehlgeschlagene Assertion). Synthese/Flash sind abgeschaltet: verglichen
wird die Simulationsreife. Ergebnisse, Metadaten und Code-Stand landen nach
jedem Lauf in docs/benchmark/ergebnisse/<zeitstempel>/ (Methodik siehe
docs/benchmark/METHODIK.md); die Workspaces außerhalb des Repos unter
~/vhdl-agent-benchmark/<zeitstempel>/; MAS-Fehlschläge werden grob nach der MAST-Taxonomie
(Cemri et al., arXiv:2503.13657) eingeordnet.

Aufruf (aus Schaltungsagent/):
  python -m benchmark.mas_vs_single --variants single mas mas-single --repeat 3
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.domain.agents.worker_instructions import SIM_STOP_TIME, TESTBENCH_RULES  # noqa: E402
from src.infrastructure.validation.ghdl_validator import GHDLValidator  # noqa: E402
from src.services.opencode_service import SubprocessOpenCodeService  # noqa: E402

# Grobe Zuordnung failure_type -> MAST-Kategorie. Heuristik, kein Ersatz für
# eine manuelle Annotation der Läufe.
MAST_CATEGORY = {
    "architecture_error": "specification",
    "target_ambiguous": "specification",
    "interface_mismatch": "inter_agent_misalignment",
    "contract_violation": "inter_agent_misalignment",
    "testbench_error": "inter_agent_misalignment",
    "coverage_gap": "task_verification",
    "functional_simulation_error": "task_verification",
    "logic_error": "task_verification",
    "syntax_error": "task_verification",
    "type_error": "task_verification",
    "elaboration_error": "task_verification",
    "clock_reset_error": "task_verification",
    "infrastructure": "infrastructure",
}

SINGLE_INSTRUCTION = (
    "Lies PROMPT.md vollständig und setze das Projekt komplett um: VHDL-2008-Quellen "
    "unter src/<entity>.vhd, mindestens eine Testbench unter tests/<entity>_tb.vhd, "
    "die das Top-Level prüft.\n"
    f"{TESTBENCH_RULES}\n"
    "Prüfe dein Ergebnis selbst mit GHDL (mkdir -p build/ghdl; ghdl -a --std=08 "
    "--workdir=build/ghdl <dateien>; ghdl -r --std=08 --workdir=build/ghdl <tb> "
    f"--stop-time={SIM_STOP_TIME} --assert-level=error) und behebe alle Fehler, bevor du endest."
)


def run_single(settings, prompt: str, workspace: Path) -> dict:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "PROMPT.md").write_text(prompt, encoding="utf-8")
    cfg = settings.opencode
    service = SubprocessOpenCodeService(
        binary=cfg.binary, model=cfg.model,
        default_timeout=cfg.default_timeout, fallback_model=cfg.fallback_model,
    )
    try:
        result = service.execute(str(workspace), SINGLE_INSTRUCTION)
        note = "" if result.success else (result.stderr or result.stdout or "")[-300:]
    except Exception as exc:  # Zeitlimit, Programm fehlt ...
        note = f"{type(exc).__name__}: {exc}"[:300]
    return {"workspace": str(workspace), "stage": "", "failure_type": "", "note": note}


def run_mas(settings, prompt: str, implementation_mode: str, projects_dir: Path,
            repair_policy: str = "standard") -> dict:
    from src.main import create_orchestrator

    settings.workspace.base_dir = str(projects_dir)
    # Benchmarks standardmäßig mit knappen Grenzen (Vergleichbarkeit); "persistent"
    # misst das Verhalten echter Läufe mit Eskalation.
    settings.opencode.repair_policy = repair_policy
    settings.opencode.test_mode = True
    settings.opencode.implementation_mode = implementation_mode
    settings.synthesis.enabled = False
    orchestrator = create_orchestrator(settings)
    try:
        result = orchestrator.execute(prompt, "vhdl")
    except Exception as exc:
        return {"workspace": "", "stage": "EXCEPTION", "failure_type": "infrastructure",
                "note": f"{type(exc).__name__}: {exc}"[:300]}
    workspace = Path(orchestrator._fs.workspace_path(result["task_id"]))
    stage, failure_type = "", ""
    state_file = workspace / "design_state.yaml"
    if state_file.is_file():
        state = yaml.safe_load(state_file.read_text()) or {}
        stage = str(state.get("current_stage", ""))
        history = (state.get("diagnostics") or {}).get("history") or []
        failure_type = next((d.get("failure_type") for d in history if d and d.get("failure_type")), "")
    return {"workspace": str(workspace), "stage": stage, "failure_type": failure_type,
            "note": (result.get("error_message") or "")[:300]}


REFERENCE_DIR = ROOT / "benchmark" / "reference"


def reference_check(workspace: str, prompt_stem: str, scratch: Path, ghdl: str = "ghdl") -> tuple[bool | None, str]:
    """Prüft den erzeugten Entwurf (nur src/) gegen eine unabhängige Referenz-Testbench.

    Die Referenz-Testbenches liegen außerhalb jedes Workspaces und werden dem
    System nie gezeigt. Damit misst der Benchmark nicht nur, ob die vom
    System selbst geschriebene Testbench besteht, sondern ob der Entwurf die
    Spezifikation erfüllt. None = keine Referenz für diesen Prompt.
    """
    ref = REFERENCE_DIR / f"{prompt_stem}_ref_tb.vhd"
    src = Path(workspace) / "src" if workspace else None
    if not ref.is_file():
        return None, "keine Referenz-Testbench"
    sources = sorted(src.glob("*.vhd")) if src and src.is_dir() else []
    if not sources:
        return False, "keine Quelldateien in src/"
    entity = re.search(r"\bentity\s+(\w+)\s+is\b", ref.read_text(), re.IGNORECASE).group(1)
    workdir = scratch / f"ref_{prompt_stem}_{datetime.now().strftime('%H%M%S%f')}"
    workdir.mkdir(parents=True)
    std = ["--std=08", f"--workdir={workdir}"]
    steps = [
        [ghdl, "-i", *std, *map(str, sources), str(ref)],
        [ghdl, "-m", *std, entity],
        [ghdl, "-r", *std, entity, "--stop-time=1ms", "--assert-level=error"],
    ]
    output = ""
    for cmd in steps:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir, timeout=300)
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            first = next((line for line in output.splitlines() if "REF_FAIL" in line or "error" in line.lower()), output[-200:])
            return False, f"{cmd[1]}: {first.strip()[:200]}"
    if "REF_FAIL" in output or "TB_COMPLETE" not in output:
        return False, "Referenz-Simulation unvollständig"
    return True, "Referenz-Testbench bestanden"


def provider_ok(settings, scratch: Path, timeout: int = 120) -> tuple[bool, str]:
    """Kurze Testanfrage an das Modell: ist der Provider gerade erreichbar?

    Im Lauf 20261008-161755 fiel der Provider des Gratis-Modells ab ~18:00
    aus ([502] Upstream error from Nvidia). OpenCode wartete still bis zum
    Zeitlimit; 15 von 18 Läufen waren dadurch wertlos und kosteten 10 h.
    """
    scratch.mkdir(parents=True, exist_ok=True)
    cfg = settings.opencode
    service = SubprocessOpenCodeService(
        binary=cfg.binary, model=cfg.model, default_timeout=timeout, fallback_model=cfg.model,
    )
    try:
        result = service.execute(str(scratch), "Antworte nur mit dem Wort OK.", timeout_seconds=timeout)
    except Exception as exc:
        return False, f"{type(exc).__name__}"
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0 and "OK" in output.upper():
        return True, "ok"
    return False, (output.strip().splitlines() or ["keine Antwort"])[-1][:120]


def wait_for_provider(settings, scratch: Path, max_wait_min: int) -> bool:
    deadline = time.monotonic() + max_wait_min * 60
    while True:
        ok, detail = provider_ok(settings, scratch)
        if ok:
            return True
        if time.monotonic() >= deadline:
            print(f"PROVIDER_DOWN seit über {max_wait_min} min ({detail}) – Benchmark wird beendet", flush=True)
            return False
        print(f"PROVIDER_DOWN ({detail}) – neuer Versuch in 10 min", flush=True)
        time.sleep(600)


FIELDS = [
    "round", "prompt", "variant", "model", "passed", "validator", "ref_passed", "ref_detail", "duration_s",
    "final_stage", "failure_type", "mast_category", "started_at", "workspace", "note",
    "provider_ok_after", "valid",
]


def _tool_version(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception as exc:  # Werkzeug fehlt o. Ä.
        return f"unbekannt ({exc})"


def _code_state() -> dict:
    """Identifiziert den Code-Stand exakt, auch mit nicht committeten Änderungen."""
    repo = ROOT.parent
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True).stdout.strip()
    dirty = [line[3:] for line in git("status", "--porcelain", "--", "Schaltungsagent", "config.yaml").splitlines()]
    files = {}
    for rel in dirty:
        path = repo / rel
        if path.is_file():
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return {"head": git("rev-parse", "HEAD"), "uncommitted_files": files}


def _summary(rows: list[dict], variants: list[str]) -> dict:
    """Quoten nur über gültige Läufe (Provider vor und nach dem Lauf erreichbar)."""
    summary = {}
    for variant in variants:
        invalid = sum(1 for r in rows if r["variant"] == variant and not r.get("valid", True))
        runs = [r for r in rows if r["variant"] == variant and r.get("valid", True)]
        per_prompt = {}
        for r in runs:
            entry = per_prompt.setdefault(r["prompt"], {"runs": 0, "passed": 0, "ref_passed": 0})
            entry["runs"] += 1
            entry["passed"] += int(r["passed"])
            entry["ref_passed"] += int(r.get("ref_passed") is True)
        summary[variant] = {
            "runs": len(runs),
            "invalid_runs_excluded": invalid,
            "passed": sum(r["passed"] for r in runs),
            "pass_rate": round(sum(r["passed"] for r in runs) / len(runs), 3) if runs else 0.0,
            "ref_passed": sum(1 for r in runs if r.get("ref_passed") is True),
            "ref_pass_rate": round(sum(1 for r in runs if r.get("ref_passed") is True) / len(runs), 3) if runs else 0.0,
            "mean_duration_s": round(sum(r["duration_s"] for r in runs) / len(runs), 1) if runs else 0.0,
            "per_prompt": per_prompt,
            "mast": {c: sum(1 for r in runs if r["mast_category"] == c)
                     for c in sorted({r["mast_category"] for r in runs if r["mast_category"]})},
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--prompts", default=str(ROOT / "benchmark" / "prompts"))
    parser.add_argument("--prompt-files", nargs="+", default=None,
                        help="Prompt-Dateinamen in gewünschter Reihenfolge (Standard: alle, alphabetisch)")
    parser.add_argument("--variants", nargs="+", default=["single", "mas", "mas-single"],
                        choices=["single", "mas", "mas-single"])
    parser.add_argument("--repeat", type=int, default=1, help="Runden; jede Runde führt jeden Prompt in jeder Variante aus")
    parser.add_argument("--out", default=str(Path.home() / "vhdl-agent-benchmark"),
                        help="Ablage der Workspaces; muss außerhalb jedes Git-Repos liegen")
    parser.add_argument("--opencode-timeout", type=int, default=0,
                        help="Zeitlimit je OpenCode-Aufruf in Sekunden (0 = opencode.default_timeout aus config.yaml); "
                             "für die Variante single, die die ganze Aufgabe in einem Aufruf lösen muss")
    parser.add_argument("--max-provider-wait", type=int, default=120,
                        help="Minuten, die auf einen ausgefallenen Modell-Provider gewartet wird, bevor der Benchmark endet")
    parser.add_argument("--results-dir", default=str(ROOT.parent / "docs" / "benchmark" / "ergebnisse"),
                        help="Ablage von Ergebnissen und Metadaten (versionierbar)")
    args = parser.parse_args()

    prompt_dir = Path(args.prompts)
    prompts = ([prompt_dir / name for name in args.prompt_files] if args.prompt_files
               else sorted(prompt_dir.glob("*.md")))
    missing = [str(p) for p in prompts if not p.is_file()]
    if not prompts or missing:
        sys.exit(f"Prompts fehlen: {missing or prompt_dir}")
    out_root = Path(args.out).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    # Nativ ist OpenCode nur außerhalb eines Git-Repos auf den Workspace
    # begrenzt (siehe ensure_native_guard); ein erster Lauf im Repo hat sich
    # dort umgesehen und Dateien unter halluzinierten Pfaden angelegt.
    inside_repo = subprocess.run(
        ["git", "-C", str(out_root), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if inside_repo.returncode == 0:
        sys.exit(f"--out {out_root} liegt im Git-Repo {inside_repo.stdout.strip()}; bitte einen Ordner außerhalb wählen")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = out_root / run_id
    out_dir.mkdir(parents=True)
    results_dir = Path(args.results_dir) / run_id
    results_dir.mkdir(parents=True)
    probe = load_config()
    if not shutil.which(probe.opencode.binary) or not shutil.which(probe.ghdl.binary):
        sys.exit("opencode und ghdl müssen nativ im PATH liegen")
    validator = GHDLValidator(ghdl_binary=probe.ghdl.binary, timeout_seconds=probe.ghdl.timeout_seconds)

    meta = {
        "run_id": run_id,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "command": " ".join(sys.argv),
        "variants": args.variants,
        "rounds": args.repeat,
        "prompts": {p.stem: hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in prompts},
        "model": probe.opencode.model,
        "fallback_model": probe.opencode.fallback_model,
        "opencode_timeout_s": args.opencode_timeout or probe.opencode.default_timeout,
        "max_repair_iterations": probe.opencode.max_repair_iterations,
        "opencode_version": _tool_version([probe.opencode.binary, "--version"]),
        "ghdl_version": _tool_version([probe.ghdl.binary, "--version"]),
        "acceptance": "GHDLValidator: analysieren, elaborieren, jede tests/*_tb.vhd mit --stop-time=1ms "
                      "--assert-level=error simulieren; TB_COMPLETE vorhanden; keine fehlgeschlagene Assertion",
        "reference_acceptance": "unabhängige Referenz-Testbench je Prompt (benchmark/reference), nur gegen src/*.vhd",
        "reference_testbenches": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                                  for p in sorted(REFERENCE_DIR.glob("*_ref_tb.vhd"))},
        "workspaces": str(out_dir),
        "code_state": _code_state(),
    }
    (results_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    csv_path = results_dir / "results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writeheader()

    rows = []
    # Runden außen, Varianten innen: Tageszeit- und Rate-Limit-Effekte des
    # Providers verteilen sich gleichmäßig auf alle Varianten, und ein
    # Abbruch hinterlässt ausgewogene Teilergebnisse.
    for rnd in range(1, args.repeat + 1):
        for prompt_file in prompts:
            prompt = prompt_file.read_text(encoding="utf-8")
            for variant in args.variants:
                settings = load_config()  # frisch je Lauf, MAS verändert die Settings
                if args.opencode_timeout:
                    settings.opencode.default_timeout = args.opencode_timeout
                if not wait_for_provider(settings, out_dir / "_health", args.max_provider_wait):
                    meta["aborted"] = "Modell-Provider nicht erreichbar"
                    meta["finished_at"] = datetime.now().isoformat(timespec="seconds")
                    (results_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
                    sys.exit(2)
                started_at = datetime.now().isoformat(timespec="seconds")
                started = time.monotonic()
                if variant == "single":
                    info = run_single(settings, prompt, out_dir / f"{prompt_file.stem}-single-{rnd}")
                else:
                    info = run_mas(settings, prompt, "single_session" if variant == "mas-single" else "modular",
                                   out_dir / "mas-projects")
                duration = time.monotonic() - started
                check = validator.validate(info["workspace"]) if info["workspace"] else None
                provider_after, _ = provider_ok(settings, out_dir / "_health")
                ref_passed, ref_detail = reference_check(
                    info["workspace"], prompt_file.stem, out_dir / "_refcheck", probe.ghdl.binary,
                )
                row = {
                    "round": rnd,
                    "prompt": prompt_file.stem,
                    "variant": variant,
                    "model": settings.opencode.model,
                    "passed": bool(check and check.passed),
                    "validator": (check.message if check else "kein Workspace")[:200],
                    "ref_passed": "" if ref_passed is None else ref_passed,
                    "ref_detail": ref_detail,
                    "duration_s": round(duration, 1),
                    "final_stage": info["stage"],
                    "failure_type": info["failure_type"],
                    "mast_category": "" if check and check.passed else MAST_CATEGORY.get(info["failure_type"], ""),
                    "started_at": started_at,
                    "workspace": info["workspace"],
                    "note": info["note"].replace("\n", " "),
                    "provider_ok_after": provider_after,
                    # Fehlgeschlagen und Provider danach nicht erreichbar: der
                    # Lauf misst den Ausfall, nicht die Variante.
                    "valid": provider_after or bool(check and check.passed) or ref_passed is True,
                }
                rows.append(row)
                with open(csv_path, "a", newline="", encoding="utf-8") as f:
                    csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
                (results_dir / "summary.json").write_text(
                    json.dumps(_summary(rows, args.variants), indent=2, ensure_ascii=False))
                print(f"R{rnd} {row['prompt']:<22} {variant:<11} {'PASS' if row['passed'] else 'FAIL'}  "
                      f"{'' if row['valid'] else '[UNGÜLTIG: Provider-Ausfall] '}"
                      f"REF={'PASS' if ref_passed else '-' if ref_passed is None else 'FAIL'}  "
                      f"{row['duration_s']:>7}s  {row['failure_type'] or row['validator'][:60]}", flush=True)

    meta["finished_at"] = datetime.now().isoformat(timespec="seconds")
    (results_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(json.dumps(_summary(rows, args.variants), indent=2, ensure_ascii=False))
    print(f"Ergebnisse: {results_dir}")


if __name__ == "__main__":
    main()
