import tests

from importlib.metadata import PackageNotFoundError
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import clipper.runtime.cuda_runtime as cuda_runtime


class CudaBootstrapTests(unittest.TestCase):
    def test_loader_paths_precede_existing_paths_and_restart_preserves_arguments(self):
        directories = ["/venv/nvidia/cublas/lib", "/venv/nvidia/cudnn/lib"]
        with patch.object(cuda_runtime, "WHISPER_DEVICE", "cuda"), \
             patch.object(cuda_runtime.sys, "platform", "linux"), \
             patch.object(cuda_runtime.sys, "orig_argv", ["python", "-u", "-m", "unittest"]), \
             patch.object(cuda_runtime, "cuda_library_directories", return_value=directories), \
             patch.dict(os.environ, {"LD_LIBRARY_PATH": "/existing/lib", "KEEP_TEST": "value"}), \
             patch.object(cuda_runtime.os, "execve") as restart:
            cuda_runtime.prepare_cuda_environment()
            executable, arguments, environment = restart.call_args.args
            self.assertEqual(executable, cuda_runtime.sys.executable)
            self.assertEqual(arguments, [executable, "-u", "-m", "unittest"])
            self.assertEqual(environment["KEEP_TEST"], "value")
            self.assertEqual(
                environment["LD_LIBRARY_PATH"], ":".join(directories + ["/existing/lib"])
            )
            with patch.dict(os.environ, environment, clear=True):
                cuda_runtime.prepare_cuda_environment()
            restart.assert_called_once()

    def test_cpu_does_not_require_nvidia_packages_or_restart(self):
        with patch.object(cuda_runtime, "WHISPER_DEVICE", "cpu"), \
             patch.object(cuda_runtime, "cuda_library_directories") as discover, \
             patch.object(cuda_runtime.os, "execve") as restart, \
             patch.object(cuda_runtime.ctypes, "CDLL") as load:
            cuda_runtime.prepare_cuda_environment()
            cuda_runtime.validate_cuda_runtime()
        discover.assert_not_called()
        restart.assert_not_called()
        load.assert_not_called()

    def test_missing_package_has_installation_instructions(self):
        with patch.object(cuda_runtime, "distribution", side_effect=PackageNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "requirements-gpu.txt"):
                cuda_runtime.cuda_library_directories()

    def test_missing_directory_has_reinstallation_instructions(self):
        package = SimpleNamespace(locate_file=lambda name: Path("missing-cuda-test") / name)
        with patch.object(cuda_runtime, "distribution", return_value=package):
            with self.assertRaisesRegex(RuntimeError, "Reinstall GPU dependencies"):
                cuda_runtime.cuda_library_directories()

    def test_missing_library_has_loader_instructions(self):
        with patch.object(cuda_runtime, "WHISPER_DEVICE", "cuda"), \
             patch.object(cuda_runtime.ctypes, "CDLL", side_effect=OSError("not found")):
            with self.assertRaisesRegex(RuntimeError, "libcublasLt.so.12.*run_pipeline.sh"):
                cuda_runtime.validate_cuda_runtime()

    def test_missing_gpu_and_unsupported_precision_fail_before_inference(self):
        for count, precision, expected in (
            (0, "float16", "No CUDA GPU"),
            (1, "unsupported", "unsupported by this GPU"),
        ):
            backend = SimpleNamespace(
                get_cuda_device_count=lambda: count,
                get_supported_compute_types=lambda device: {"float16"},
            )
            with self.subTest(count=count, precision=precision), \
                 patch.object(cuda_runtime, "WHISPER_DEVICE", "cuda"), \
                 patch.object(cuda_runtime, "WHISPER_COMPUTE_TYPE", precision), \
                 patch.object(cuda_runtime.ctypes, "CDLL"), \
                 patch.dict("sys.modules", {"ctranslate2": backend}):
                with self.assertRaisesRegex(RuntimeError, expected):
                    cuda_runtime.validate_cuda_runtime()


if __name__ == "__main__":
    unittest.main()
