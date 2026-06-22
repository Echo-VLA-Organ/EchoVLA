#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=setup_env.sh
source "${SCRIPT_DIR}/setup_env.sh"

export ECHO_MOMANI_ROOT="${ECHO_MOMANI_ROOT:-${ECHO_VLA_ROOT}/benchmarks/momani}"
export MOMANI_ROOT="${MOMANI_ROOT:-${ECHO_MOMANI_ROOT}}"
export NAVGEN_ROOT="${NAVGEN_ROOT:-${ECHO_MOMANI_ROOT}}"
export NAVGEN_SKIP_GIT_SYNC="${NAVGEN_SKIP_GIT_SYNC:-1}"
export PYTHONPATH="${ECHO_MOMANI_ROOT}:${PYTHONPATH}"

echo "ECHO_MOMANI_ROOT=${ECHO_MOMANI_ROOT}"
