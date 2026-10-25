#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-$project_dir/venv/bin/python}"

# The dynamic linker needs pip-installed CUDA paths before Python starts.
cuda_lib_dirs="$("$python_bin" - <<'PY'
from importlib.util import find_spec
from pathlib import Path

paths = []
for name in ("nvidia.cublas", "nvidia.cudnn"):
    try:
        spec = find_spec(name)
    except ModuleNotFoundError:
        spec = None
    if spec is None:
        raise SystemExit("Install GPU dependencies: pip install -r requirements-gpu.txt")
    paths.append(str(Path(next(iter(spec.submodule_search_locations))) / "lib"))
print(":".join(paths))
PY
)"
export LD_LIBRARY_PATH="$cuda_lib_dirs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

cd -- "$project_dir"
if (($#)); then
    exec "$python_bin" "$@"
fi
exec "$python_bin" orchestrator.py
