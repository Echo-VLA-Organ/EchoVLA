#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAVGEN_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

MANIFEST_PATH="${NAVGEN_RUNTIME_MANIFEST:-${NAVGEN_ROOT}/config/runtime/runtime_manifest.yaml}"
VENV_PATH="${1:-${NAVGEN_VENV_PATH:-${NAVGEN_ROOT}/.venv}}"
PYTHON_VERSION="${NAVGEN_PYTHON_VERSION:-3.10}"
DEPS_ROOT="${NAVGEN_DEPS_ROOT:-${NAVGEN_ROOT}/.deps}"
SKIP_GIT_SYNC="${NAVGEN_SKIP_GIT_SYNC:-0}"

ROBOCASA_GIT_URL="${NAVGEN_ROBOCASA_GIT_URL:-https://github.com/robocasa/robocasa}"
ROBOCASA_GIT_REF="${NAVGEN_ROBOCASA_GIT_REF:-756598a5be52e052339bb2d957426e39015c2afb}"
ROBOSUITE_GIT_URL="${NAVGEN_ROBOSUITE_GIT_URL:-https://github.com/ARISE-Initiative/robosuite}"
ROBOSUITE_GIT_REF="${NAVGEN_ROBOSUITE_GIT_REF:-e94119512f737635111ae651768c17ad1be72859}"

ROBOCASA_SRC="${ROBOCASA_SRC:-${DEPS_ROOT}/robocasa}"
ROBOSUITE_SRC="${ROBOSUITE_SRC:-${DEPS_ROOT}/robosuite}"

echo "[bootstrap_runtime] navgen_root=${NAVGEN_ROOT}"
echo "[bootstrap_runtime] manifest=${MANIFEST_PATH}"
echo "[bootstrap_runtime] venv_path=${VENV_PATH}"
echo "[bootstrap_runtime] python_version=${PYTHON_VERSION}"
echo "[bootstrap_runtime] deps_root=${DEPS_ROOT}"
echo "[bootstrap_runtime] skip_git_sync=${SKIP_GIT_SYNC}"

sync_repo() {
  local url="$1"
  local ref="$2"
  local dst="$3"

  if [[ -d "${dst}/.git" ]]; then
    git -C "${dst}" fetch --all --tags
  elif [[ -d "${dst}" ]]; then
    echo "[bootstrap_runtime] path exists but is not a git repo: ${dst}" >&2
    exit 1
  else
    mkdir -p "$(dirname "${dst}")"
    git clone "${url}" "${dst}"
  fi
  git -C "${dst}" checkout "${ref}"
}

if [[ "${SKIP_GIT_SYNC}" != "1" ]]; then
  sync_repo "${ROBOCASA_GIT_URL}" "${ROBOCASA_GIT_REF}" "${ROBOCASA_SRC}"
  sync_repo "${ROBOSUITE_GIT_URL}" "${ROBOSUITE_GIT_REF}" "${ROBOSUITE_SRC}"
fi

for src in "${ROBOCASA_SRC}" "${ROBOSUITE_SRC}"; do
  if [[ ! -d "${src}" ]]; then
    echo "[bootstrap_runtime] missing source path: ${src}" >&2
    exit 1
  fi
done

uv venv "${VENV_PATH}" --python "${PYTHON_VERSION}"

CORE_REQ="${NAVGEN_ROOT}/requirements/runtime-core.txt"
DARWIN_REQ="${NAVGEN_ROOT}/requirements/runtime-platform-darwin.txt"
LINUX_REQ="${NAVGEN_ROOT}/requirements/runtime-platform-linux-wsl.txt"

uv pip install --python "${VENV_PATH}/bin/python" -r "${CORE_REQ}"

OS_NAME="$(uname -s | tr '[:upper:]' '[:lower:]')"
if [[ "${OS_NAME}" == "darwin" ]]; then
  uv pip install --python "${VENV_PATH}/bin/python" -r "${DARWIN_REQ}"
elif [[ "${OS_NAME}" == "linux" ]]; then
  uv pip install --python "${VENV_PATH}/bin/python" -r "${LINUX_REQ}"
fi

uv pip install --python "${VENV_PATH}/bin/python" --no-deps -e "${ROBOSUITE_SRC}"
uv pip install --python "${VENV_PATH}/bin/python" --no-deps -e "${ROBOCASA_SRC}"

"${VENV_PATH}/bin/python" "${NAVGEN_ROOT}/scripts/env/check_runtime.py" \
  --manifest "${MANIFEST_PATH}"

echo "[bootstrap_runtime] done"
