#!/usr/bin/env bash
# cleanup.sh – Temporäre Artefakte des VHDL-Agents bereinigen
#
# Nutzung:
#   ./cleanup.sh              # Standard: Aufräumen mit Protokollierung
#   ./cleanup.sh --dry-run    # Nur anzeigen, was gelöscht würde
#   ./cleanup.sh --force      # Ohne Nachfrage alles löschen
#   ./cleanup.sh --projects-only  # Nur Projekt-Artefakte (kein Repo-Root)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false
FORCE=false
PROJECTS_ONLY=false
REMOVED=0

# --- Argumente parsen ---
for arg in "$@"; do
    case "$arg" in
        --dry-run)      DRY_RUN=true ;;
        --force)        FORCE=true ;;
        --projects-only) PROJECTS_ONLY=true ;;
        -h|--help)
            echo "Nutzung: $0 [--dry-run] [--force] [--projects-only]"
            echo ""
            echo "Optionen:"
            echo "  --dry-run        Nur anzeigen, was gelöscht würde"
            echo "  --force          Ohne Nachfrage alles löschen"
            echo "  --projects-only  Nur Projekt-Artefakte (kein Repo-Root)"
            exit 0
            ;;
        *)
            echo "Unbekanntes Argument: $arg"
            exit 1
            ;;
    esac
done

log() { echo "[cleanup] $*"; }
remove_item() {
    local path="$1"
    local label="${2:-$path}"
    if $DRY_RUN; then
        log "DRY-RUN: würde löschen: $label"
    else
        if [ -e "$path" ]; then
            rm -rf "$path"
            log "gelöscht: $label"
            REMOVED=$((REMOVED + 1))
        fi
    fi
}

# ======================================================================
# 1. Repo-Root: GHDL-Artefakte (work-obj*.cf)
# ======================================================================
if ! $PROJECTS_ONLY; then
    log "--- Repo-Root: GHDL-Artefakte ---"
    for f in "$SCRIPT_DIR"/work-obj*.cf; do
        [ -e "$f" ] && remove_item "$f" "$(basename "$f")"
    done
fi

# ======================================================================
# 2. Repo-Root: Vivado-Artefakte (.Xil/, clockInfo.txt, vivado-Logs)
# ======================================================================
if ! $PROJECTS_ONLY; then
    log "--- Repo-Root: Vivado-Artefakte ---"
    [ -d "$SCRIPT_DIR/.Xil" ] && remove_item "$SCRIPT_DIR/.Xil" ".Xil/"
    for f in "$SCRIPT_DIR"/clockInfo.txt "$SCRIPT_DIR"/vivado.jou "$SCRIPT_DIR"/vivado.log \
             "$SCRIPT_DIR"/vivado_*.backup.jou "$SCRIPT_DIR"/vivado_*.backup.log; do
        [ -e "$f" ] && remove_item "$f" "$(basename "$f")"
    done
fi

# ======================================================================
# 3. Projekte: Temporäre Artefakte in Projekt-Roots bereinigen
# ======================================================================
log "--- Projekte: Temporäre Artefakte ---"
PROJECTS_DIR="$SCRIPT_DIR/projects"
if [ -d "$PROJECTS_DIR" ]; then
    for project in "$PROJECTS_DIR"/*/; do
        [ -d "$project" ] || continue
        proj_name="$(basename "$project")"

        # GHDL-Artefakte im Projekt-Root (leaked)
        for f in "$project"work-obj*.cf; do
            [ -e "$f" ] && remove_item "$f" "$proj_name/$(basename "$f")"
        done

        # Vivado-Artefakte im Projekt-Root
        [ -d "$project/.Xil" ] && remove_item "$project/.Xil" "$proj_name/.Xil/"
        for f in "$project"/clockInfo.txt "$project"/vivado.jou "$project"/vivado.log; do
            [ -e "$f" ] && remove_item "$f" "$proj_name/$(basename "$f")"
        done

        # GHDL-Artefakte in src/ (leaked)
        if [ -d "$project/src" ]; then
            for f in "$project/src"/work-obj*.cf; do
                [ -e "$f" ] && remove_item "$f" "$proj_name/src/$(basename "$f")"
            done
        fi

        # GHDL-Artefakte in build/ (erwartet, aber aufräumen nach alten Runs)
        if [ -d "$project/build" ]; then
            for f in "$project/build"/work-obj*.cf; do
                [ -e "$f" ] && remove_item "$f" "$proj_name/build/$(basename "$f")"
            done
        fi
    done
fi

# ======================================================================
# 4. Schaltungsagent: GHDL-Artefakte (leaked)
# ======================================================================
if ! $PROJECTS_ONLY; then
    log "--- Schaltungsagent: Temporäre Artefakte ---"
    SA_DIR="$SCRIPT_DIR/Schaltungsagent"
    if [ -d "$SA_DIR" ]; then
        for f in "$SA_DIR"/work-obj*.cf; do
            [ -e "$f" ] && remove_item "$f" "Schaltungsagent/$(basename "$f")"
        done
    fi
fi

# ======================================================================
# 5. Temporäre Vivado-Flash-Verzeichnisse (falls Steps abgebrochen)
# ======================================================================
log "--- Temporäre Flash-Verzeichnisse ---"
for d in /tmp/vivado_flash_*/; do
    [ -d "$d" ] && remove_item "$d" "$(basename "$d")"
done

# ======================================================================
# Zusammenfassung
# ======================================================================
if $DRY_RUN; then
    log "Dry-Run abgeschlossen. Keine Dateien gelöscht."
else
    log "Cleanup abgeschlossen. $REMOVED Element(e) entfernt."
fi
