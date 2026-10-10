#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_ROOT = os.path.join(ROOT_DIR, "Schaltungsagent")
VENV_DIR = os.path.join(ROOT_DIR, ".venv")
VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python")
INSTALLER = os.path.join(ROOT_DIR, "installer", "installer.py")

REQUIRED_COMMANDS = ["docker", "opencode", "ghdl", "git"]
CORE_MODULES = [
    "pydantic",
    "fastapi",
    "uvicorn",
    "yaml",
    "dotenv",
    "httpx",
]

def test_mode_enabled():
    return (
        os.environ.get("VHDL_AGENT_TEST_MODE", "").lower() in {"1", "true", "yes", "on"}
        or "--test-mode" in sys.argv
    )

def has_command(name):
    return shutil.which(name) is not None

def has_venv():
    if not os.path.isfile(VENV_PYTHON):
        return False
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-c", "import " + ",".join(CORE_MODULES)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except OSError:
        return False


def missing_components():
    missing = []
    required_commands = [cmd for cmd in REQUIRED_COMMANDS if not (test_mode_enabled() and cmd == "docker")]
    for cmd in required_commands:
        if not has_command(cmd):
            missing.append(cmd)
    # docker compose wird nur für den Isolationsmodus "shared" gebraucht
    # (docker compose up -d opencode); "per_task" benötigt nur docker.
    if not has_venv():
        missing.append("Python venv (Abhängigkeiten)")
    return missing

def ask_start_installer():
    while True:
        answer = input("Soll der Installer gestartet werden? [y/n]: ").strip().lower()
        if answer == "y":
            return True
        if answer == "n":
            return False
        print("Bitte 'y' oder 'n' eingeben.")

def run_installer():
    print("\n[INFO] Starte Installer...")
    subprocess.call([sys.executable, INSTALLER])

def check_components():
    missing = missing_components()
    if not missing:
        print("[OK] Alle Komponenten sind installiert.")
        return

    print("Folgende Komponenten fehlen:")
    for item in missing:
        print(f"  - {item}")

    if ask_start_installer():
        run_installer()
        still_missing = missing_components()
        if still_missing:
            print("\n[WARNUNG] Nach der Installation fehlen weiterhin:")
            for item in still_missing:
                print(f"  - {item}")
    else:
        print("\nInstallation übersprungen. Das Programm funktioniert möglicherweise nicht korrekt.")

def main():
    if "--test-mode" in sys.argv:
        os.environ["VHDL_AGENT_TEST_MODE"] = "1"
    check_components()

    if SRC_ROOT not in sys.path:
        sys.path.insert(0, SRC_ROOT)

    from src.main import main as app_main

    app_main()


if __name__ == "__main__":
    main()