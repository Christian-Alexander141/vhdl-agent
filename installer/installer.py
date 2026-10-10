#!/usr/bin/env python3

"""
Autonomous Agent Environment Installer

Target:
Ubuntu / Linux Mint

Installiert alles, was das Projekt zum Laufen braucht:
- Systempakete (Python, git, curl, build tools, GHDL)
- Docker Engine + Docker Compose Plugin
- OpenCode CLI, gebaut als eigenes Docker-Image (opencode-agent:latest)
- Python Virtualenv mit allen Abhängigkeiten (pyproject.toml)
- Projektstruktur und Docker-Images

Hinweis: Vivado wird bewusst NICHT installiert (muss manuell erfolgen).
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / ".venv"
PYTHON_BIN = VENV_DIR / "bin" / "python"
PIP_BIN = VENV_DIR / "bin" / "pip"

OPENCODE_IMAGE = "opencode-agent:latest"
OPENCODE_DOCKER_DIR = REPO_ROOT / "docker" / "opencode"

SYSTEM_PACKAGES = [
    "python3",
    "python3-venv",
    "python3-pip",
    "python3-dev",
    "git",
    "curl",
    "ca-certificates",
    "gnupg",
    "build-essential",
    "ghdl",
]

# Offizieller Installationsweg von OpenCode (curl | bash), nur eben im
# Container statt auf dem Host -> landet nicht in /root auf dem Host.
OPENCODE_DOCKERFILE = """FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git curl && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://opencode.ai/install | bash
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /workspace
ENTRYPOINT ["opencode"]
"""


def run(cmd, check=True):
    print(f"\n>>> {cmd}")
    result = subprocess.run(cmd, shell=True)
    if check and result.returncode != 0:
        print(f"\nFEHLER bei: {cmd}")
        sys.exit(1)
    return result


def as_root():
    if os.geteuid() != 0:
        print("[INFO] Administratorrechte erforderlich...")
        os.execvp("sudo", ["sudo", sys.executable] + sys.argv)


def original_user():
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or "root"


def exists(command):
    """Prüft, ob EIN einzelnes Kommando im PATH existiert.
    Nicht für mehrteilige Befehle wie 'docker compose' verwenden -
    'command -v docker compose' prüft in bash nur 'docker' und ignoriert
    'compose' faktisch, was einen falschen Treffer liefert."""
    return subprocess.call(
        ["bash", "-c", f"command -v {command}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) == 0


def docker_compose_available():
    """Prüft das docker-compose-Plugin direkt über seinen Subcommand,
    statt über 'command -v docker compose' (siehe Bugfix-Hinweis oben)."""
    return subprocess.call(
        ["docker", "compose", "version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) == 0


# ==================================================
# Systemprüfung
# ==================================================

def check_system():
    print("[INFO] Prüfe Betriebssystem...")
    if not Path("/etc/os-release").exists():
        sys.exit("Kein Linux erkannt")
    data = Path("/etc/os-release").read_text().lower()
    if "ubuntu" in data or "linuxmint" in data:
        print("[OK] Unterstütztes System")
    else:
        print("WARNUNG: Nicht Ubuntu/Mint")


# ==================================================
# Systempakete
# ==================================================

def install_system_packages():
    print("[INFO] Installiere Systempakete...")
    run("apt update")
    run("apt install -y " + " ".join(SYSTEM_PACKAGES))
    print("[OK] Systempakete installiert")


# ==================================================
# Docker + Compose
# ==================================================

def install_docker():
    if exists("docker"):
        print("[OK] Docker vorhanden")
    else:
        print("[INFO] Installiere Docker...")
        run("curl -fsSL https://get.docker.com | sh")
    run("systemctl enable docker")
    run("systemctl start docker")

    # Ohne das hier bleibt 'docker'/'docker compose' für den normalen
    # Nutzer nach der Installation "Permission denied", solange nicht
    # weiter mit sudo gearbeitet wird.
    owner = original_user()
    if owner != "root":
        print(f"[INFO] Füge '{owner}' zur Gruppe 'docker' hinzu...")
        run(f"usermod -aG docker {owner}", check=False)
        print(f"[OK] '{owner}' kann Docker nach Neuanmeldung ohne sudo nutzen "
              f"(oder vorher: 'newgrp docker')")

    print("[OK] Docker installiert")


def install_compose():
    if docker_compose_available():
        print("[OK] Docker Compose vorhanden")
    else:
        print("[INFO] Installiere Docker Compose Plugin...")
        run("apt install -y docker-compose-plugin")
    print("[OK] Docker Compose installiert")


# ==================================================
# Python-Umgebung
# ==================================================

def setup_venv():
    if not PYTHON_BIN.exists():
        print("[INFO] Erstelle Virtualenv...")
        run(f"python3 -m venv {VENV_DIR}")
    print("[INFO] Installiere Python-Abhängigkeiten...")
    run(f"{PIP_BIN} install --upgrade pip")
    run(f"{PIP_BIN} install -e {REPO_ROOT}")
    print("[OK] Python-Umgebung eingerichtet")


# ==================================================
# Projektstruktur
# ==================================================

def setup_structure():
    print("[INFO] Erstelle Projektstruktur...")
    for d in ["data", "config", "logs", "projects", "memory", "Dateien"]:
        (REPO_ROOT / d).mkdir(parents=True, exist_ok=True)
    print("[OK] Projektstruktur erstellt")


# ==================================================
# OpenCode-Agent (im Docker-Container)
# ==================================================

def setup_agents():
    print("[INFO] Baue OpenCode Docker-Image...")
    OPENCODE_DOCKER_DIR.mkdir(parents=True, exist_ok=True)
    dockerfile_path = OPENCODE_DOCKER_DIR / "Dockerfile"
    if not dockerfile_path.exists():
        dockerfile_path.write_text(OPENCODE_DOCKERFILE)
    run(f"docker build -t {OPENCODE_IMAGE} {OPENCODE_DOCKER_DIR}", check=False)
    print("[OK] OpenCode Docker-Image bereit")


# ==================================================
# Projektstart
# ==================================================

def start_project():
    print("[INFO] Starte Projektcontainer...")
    run(f"cd {REPO_ROOT} && docker compose up -d", check=False)
    print("[OK] Projekt gestartet")


# ==================================================
# Start
# ==================================================

def main():
    print(
        """
========================================
 Autonomous Agent Installer
 Ubuntu / Linux Mint
========================================
"""
    )

    as_root()
    check_system()
    install_system_packages()
    install_docker()
    install_compose()
    setup_venv()
    setup_structure()
    setup_agents()
    start_project()

    # Alles, was während des root-Laufs unter REPO_ROOT neu entstanden ist
    # (venv, data/, logs/, docker/opencode/...), gehört sonst root statt
    # dem eigentlichen Nutzer.
    owner = original_user()
    if owner != "root":
        run(f"chown -R {owner}:{owner} {REPO_ROOT}")

    print(
        f"""
========================================
 Installation abgeschlossen.
 Projekt: {REPO_ROOT}
 Venv:    {VENV_DIR}

 Container Status:
========================================
"""
    )
    run("docker ps", check=False)


if __name__ == "__main__":
    main()