#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ECHO_VLA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PYTHONPATH="${ECHO_VLA_ROOT}:${PYTHONPATH:-}"
echo "ECHO_VLA_ROOT=${ECHO_VLA_ROOT}"
