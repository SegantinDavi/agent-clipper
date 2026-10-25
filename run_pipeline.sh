#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-$project_dir/venv/bin/python}"

cd -- "$project_dir"
if (($#)); then
    if [[ "${1##*/}" == "orchestrator.py" ]]; then
        exec "$python_bin" "$@"
    fi
    if [[ "$1" == --* || "$1" == "-h" ]]; then
        exec "$python_bin" "$project_dir/orchestrator.py" "$@"
    fi
    exec "$python_bin" "$project_dir/cuda_runtime.py" "$@"
fi
exec "$python_bin" "$project_dir/orchestrator.py"
