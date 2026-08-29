import os
import re
import shlex
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from src.config import load_config

EDA_TOOLS = [
    {"id": "modelsim", "name": "ModelSim", "binary": "vsim"},
    {"id": "vivado", "name": "Vivado", "binary": "vivado"},
    {"id": "quartus", "name": "Quartus", "binary": "quartus"},
]

EXCLUDED_DIRS = {"build", "logs", "reports", ".venv", "node_modules", "__pycache__"}

# Bekannte Installationsordner für ModelSim unter einem Wine-Prefix.
_WINE_MODELSIM_DIRS = (
    "ModelSim", "ModelSimSE", "modeltech", "MentorGraphics", "IntelFPGA", "intelFPGA",
)


@lru_cache(maxsize=1)
def _modelsim_settings():
    try:
        return load_config().eda_tools
    except Exception:
        return None


def detect_eda_tools():
    tools = []
    for t in EDA_TOOLS:
        installed = shutil.which(t["binary"]) is not None
        if t["id"] == "modelsim":
            installed = _resolve_modelsim() is not None
        elif t["id"] == "vivado" and not installed:
            # Check config for full path
            try:
                cfg = load_config()
                if cfg.vivado.binary and Path(cfg.vivado.binary).is_file():
                    installed = True
            except Exception:
                pass
        tools.append({
            "id": t["id"],
            "name": t["name"],
            "binary": t["binary"],
            "installed": installed,
        })
    return tools


@lru_cache(maxsize=1)
def _resolve_modelsim():
    """Ermittelt das ModelSim-Binary inklusive Wine-Wrapper.

    Auflösungsreihenfolge:
    1. Konfiguration eda_tools.modelsim_binary
    2. Umgebungsvariable MODELSIM_BIN
    3. vsim / vsim.exe direkt im PATH
    4. Suche von vsim.exe unter dem Wine-Prefix (WINEPREFIX bzw. ~/.wine)

    Rückgabe: (command, workdir) — command ist z. B. ["wine", "<...>/vsim.exe"]
    für Windows-Binaries oder ["<...>/vsim"] für native Installationen.
    """
    cfg = _modelsim_settings()
    candidates = []
    if cfg and cfg.modelsim_binary:
        candidates.append(Path(cfg.modelsim_binary).expanduser())
    if os.environ.get("MODELSIM_BIN"):
        candidates.append(Path(os.environ["MODELSIM_BIN"]).expanduser())
    for candidate in candidates:
        resolved = _command_for_binary(candidate)
        if resolved:
            return resolved
    direct = shutil.which("vsim")
    if direct:
        return _command_for_binary(Path(direct))
    exe = shutil.which("vsim.exe")
    if exe:
        return _command_for_binary(Path(exe))
    found = _search_vsim_in_wine()
    if found:
        return _command_for_binary(found)
    return None


def _command_for_binary(bin_path: Path):
    if not bin_path or not bin_path.is_file():
        return None
    cmd = [str(bin_path)]
    if bin_path.suffix.lower() == ".exe":
        cfg = _modelsim_settings()
        wine_cmd = (cfg.modelsim_wine if cfg and cfg.modelsim_wine else "wine")
        if shutil.which(wine_cmd) is None:
            return None
        cmd = [wine_cmd] + cmd
    return (cmd, bin_path.parent)


def _search_vsim_in_wine():
    prefixes = []
    if os.environ.get("WINEPREFIX"):
        prefixes.append(Path(os.environ["WINEPREFIX"]))
    prefixes.append(Path.home() / ".wine")
    for prefix in prefixes:
        drive_c = prefix / "drive_c"
        if not drive_c.is_dir():
            continue
        for top in _WINE_MODELSIM_DIRS:
            base = drive_c / top
            if not base.is_dir():
                continue
            try:
                for f in base.rglob("vsim.exe"):
                    return f
            except OSError:
                pass
        try:
            for entry in drive_c.iterdir():
                name = entry.name.lower()
                if entry.is_dir() and ("modelsim" in name or "modeltech" in name):
                    for f in entry.rglob("vsim.exe"):
                        return f
        except OSError:
            pass
    return None


def _wine_path(path: Path) -> str:
    """Übersetzt einen Linux-Pfad in einen Windows-Pfad (z. B. Z:\\...)."""
    winepath = shutil.which("winepath")
    if winepath:
        try:
            result = subprocess.run(
                [winepath, "-w", str(path)],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return str(path)


def _tcl_quote(value: str) -> str:
    """Quoted einen Pfad für das ModelSim-Tcl-Skript (Doppelpunkte/Backslashes
    in Windows-Pfaden sind kein Problem, Leerzeichen schon)."""
    if any(c in value for c in " \t{}[]$\\"):
        return "{" + value.replace("}", r"\}") + "}"
    return value


def _find_vhdl_files(project_dir: Path):
    files = []
    for ext in ("*.vhd", "*.vhdl"):
        for f in project_dir.rglob(ext):
            if not any(part in EXCLUDED_DIRS for part in f.parts):
                files.append(f)
    return sorted(set(files))


def _extract_entity(vhd_file: Path):
    try:
        text = vhd_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"\bentity\s+(\w+)\s+is", text, re.IGNORECASE)
    return match.group(1) if match else None


def _find_testbench(vhdl_files):
    tb_candidates = [f for f in vhdl_files if "tb" in f.name.lower()]
    if tb_candidates:
        return tb_candidates[0]
    test_candidates = [f for f in vhdl_files if f.parent.name in ("tests", "test")]
    if test_candidates:
        return test_candidates[0]
    return None


