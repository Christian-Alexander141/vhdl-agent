"""Modellvergleich auf small_vhdl_bench: ein einzelner OpenCode-Lauf je Aufgabe und Modell.

Jedes Modell löst jede der 10 Aufgaben aus benchmark/small_vhdl_bench-main
in einem eigenen nativen OpenCode-Lauf. Bewertet wird mit evaluate() des
Benchmarks (regelbasiert, 0–100 Punkte, bestanden ab 70). Methodik:
docs/benchmark/METHODIK.md, Abschnitt 11.

Aufruf (aus Schaltungsagent/):
  python -m benchmark.small_bench_models --models opencode/muse-spark-1.3-contributor-free ... --run-id <id>
  python -m benchmark.small_bench_models --summarize --run-id <id>
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmark" / "small_vhdl_bench-main"))

import re  # noqa: E402

from bench.benchmark_api import evaluate, get_prompt, list_tasks  # noqa: E402
from benchmark.mas_vs_single import _code_state  # noqa: E402
from src.services.opencode_service import SubprocessOpenCodeService  # noqa: E402

# Provider-Ausfall in der Ausgabe eines Laufs: der Lauf misst den Ausfall, nicht das Modell
# (beobachtet: "[503] Upstream error from Nvidia: Service temporarily unavailable").
PROVIDER_ERROR = re.compile(
    r"upstream error|rate.?limit|\[50[234]\]|service temporarily|AI_RetryError|"
    r"kontingent bzw\. rate-limit|serverfehler beim modell-provider", re.IGNORECASE,
)

RESULTS_ROOT = ROOT.parent / "docs" / "benchmark" / "ergebnisse"
WORK_ROOT = Path.home() / "vhdl-agent-benchmark"
TIMEOUT_S = 1800
FIELDS = ["variant", "model", "task", "titel", "score", "bestanden", "duration_s", "files", "xdc_source",
          "final_stage", "failure_type", "provider_ok_after", "valid", "note", "started_at", "workspace"]

INSTRUCTION = (
    "Lies PROMPT.md vollständig und setze die Aufgabe um. Schreibe alle VHDL-Dateien nach src/ "
    "(Testbenches, falls die Aufgabe welche verlangt, nach tests/) und die Constraints nach "
    "constraints/arty_s7.xdc. Prüfe jede VHDL-Datei mit 'ghdl -a --std=08 <datei>' auf Fehler "
    "und behebe sie, bevor du endest."
)


def provider_ok(model: str, scratch: Path) -> bool:
    scratch.mkdir(parents=True, exist_ok=True)
    service = SubprocessOpenCodeService(binary="opencode", model=model, default_timeout=120, fallback_model=model)
    try:
        result = service.execute(str(scratch), "Antworte nur mit dem Wort OK.", timeout_seconds=120)
    except Exception:
        return False
    return result.returncode == 0 and "OK" in ((result.stdout or "") + (result.stderr or "")).upper()


def collect(workspace: Path) -> tuple[dict, str]:
    """VHDL-Dateien für evaluate(); Testbenches unter dem Schlüssel tb_<name>.

    evaluate() nimmt nur Dateien mit Präfix 'tb_' vom Verbot von
    Simulationskonstrukten aus; Modelle benennen Testbenches meist '*_tb.vhd'.
    """
    vhdl = {}
    for path in sorted(workspace.rglob("*.vhd")):
        if any(part.startswith(".") for part in path.relative_to(workspace).parts):
            continue
        rel = path.relative_to(workspace)
        name = path.name
        is_tb = rel.parts[0] == "tests" or "_tb" in path.stem.lower() or path.stem.lower().startswith("tb_")
        key = name if not is_tb or name.lower().startswith("tb_") else f"tb_{name}"
        vhdl[key] = path.read_text(errors="replace")
    xdc = "\n".join(p.read_text(errors="replace") for p in sorted(workspace.rglob("*.xdc"))
                    if not any(part.startswith(".") for part in p.relative_to(workspace).parts))
    return vhdl, xdc


def _mas_xdc(workspace: Path) -> str:
    """XDC so, wie das MAS sie in seiner Synthesephase erzeugt (ohne Vivado zu starten)."""
    from src.infrastructure.synthesis.vivado_synthesis import VivadoBitstreamService

    state = workspace / "design_state.yaml"
    top = ""
    if state.is_file():
        import yaml
        top = ((yaml.safe_load(state.read_text()) or {}).get("architecture") or {}).get("top_module", "")
    sources = sorted((workspace / "src").glob("*.vhd"))
    if not top or not sources:
        return ""
    service = VivadoBitstreamService(vivado_binary="vivado")
    return service._generatexdc_for_board(top, sources, "arty_s7_50", 100_000_000) or ""


def run_task_single(model: str, task_id: str, workspace: Path) -> dict:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "PROMPT.md").write_text(get_prompt(task_id), encoding="utf-8")
    note = ""
    service = SubprocessOpenCodeService(binary="opencode", model=model, default_timeout=TIMEOUT_S, fallback_model=model)
    try:
        result = service.execute(str(workspace), INSTRUCTION, timeout_seconds=TIMEOUT_S)
        if result.returncode != 0 or PROVIDER_ERROR.search(result.stdout or ""):
            note = (result.stdout or result.stderr or "")[-300:]
    except Exception as exc:
        note = f"{type(exc).__name__}: {exc}"[:300]
    vhdl, xdc = collect(workspace)
    return {"workspace": workspace, "vhdl": vhdl, "xdc": xdc, "xdc_source": "modell" if xdc else "",
            "final_stage": "", "failure_type": "", "note": note}


def run_task_mas(model: str, task_id: str, projects_dir: Path) -> dict:
    from benchmark.mas_vs_single import run_mas
    from src.config import load_config

    settings = load_config()
    settings.opencode.model = model
    settings.opencode.fallback_model = model
    info = run_mas(settings, get_prompt(task_id), "modular", projects_dir)
    workspace = Path(info["workspace"]) if info["workspace"] else None
    vhdl, xdc, source = {}, "", ""
    if workspace and workspace.is_dir():
        vhdl, xdc = collect(workspace)
        source = "modell" if xdc else ""
        if not xdc:
            xdc = _mas_xdc(workspace)
            source = "mas-auto" if xdc else ""
    return {"workspace": workspace or "", "vhdl": vhdl, "xdc": xdc, "xdc_source": source,
            "final_stage": info["stage"], "failure_type": info["failure_type"], "note": info["note"]}


def run_model(model: str, run_id: str, tasks: list[str], variant: str = "single") -> None:
    short = model.split("/")[-1]
    out_dir = RESULTS_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"results_{variant}_{short}.csv"
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()
    work = WORK_ROOT / run_id / f"{variant}_{short}"
    titles = {t["id"]: t["titel"] for t in list_tasks()}
    for task_id in tasks:
        health = work / "_health"
        waited = 0
        while not provider_ok(model, health):
            if waited >= 120:
                print(f"{short}: Provider seit 2 h nicht erreichbar, Abbruch", flush=True)
                return
            print(f"{short}: Provider nicht erreichbar, neuer Versuch in 10 min", flush=True)
            time.sleep(600)
            waited += 10
        started_at = datetime.now().isoformat(timespec="seconds")
        started = time.monotonic()
        if variant == "mas":
            info = run_task_mas(model, task_id, work / "mas-projects")
        else:
            info = run_task_single(model, task_id, work / task_id)
        duration = time.monotonic() - started
        verdict = (evaluate(task_id, info["vhdl"], info["xdc"] or None) if info["vhdl"]
                   else {"score": 0.0, "bestanden": False})
        after = provider_ok(model, health)
        provider_error = bool(PROVIDER_ERROR.search(info["note"] or ""))
        row = {
            "variant": variant, "model": short, "task": task_id, "titel": titles.get(task_id, ""),
            "score": verdict["score"], "bestanden": verdict["bestanden"],
            "duration_s": round(duration, 1), "files": len(info["vhdl"]), "xdc_source": info["xdc_source"],
            "final_stage": info["final_stage"], "failure_type": info["failure_type"],
            "provider_ok_after": after,
            # Durchgefallen mit Provider-Fehler oder Provider danach weg: misst den Ausfall, nicht das Modell.
            "valid": verdict["bestanden"] or (after and not provider_error),
            "note": (info["note"] or "").replace("\n", " ")[:300], "started_at": started_at,
            "workspace": str(info["workspace"]),
        }
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
        print(f"{variant:<6} {short:<34} {task_id} {row['score']:>5} {'PASS' if row['bestanden'] else 'FAIL'} "
              f"{row['duration_s']:>7}s{'' if row['valid'] else ' [UNGÜLTIG: Provider]'}", flush=True)


def summarize(run_id: str) -> dict:
    out_dir = RESULTS_ROOT / run_id
    summary = {}
    for csv_path in sorted(out_dir.glob("results_*.csv")):
        rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
        valid = [r for r in rows if r["valid"] == "True"]
        summary[csv_path.stem.removeprefix("results_")] = {
            "runs": len(rows),
            "valid_runs": len(valid),
            "passed": sum(r["bestanden"] == "True" for r in valid),
            "mean_score": round(sum(float(r["score"]) for r in valid) / len(valid), 1) if valid else 0.0,
            "mean_duration_s": round(sum(float(r["duration_s"]) for r in valid) / len(valid), 1) if valid else 0.0,
            "per_task": {r["task"]: float(r["score"]) for r in valid},
        }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", default=[])
    parser.add_argument("--tasks", nargs="+", default=[t["id"] for t in list_tasks()])
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S") + "-small_vhdl_bench")
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--variant", choices=["single", "mas"], default="single")
    parser.add_argument("--compare-with", default="", help="Lauf-ID der Vergleichsbasis (z. B. Einzel-OpenCode)")
    args = parser.parse_args()
    if args.summarize:
        print(json.dumps(summarize(args.run_id), indent=2, ensure_ascii=False))
        return
    out_dir = RESULTS_ROOT / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    if not meta_path.exists():
        bench = ROOT / "benchmark" / "small_vhdl_bench-main" / "bench"
        meta = {
            "run_id": args.run_id,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "benchmark": "small_vhdl_bench (Projektautor), 10 Aufgaben, evaluate(): regelbasiert, bestanden ab 70",
            "benchmark_files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                                       for p in (bench / "tasks.json", bench / "benchmark_api.py")},
            "variants": "single = ein nativer OpenCode-Lauf je Aufgabe; mas = vollständiges MAS (modular, ohne Synthese, XDC wie in der Synthesephase des MAS erzeugt)",
            "instruction": INSTRUCTION,
            "timeout_s": TIMEOUT_S,
            "opencode_version": subprocess.run(["opencode", "--version"], capture_output=True, text=True).stdout.strip(),
            "git_head": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
            "code_state": _code_state(),
            "python": sys.version.split()[0],
            "compare_with": args.compare_with,
            "order": "Modelle nacheinander (eines zur Zeit), Aufgaben task01..task10; schont das Gratis-Kontingent",
            "workspaces": str(WORK_ROOT / args.run_id),
            "testbench_mapping": "Dateien unter tests/ oder mit '_tb' im Namen gehen als 'tb_<name>' an evaluate()",
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    for model in args.models:
        run_model(model, args.run_id, args.tasks, args.variant)


if __name__ == "__main__":
    main()
