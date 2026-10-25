#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-$project_dir/venv/bin/python}"

cd -- "$project_dir"
if (($#)); then
    exec "$python_bin" "$project_dir/cuda_runtime.py" "$@"
fi
exec "$python_bin" "$project_dir/cuda_runtime.py" orchestrator.py