def _launch(cmd, cwd: Path):
    subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _open_modelsim(project_dir: Path, vhdl_files, tb_file):
    resolved = _resolve_modelsim()
    if resolved is None:
        return False, (
            "ModelSim (vsim/vsim.exe) wurde nicht gefunden. Pfad in config.yaml "
            "unter eda_tools.modelsim_binary angeben oder MODELSIM_BIN setzen."
        )
    cmd, workdir = resolved
    use_wine = cmd[0].lower().endswith("wine") or ".exe" in cmd[0].lower()
    path_for_ms = (lambda p: _wine_path(p)) if use_wine else (lambda p: str(p))

    build_dir = project_dir / "build"
    build_dir.mkdir(exist_ok=True)
    tb_entity = _extract_entity(tb_file) if tb_file else None
    lines = [
        f"cd {_tcl_quote(path_for_ms(build_dir))}",
        "onerror {resume}",
        "vlib work",
        "vmap work work",
    ]
    lines += [f"vcom -2008 {_tcl_quote(path_for_ms(f))}" for f in vhdl_files]
    if tb_entity:
        lines.append(f"vsim -gui work.{tb_entity} -t 1ns")
        lines.append("add wave -r /*")
        lines.append("run -all")
    else:
        lines.append("vsim -gui")
    script = build_dir / "run_modelsim.do"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _launch(cmd + ["-gui", "-do", f"do {_tcl_quote(path_for_ms(script))}"], cwd=workdir)
    return True, "ModelSim wurde mit dem Projekt gestartet."


def _open_vivado(project_dir: Path, vhdl_files, tb_file):
    tcl_dir = project_dir / "build" / "vivado"
    tcl_dir.mkdir(parents=True, exist_ok=True)
    tb_entity = _extract_entity(tb_file) if tb_file else None
    files_list = " ".join(shlex.quote(str(f)) for f in vhdl_files)
    lines = [
        f"create_project {shlex.quote(project_dir.name)} ./vivado_proj -force",
        f"add_files -norecurse [list {files_list}]",
    ]
    if tb_entity:
        lines.append(f"set_property top {tb_entity} [current_fileset]")
    lines.append("close_project")
    script = tcl_dir / "open_project.tcl"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    vivado = shutil.which("vivado")
    if vivado is None:
        # Try full path from config
        try:
            cfg = load_config()
            vivado = cfg.vivado.binary
            if not Path(vivado).is_file():
                vivado = None
        except Exception:
            vivado = None
    if vivado is None:
        return False, "Vivado ist nicht installiert oder nicht erreichbar."
    _launch([vivado, "-mode", "gui", "-source", str(script)], cwd=tcl_dir)
    return True, "Vivado wurde mit dem Projekt gestartet."


def _open_quartus(project_dir: Path, vhdl_files, tb_file):
    tcl_dir = project_dir / "build" / "quartus"
    tcl_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "package require ::quartus::project",
        f"project_new {shlex.quote(project_dir.name)} -overwrite",
    ]
    lines += [f"set_global_assignment -name VHDL_FILE {shlex.quote(str(f))}" for f in vhdl_files]
    lines.append("project_close")
    script = tcl_dir / "create_project.tcl"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    quartus_sh = shutil.which("quartus_sh")
    if quartus_sh is None:
        return False, "quartus_sh ist nicht installiert."
    try:
        result = subprocess.run(
            [quartus_sh, "-t", str(script)],
            cwd=str(tcl_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"quartus_sh konnte nicht ausgeführt werden: {e}"
    qpf = tcl_dir / f"{project_dir.name}.qpf"
    if result.returncode != 0 or not qpf.exists():
        return False, f"Quartus-Projekt konnte nicht erstellt werden:\n{result.stderr[-500:]}"
    quartus = shutil.which("quartus")
    _launch([quartus, "--64bit", str(qpf)], cwd=tcl_dir)
    return True, "Quartus wurde mit dem Projekt gestartet."


def open_project_in_tool(tool_id: str, project_dir: Path):
    if not project_dir.is_dir():
        return False, "Projektverzeichnis nicht gefunden."
    vhdl_files = _find_vhdl_files(project_dir)
    if not vhdl_files:
        return False, "Keine VHDL-Dateien im Projekt gefunden."
    tb_file = _find_testbench(vhdl_files)
    if tool_id == "modelsim":
        if _resolve_modelsim() is None:
            return False, (
                "ModelSim (vsim/vsim.exe) wurde nicht gefunden. Pfad in config.yaml "
                "unter eda_tools.modelsim_binary angeben oder MODELSIM_BIN setzen."
            )
        return _open_modelsim(project_dir, vhdl_files, tb_file)
    if tool_id == "vivado":
        vivado = shutil.which("vivado")
        if vivado is None:
            try:
                cfg = load_config()
                vivado = cfg.vivado.binary
                if not Path(vivado).is_file():
                    return False, "Vivado ist nicht installiert."
            except Exception:
                return False, "Vivado ist nicht installiert."
        return _open_vivado(project_dir, vhdl_files, tb_file)
    if tool_id == "quartus":
        if shutil.which("quartus") is None:
            return False, "Quartus ist nicht installiert."
        return _open_quartus(project_dir, vhdl_files, tb_file)
    return False, f"Unbekanntes Tool: {tool_id}"
