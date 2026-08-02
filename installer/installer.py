#!/usr/bin/env python3

"""
Autonomous Agent Environment Installer

Target:
Ubuntu / Linux Mint

Installiert:
- Docker Engine
- Docker Compose
- Hermes Agent Container
- OpenCode Container

Erweiterbar für:
- Ollama
- LangChain
- CrewAI
- Next.js Frontend
- Python Backend
"""


import os
import sys
import subprocess
from pathlib import Path


PROJECT_DIR = Path.home() / "agent_environment"



# ==================================================
# Grundfunktionen
# ==================================================

def run(cmd):

    print("\n>>>", cmd)

    result = subprocess.run(
        cmd,
        shell=True
    )

    if result.returncode != 0:
        print("\nFEHLER:")
        print(cmd)
        sys.exit(1)



def as_root():

    """
    Startet Skript automatisch mit sudo
    """

    if os.geteuid() != 0:

        print(
            "[INFO] Administratorrechte erforderlich..."
        )

        os.execvp(
            "sudo",
            [
                "sudo",
                sys.executable
            ]
            +
            sys.argv
        )



def exists(command):

    return subprocess.call(
        [
            "bash",
            "-c",
            f"command -v {command}"
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    ) == 0



# ==================================================
# Systemprüfung
# ==================================================

def check_system():

    print(
        "[INFO] Prüfe Betriebssystem..."
    )


    if not Path(
        "/etc/os-release"
    ).exists():

        sys.exit(
            "Kein Linux erkannt"
        )


    with open(
        "/etc/os-release"
    ) as f:

        data=f.read().lower()


    if (
        "ubuntu" not in data
        and
        "linuxmint" not in data
    ):

        print(
            "WARNUNG: Nicht Ubuntu/Mint"
        )

    else:

        print(
            "[OK] Unterstütztes System"
        )



# ==================================================
# Docker Installation
# ==================================================

def install_docker():


    if exists("docker"):

        print(
            "[OK] Docker vorhanden"
        )

        return


    print(
        "[INFO] Installiere Docker..."
    )


    run(
"""
apt update

apt install -y \
ca-certificates \
curl \
gnupg
"""
    )


    run(
        """
curl -fsSL https://get.docker.com | sh
"""
    )


    run(
        """
systemctl enable docker
systemctl start docker
"""
    )


    print(
        "[OK] Docker installiert"
    )



def install_compose():


    if exists("docker-compose"):

        return


    print(
        "[INFO] Installiere Docker Compose..."
    )


    run(
        """
apt install -y docker-compose-plugin
"""
    )



# ==================================================
# Projektstruktur
# ==================================================

def setup_structure():

    print(
        "[INFO] Erstelle Projektstruktur"
    )


    dirs=[

        PROJECT_DIR,

        PROJECT_DIR/"data",

        PROJECT_DIR/"config",

        PROJECT_DIR/"logs",

        PROJECT_DIR/"projects",

        PROJECT_DIR/"hermes",

        PROJECT_DIR/"opencode",

        PROJECT_DIR/"shared",
    ]


    for d in dirs:

        d.mkdir(
            parents=True,
            exist_ok=True
        )



# ==================================================
# Agent Umgebung
# ==================================================

def setup_agents():


    compose = PROJECT_DIR / "docker-compose.yml"


    if not compose.exists():

        compose.write_text(
"""
version: '3.9'

services:
  hermes:
    image: hermes-agent:latest
    container_name: hermes-agent
    restart: unless-stopped
    volumes:
      - ./hermes:/workspace
      - ./projects:/projects
      - ./shared:/shared
      - ./config:/config
      - {repo_root}:/agent_repo:ro
    working_dir: /workspace

  opencode:
    image: ghcr.io/anomalyco/opencode:latest
    container_name: opencode-agent
    restart: unless-stopped
    volumes:
      - ./opencode:/workspace
      - ./projects:/projects
      - ./shared:/shared
      - ./config:/config
      - {repo_root}:/agent_repo:ro
    working_dir: /workspace
""".format(repo_root=REPO_ROOT)
        )


    print(
        "[OK] Agent Konfiguration erstellt"
    )


    run(
        f"""
cd {PROJECT_DIR}

docker compose pull
"""
    )


# ==================================================
# Projektstart
# ==================================================

def start_project():
    print("[INFO] Starte Projektcontainer...")
    run(
        f"""
cd {PROJECT_DIR}

docker compose up -d
"""
    )
    print("[OK] Projekt gestartet")



# ==================================================
# Erweiterungspunkte
# ==================================================

def install_ghdl():

    if exists("ghdl"):
        print("[OK] GHDL bereits installiert")
        return

    print("[INFO] Installiere GHDL...")
    run(
        "apt update && apt install -y ghdl"
    )
    print("[OK] GHDL installiert")


def install_fpga_support():

    print("[INFO] Installiere FPGA-Werkzeuge (Platzhalter)...")
    print(
        "[WARN] FPGA-spezifische Tools werden nicht automatisch installiert. "
        "Bitte passe install_fpga_support() im Installer an."
    )


def install_ollama():

    """
    Hier später Ollama
    """

    pass



def install_python_agents():

    """
    Hier später:
    LangChain
    eigene Agenten
    """

    pass



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

    install_docker()

    install_compose()

    setup_structure()

    setup_agents()

    install_ghdl()

    install_fpga_support()


    # spätere Module

    install_ollama()

    install_python_agents()

    start_project()



    print(
f"""

========================================

Installation abgeschlossen.

Projekt:
{PROJECT_DIR}

Container Status:

"""
    )


    run(
        "docker ps"
    )



if __name__ == "__main__":

    main()