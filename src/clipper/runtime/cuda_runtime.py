"""Initialize the Linux CUDA loader before importing inference packages."""

import ctypes
from importlib.metadata import PackageNotFoundError, distribution
import logging
import os
from pathlib import Path
import sys

from clipper.runtime.config import WHISPER_COMPUTE_TYPE, WHISPER_DEVICE

logger = logging.getLogger(__name__)


class _NvmlMemory(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


def get_gpu_memory_info(device_index: int = 0) -> tuple[float, float, float] | None:
    try:
        nvml = ctypes.CDLL("libnvidia-ml.so.1")
        init_fn = getattr(nvml, "nvmlInit_v2", getattr(nvml, "nvmlInit", None))
        get_handle_fn = getattr(
            nvml, "nvmlDeviceGetHandleByIndex_v2", getattr(nvml, "nvmlDeviceGetHandleByIndex", None)
        )
        get_mem_fn = getattr(nvml, "nvmlDeviceGetMemoryInfo", None)
        shutdown_fn = getattr(nvml, "nvmlShutdown", None)

        if not (init_fn and get_handle_fn and get_mem_fn):
            return None

        ret = init_fn()
        if ret != 0:
            return None

        try:
            handle = ctypes.c_void_p()
            ret = get_handle_fn(ctypes.c_uint(device_index), ctypes.byref(handle))
            if ret != 0:
                return None

            mem = _NvmlMemory()
            ret = get_mem_fn(handle, ctypes.byref(mem))
            if ret != 0:
                return None

            mb = 1024.0 * 1024.0
            return (float(mem.used) / mb, float(mem.free) / mb, float(mem.total) / mb)
        finally:
            if shutdown_fn:
                shutdown_fn()
    except Exception:
        return None


def release_cuda_memory(before_mb: float | None = None) -> None:
    if WHISPER_DEVICE != "cuda":
        return

    try:
        if before_mb is None:
            before_info = get_gpu_memory_info()
            if before_info is not None:
                before_mb = before_info[0]

        torch = sys.modules.get("torch")
        if torch is None:
            try:
                import torch
            except ImportError:
                torch = None

        if torch is not None and hasattr(torch, "cuda") and torch.cuda.is_available():
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()

        after_info = get_gpu_memory_info()
        if before_mb is not None and after_info is not None:
            after_mb = after_info[0]
            freed_mb = max(0.0, before_mb - after_mb)
            logger.info(
                "GPU memory flushed successfully: before=%.1f MB, after=%.1f MB (freed=%.1f MB)",
                before_mb,
                after_mb,
                freed_mb,
            )
        else:
            logger.info("GPU memory flushed successfully.")
    except Exception as error:
        logger.warning("GPU memory cleanup failed: %s", error)


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
