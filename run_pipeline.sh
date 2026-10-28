#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-$project_dir/venv/bin/python}"
export PYTHONPATH="$project_dir/src${PYTHONPATH:+:$PYTHONPATH}"

cd -- "$project_dir"
if (($#)); then
    if [[ "$1" == "clipper.core.orchestrator" || "${1##*/}" == "orchestrator.py" ]]; then
        shift
        exec "$python_bin" -m clipper.core.orchestrator "$@"
    fi
    if [[ "$1" == --* || "$1" == "-h" ]]; then
        exec "$python_bin" -m clipper.core.orchestrator "$@"
    fi
    if [[ "$1" == "clipper.runtime.cuda_runtime" || "${1##*/}" == "cuda_runtime.py" ]]; then
        shift
        exec "$python_bin" -m clipper.runtime.cuda_runtime "$@"
    fi
    if [[ "$1" == "-m" ]]; then
        exec "$python_bin" "$@"
    fi
    exec "$python_bin" "$@"
fi
exec "$python_bin" -m clipper.core.orchestrator
