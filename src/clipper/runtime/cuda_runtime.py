"""Initialize the Linux CUDA loader before importing inference packages."""

import ctypes
from importlib.metadata import PackageNotFoundError, distribution
import os
from pathlib import Path
import sys

from clipper.runtime.config import WHISPER_COMPUTE_TYPE, WHISPER_DEVICE


def cuda_library_directories() -> list[str]:
    directories = []
    for package, relative_path in (
        ("nvidia-cublas-cu12", "nvidia/cublas/lib"),
        ("nvidia-cudnn-cu12", "nvidia/cudnn/lib"),
    ):
        try:
            directory = Path(distribution(package).locate_file(relative_path)).resolve()
        except PackageNotFoundError as error:
            raise RuntimeError(
                f"Missing {package}. Install GPU dependencies with: "
                f"{sys.executable} -m pip install --prefer-binary -r requirements-gpu.txt"
            ) from error
        if not directory.is_dir():
            raise RuntimeError(
                f"Missing CUDA library directory: {directory}. Reinstall GPU dependencies "
                "from requirements-gpu.txt in the active virtual environment."
            )
        directories.append(str(directory))
    return directories


def prepare_cuda_environment() -> None:
    if WHISPER_DEVICE != "cuda":
        return
    if sys.platform != "linux":
        raise RuntimeError("The CUDA launcher supports Linux/WSL/Docker; use the WSL venv.")

    directories = cuda_library_directories()
    current_paths = os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep)
    if current_paths[:len(directories)] == directories:
        return

    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = os.pathsep.join(
        directories + [path for path in current_paths if path and path not in directories]
    )
    # glibc reads loader paths at process startup; changing os.environ is insufficient.
    os.execve(sys.executable, [sys.executable, *sys.orig_argv[1:]], environment)


def validate_cuda_runtime() -> None:
    if WHISPER_DEVICE != "cuda":
        return
    for library in ("libcublasLt.so.12", "libcublas.so.12", "libcudnn.so.9"):
        try:
            ctypes.CDLL(library)
        except OSError as error:
            raise RuntimeError(
                f"Cannot load {library}: {error}. Use bash run_pipeline.sh or "
                "python orchestrator.py to initialize the CUDA loader. Check the active "
                "venv dependencies with: python -m pip install --prefer-binary "
                "-r requirements-gpu.txt"
            ) from error

    import ctranslate2

    if ctranslate2.get_cuda_device_count() < 1:
        raise RuntimeError(
            "No CUDA GPU is visible. Check nvidia-smi in WSL; Docker requires --gpus all."
        )
    supported_types = ctranslate2.get_supported_compute_types("cuda")
    if WHISPER_COMPUTE_TYPE not in supported_types:
        raise RuntimeError(
            f"WHISPER_COMPUTE_TYPE={WHISPER_COMPUTE_TYPE} is unsupported by this GPU. "
            f"Supported types: {', '.join(sorted(supported_types))}"
        )


if __name__ == "__main__":
    try:
        prepare_cuda_environment()
        validate_cuda_runtime()
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python cuda_runtime.py <script.py | -m module> [arguments]")
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
