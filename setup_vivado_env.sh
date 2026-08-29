#!/bin/bash
# =============================================================================
# Vivado Environment Setup for vhdl-agent
# =============================================================================
# This script sources the Xilinx Vivado environment so that:
#   - vivado, xsct, hw_server, etc. are in PATH
#   - XILINX_VIVADO, XILINX_VITIS are set
#   - LD_LIBRARY_PATH includes Vivado libraries
#
# Usage:
#   source setup_vivado_env.sh          # Interactive: loads env into current shell
#   bash setup_vivado_env.sh            # Non-interactive: just verifies setup
#
# The Vivado installation path is configured here. Adjust if your installation
# differs from the default.
# =============================================================================

# ---------------------------------------------------------------------------
# Configuration: Vivado installation path
# Adjust this if Vivado is installed elsewhere.
# ---------------------------------------------------------------------------
VIVADO_BASE="${VIVADO_BASE:-/home/alex/Xilinx/2026.1}"
VIVADO_SETTINGS="${VIVADO_BASE}/Vivado/settings64.sh"

# ---------------------------------------------------------------------------
# Verify and source Vivado environment
# ---------------------------------------------------------------------------
if [ ! -f "${VIVADO_SETTINGS}" ]; then
    echo "ERROR: Vivado settings not found at: ${VIVADO_SETTINGS}"
    echo "Please adjust VIVADO_BASE in this script or set the VIVADO_BASE environment variable."
    return 1 2>/dev/null || exit 1
fi

# Source Vivado settings (sets PATH, XILINX_VIVADO, LD_LIBRARY_PATH, etc.)
source "${VIVADO_SETTINGS}"

# Verify vivado is now available
if command -v vivado &>/dev/null; then
    VIVADO_VERSION=$(vivado -version 2>&1 | head -1)
    echo "Vivado environment loaded successfully."
    echo "  Version:  ${VIVADO_VERSION}"
    echo "  Path:     $(which vivado)"
    echo "  Settings: ${VIVADO_SETTINGS}"
else
    echo "ERROR: vivado binary not found after sourcing settings64.sh"
    return 1 2>/dev/null || exit 1
fi
