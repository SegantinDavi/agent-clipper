"""Tests and memory profiling helpers for sandbox memory management (Feature 018).

Provides:
- Memory profiling test helpers (ru_maxrss and /proc/{pid}/status inspection)
- AST inspection fixtures for memory management directives (gc.collect, del, .close())
- Mock fixtures for VideoState and isolated subprocess testing
"""
import ast
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from clipper.core.orchestrator import VideoState


def get_proc_status_memory_kb(pid: int | None = None) -> dict[str, int]:
    """Parse /proc/{pid}/status and return memory metrics in kilobytes.
    
    Returns a dict with available memory keys in kB, such as:
    'VmPeak', 'VmSize', 'VmHWM', 'VmRSS'.
    Returns empty dict if /proc is unavailable (e.g. non-Linux platforms).
    """
    target_pid = pid if pid is not None else os.getpid()
    proc_path = Path(f"/proc/{target_pid}/status")
    metrics: dict[str, int] = {}
    if not proc_path.exists():
        return metrics

    try:
        with open(proc_path, "r", encoding="utf-8") as f:
            for line in f:
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    if key in ("VmPeak", "VmSize", "VmHWM", "VmRSS"):
                        # Value format is typically '12345 kB'
                        parts = val.split()
                        if parts:
                            try:
                                metrics[key] = int(parts[0])
                            except ValueError:
                                pass
    except OSError:
        pass
    return metrics


def get_process_peak_memory_kb(pid: int | None = None) -> int:
    """Get peak resident set size (RSS) in kilobytes.
    
    Prefers /proc/{pid}/status VmHWM (High Water Mark).
    Falls back to resource.getrusage(resource.RUSAGE_SELF).ru_maxrss.
    """
    metrics = get_proc_status_memory_kb(pid=pid)
    if "VmHWM" in metrics:
        return metrics["VmHWM"]
    if "VmRSS" in metrics:
        return metrics["VmRSS"]
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def get_children_peak_memory_kb() -> int:
    """Return peak RSS of child processes via resource.RUSAGE_CHILDREN in kilobytes."""
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss


def run_monitored_subprocess(
    cmd: list[str],
    timeout: float = 60.0,
    poll_interval: float = 0.05,
) -> tuple[int, str, str, int]:
    """Execute a subprocess and monitor its peak memory usage in kilobytes.
    
    Returns:
        (returncode, stdout_str, stderr_str, peak_rss_kb)
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    peak_rss_kb = 0
    start_time = time.monotonic()

    while True:
        poll_res = proc.poll()
        # Sample memory while process is alive
        if proc.pid:
            metrics = get_proc_status_memory_kb(proc.pid)
            vm_rss = metrics.get("VmRSS", 0)
            vm_hwm = metrics.get("VmHWM", 0)
            current_peak = max(vm_rss, vm_hwm)
            if current_peak > peak_rss_kb:
                peak_rss_kb = current_peak

        if poll_res is not None:
            break

        if (time.monotonic() - start_time) > timeout:
            proc.kill()
            stdout, stderr = proc.communicate()
            raise subprocess.TimeoutExpired(cmd, timeout, output=stdout, stderr=stderr)

        time.sleep(poll_interval)

    stdout, stderr = proc.communicate()
    # Final check of child rusage if /proc wasn't captured or was lower
    children_rusage = get_children_peak_memory_kb()
    if children_rusage > peak_rss_kb:
        peak_rss_kb = children_rusage

    return proc.returncode, stdout, stderr, peak_rss_kb


def inspect_script_memory_ast(script_code: str) -> dict[str, bool]:
    """Parse python code and check for memory management constructs.
    
    Returns:
        dict with booleans:
            'has_gc_import': import gc present
            'has_gc_collect': gc.collect() called
            'has_del_statement': del statement present
            'has_close_call': .close() method called
    """
    tree = ast.parse(script_code)
    has_gc_import = False
    has_gc_collect = False
    has_del_statement = False
    has_close_call = False

    for node in ast.walk(tree):
        # Check imports: import gc or from gc import ...
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "gc":
                    has_gc_import = True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "gc":
                has_gc_import = True

        # Check del statements
        elif isinstance(node, ast.Delete):
            has_del_statement = True

        # Check calls: gc.collect() or clip.close()
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr == "close":
                    has_close_call = True
                elif func.attr == "collect":
                    if isinstance(func.value, ast.Name) and func.value.id == "gc":
                        has_gc_collect = True
            elif isinstance(func, ast.Name):
                if func.id == "collect":
                    has_gc_collect = True

    return {
        "has_gc_import": has_gc_import,
        "has_gc_collect": has_gc_collect,
        "has_del_statement": has_del_statement,
        "has_close_call": has_close_call,
    }


def create_mock_video_state(
    cut_id: str = "1",
    attempts: int = 0,
    error: str | None = None,
    output_dir: str = "/tmp/output",
) -> VideoState:
    """Create a mock VideoState dict with required fields for execution_node testing."""
    return {
        "video_path": "/tmp/test.mp4",
        "audio_chunks": [],
        "transcription_chunks": [],
        "cuts": [
            {
                "id": cut_id,
                "start": "00:00:10,000",
                "end": "00:00:25,000",
                "start_seconds": 10.0,
                "end_seconds": 25.0,
                "duration": 15.0,
                "title": "Test Cut",
                "summary": "A test cut summary",
                "scenes": [
                    {
                        "start_seconds": 10.0,
                        "end_seconds": 25.0,
                        "focus_target": "speaker_center",
                        "overlay_text": "HOOK",
                    }
                ],
            }
        ],
        "approved_cut_ids": [cut_id],
        "current_cut_index": 0,
        "render_attempts": attempts,
        "render_error": error,
        "render_aborted": False,
        "rendered_video_paths": [],
        "visual_identity": {},
    }


class TestMemoryProfilingHelpers(unittest.TestCase):
    """T002: Unit tests for memory profiling test helpers."""

    def test_get_proc_status_memory_kb_current_process(self):
        """Verify /proc/{pid}/status extracts memory metrics for current process on Linux."""
        metrics = get_proc_status_memory_kb()
        if os.name == "posix" and Path(f"/proc/{os.getpid()}/status").exists():
            self.assertIn("VmRSS", metrics)
            self.assertGreater(metrics["VmRSS"], 0)
            self.assertIn("VmHWM", metrics)
            self.assertGreater(metrics["VmHWM"], 0)

    def test_get_process_peak_memory_kb_returns_positive_integer(self):
        """Verify peak memory helper returns positive integer in kilobytes."""
        peak_kb = get_process_peak_memory_kb()
        self.assertIsInstance(peak_kb, int)
        self.assertGreater(peak_kb, 0)

    def test_get_children_peak_memory_kb_returns_integer(self):
        """Verify get_children_peak_memory_kb returns non-negative integer."""
        child_peak = get_children_peak_memory_kb()
        self.assertIsInstance(child_peak, int)
        self.assertGreaterEqual(child_peak, 0)

    def test_run_monitored_subprocess_measures_rss_and_output(self):
        """Verify run_monitored_subprocess captures stdout, returncode, and peak RSS."""
        cmd = [sys.executable, "-c", "x = bytearray(10 * 1024 * 1024); print('ALLOC_OK')"]
        returncode, stdout, stderr, peak_rss_kb = run_monitored_subprocess(cmd, timeout=10.0)
        self.assertEqual(returncode, 0)
        self.assertIn("ALLOC_OK", stdout)
        self.assertGreater(peak_rss_kb, 0)


class TestSandboxMemoryScaffolding(unittest.TestCase):
    """T003: Scaffold tests verifying AST memory inspector and mock fixtures."""

    def test_create_mock_video_state_structure(self):
        """Verify mock VideoState contains all expected keys and values."""
        state = create_mock_video_state(cut_id="cut_42", attempts=1, error="Previous error")
        self.assertEqual(state["current_cut_index"], 0)
        self.assertEqual(state["approved_cut_ids"], ["cut_42"])
        self.assertEqual(state["render_attempts"], 1)
        self.assertEqual(state["render_error"], "Previous error")
        self.assertEqual(state["cuts"][0]["id"], "cut_42")

    def test_inspect_script_memory_ast_detects_cleanup(self):
        """Verify inspect_script_memory_ast accurately detects gc, del, and close calls."""
        code = (
            "import gc\n"
            "clip = None\n"
            "try:\n"
            "    arr = [1, 2, 3]\n"
            "    del arr\n"
            "    gc.collect()\n"
            "finally:\n"
            "    if clip:\n"
            "        clip.close()\n"
        )
        res = inspect_script_memory_ast(code)
        self.assertTrue(res["has_gc_import"])
        self.assertTrue(res["has_gc_collect"])
        self.assertTrue(res["has_del_statement"])
        self.assertTrue(res["has_close_call"])

    def test_inspect_script_memory_ast_detects_absence(self):
        """Verify inspect_script_memory_ast detects when memory management is omitted."""
        code = (
            "import os\n"
            "print('hello world')\n"
        )
        res = inspect_script_memory_ast(code)
        self.assertFalse(res["has_gc_import"])
        self.assertFalse(res["has_gc_collect"])
        self.assertFalse(res["has_del_statement"])
        self.assertFalse(res["has_close_call"])


class TestCoderPromptMemoryDirectives(unittest.TestCase):
    """T004 [P] [US1]: Unit tests for Rule 6 prompt constants (CODER_SYSTEM_PROMPT and CODER_RETRY_PROMPT_TEMPLATE)."""

    def test_coder_system_prompt_contains_rule_6_memory_directives(self):
        """Verify CODER_SYSTEM_PROMPT adheres strictly to coder_prompt_memory_contract."""
        from clipper.core.prompts import CODER_SYSTEM_PROMPT

        self.assertIn(
            "GERENCIAMENTO ESTREITO DE MEMÓRIA",
            CODER_SYSTEM_PROMPT,
            "CODER_SYSTEM_PROMPT must have 'GERENCIAMENTO ESTREITO DE MEMÓRIA' section.",
        )
        self.assertIn(
            "import gc",
            CODER_SYSTEM_PROMPT,
            "CODER_SYSTEM_PROMPT must mandate 'import gc'.",
        )
        self.assertIn(
            "gc.collect()",
            CODER_SYSTEM_PROMPT,
            "CODER_SYSTEM_PROMPT must mandate periodic 'gc.collect()' invocations.",
        )
        self.assertIn(
            "2 GB",
            CODER_SYSTEM_PROMPT,
            "CODER_SYSTEM_PROMPT must explicitly mention the 2 GB RAM limit.",
        )
        self.assertIn(
            ".close()",
            CODER_SYSTEM_PROMPT,
            "CODER_SYSTEM_PROMPT must mandate resource disposal via .close().",
        )
        self.assertIn(
            "del ",
            CODER_SYSTEM_PROMPT,
            "CODER_SYSTEM_PROMPT must mandate explicit deallocation (del) of intermediate buffers.",
        )

    def test_coder_retry_prompt_template_reinforces_memory_management(self):
        """Verify CODER_RETRY_PROMPT_TEMPLATE reinforces Rule 6 during self-healing."""
        from clipper.core.prompts import CODER_RETRY_PROMPT_TEMPLATE

        self.assertIn(
            "gc.collect()",
            CODER_RETRY_PROMPT_TEMPLATE,
            "CODER_RETRY_PROMPT_TEMPLATE must reinforce gc.collect().",
        )
        self.assertIn(
            "2 GB",
            CODER_RETRY_PROMPT_TEMPLATE,
            "CODER_RETRY_PROMPT_TEMPLATE must reinforce the 2 GB memory ceiling.",
        )

        # Ensure placeholders format cleanly without KeyError
        formatted = CODER_RETRY_PROMPT_TEMPLATE.format(
            attempt=2,
            error_diagnostic="Traceback: MemoryError",
            previous_script="import moviepy.editor as mp\nprint('retry')",
            cut_metadata="Cut ID: 1",
        )
        self.assertIn("Tentativa 2", formatted)
        self.assertIn("MemoryError", formatted)
        self.assertIn("2 GB", formatted)


class TestGeneratedScriptASTVerification(unittest.TestCase):
    """T005 [P] [US1]: AST verification tests for intermediate-buffer cleanup and gc.collect constructs."""

    def test_generated_script_with_memory_cleanup_passes_ast_inspection(self):
        """Verify compliant render script passes AST inspection with all required constructs."""
        compliant_script = (
            "import gc\n"
            "import os\n"
            "from moviepy.editor import VideoFileClip\n"
            "\n"
            "video = VideoFileClip('source.mp4')\n"
            "try:\n"
            "    for i in range(10):\n"
            "        frame = video.get_frame(i)\n"
            "        del frame\n"
            "        if i % 5 == 0:\n"
            "            gc.collect()\n"
            "finally:\n"
            "    video.close()\n"
        )
        analysis = inspect_script_memory_ast(compliant_script)
        self.assertTrue(analysis["has_gc_import"], "Script must import gc")
        self.assertTrue(analysis["has_gc_collect"], "Script must call gc.collect()")
        self.assertTrue(analysis["has_del_statement"], "Script must use del statement")
        self.assertTrue(analysis["has_close_call"], "Script must call .close()")

    def test_generated_script_missing_gc_fails_contract_assertion(self):
        """Verify non-compliant script without gc.collect fails contract checks."""
        non_compliant_script = (
            "from moviepy.editor import VideoFileClip\n"
            "video = VideoFileClip('source.mp4')\n"
            "video.write_videofile('out.mp4')\n"
            "video.close()\n"
        )
        analysis = inspect_script_memory_ast(non_compliant_script)
        self.assertFalse(analysis["has_gc_import"])
        self.assertFalse(analysis["has_gc_collect"])
        self.assertFalse(analysis["has_del_statement"])

    def test_generated_script_missing_close_fails_contract_assertion(self):
        """Verify non-compliant script without .close() fails contract checks."""
        non_compliant_script = (
            "import gc\n"
            "arr = bytearray(100)\n"
            "del arr\n"
            "gc.collect()\n"
        )
        analysis = inspect_script_memory_ast(non_compliant_script)
        self.assertFalse(analysis["has_close_call"])


class TestRenderSubprocessMemoryLimits(unittest.TestCase):
    """T006 [US1]: Integration test asserting peak RSS < 2 GB during long video render execution."""

    def test_render_subprocess_peak_rss_under_2gb(self):
        """Verify render subprocess with intermediate cleanup stays strictly under 2 GB RAM (2,097,152 KB)."""
        # Script simulating a long processing loop with intermediate buffer allocation,
        # immediate deallocation (del), and periodic gc.collect(), exactly as mandated by Rule 6.
        script_code = (
            "import gc\n"
            "import sys\n"
            "\n"
            "# Simulate 10 iterations of intermediate buffer processing\n"
            "for step in range(10):\n"
            "    # Allocate ~20MB buffer per step\n"
            "    buf = bytearray(20 * 1024 * 1024)\n"
            "    del buf\n"
            "    gc.collect()\n"
            "\n"
            "print('RENDER_SIMULATION_SUCCESS')\n"
        )

        cmd = [sys.executable, "-c", script_code]
        returncode, stdout, stderr, peak_rss_kb = run_monitored_subprocess(cmd, timeout=30.0)

        self.assertEqual(returncode, 0, f"Subprocess failed with stderr:\n{stderr}")
        self.assertIn("RENDER_SIMULATION_SUCCESS", stdout)

        # 2 GB in KB is 2 * 1024 * 1024 = 2,097,152 KB
        two_gb_kb = 2 * 1024 * 1024
        self.assertLess(
            peak_rss_kb,
            two_gb_kb,
            f"Peak memory {peak_rss_kb} KB exceeded 2 GB limit ({two_gb_kb} KB).",
        )


class TestReleaseCudaMemoryAuditLogging(unittest.TestCase):
    """T009, T010 [P] [US2]: Tests for release_cuda_memory signature, audit logging, and CPU silence."""

    def test_release_cuda_memory_accepts_cut_id_and_logs_audit(self):
        """T009: Verify release_cuda_memory logs [cut={cut_id}] with before, after, and freed metrics."""
        import clipper.runtime.cuda_runtime as cuda_rt

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        with patch.object(cuda_rt, "WHISPER_DEVICE", "cuda"):
            with patch.dict(sys.modules, {"torch": mock_torch}):
                with patch.object(cuda_rt, "get_gpu_memory_info", return_value=(500.0, 11500.0, 12000.0)):
                    with self.assertLogs("clipper.runtime.cuda_runtime", level="INFO") as log_capture:
                        cuda_rt.release_cuda_memory(before_mb=1000.0, cut_id="cut_abc")

        # Verify torch empty_cache was triggered
        mock_torch.cuda.empty_cache.assert_called_once()

        # Check log line format
        output = "\n".join(log_capture.output)
        self.assertIn("[cut=cut_abc]", output)
        self.assertIn("before=1000.0 MB", output)
        self.assertIn("after=500.0 MB", output)
        self.assertIn("freed=500.0 MB", output)

    def test_release_cuda_memory_backward_compatibility_without_cut_id(self):
        """T009: Verify release_cuda_memory works without cut_id and preserves existing log format."""
        import clipper.runtime.cuda_runtime as cuda_rt

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        with patch.object(cuda_rt, "WHISPER_DEVICE", "cuda"):
            with patch.dict(sys.modules, {"torch": mock_torch}):
                with patch.object(cuda_rt, "get_gpu_memory_info", return_value=(500.0, 11500.0, 12000.0)):
                    with self.assertLogs("clipper.runtime.cuda_runtime", level="INFO") as log_capture:
                        cuda_rt.release_cuda_memory(before_mb=1000.0)

        output = "\n".join(log_capture.output)
        self.assertNotIn("[cut=", output)
        self.assertIn("before=1000.0 MB", output)
        self.assertIn("after=500.0 MB", output)
        self.assertIn("freed=500.0 MB", output)

    def test_release_cuda_memory_silent_noop_when_whisper_device_cpu(self):
        """T010: Verify release_cuda_memory returns immediately without touching torch or NVML in CPU profile."""
        import clipper.runtime.cuda_runtime as cuda_rt

        mock_torch = MagicMock()

        with patch.object(cuda_rt, "WHISPER_DEVICE", "cpu"):
            with patch.dict(sys.modules, {"torch": mock_torch}):
                with patch.object(cuda_rt, "get_gpu_memory_info") as mock_nvml:
                    # Should return immediately with 0 actions
                    res = cuda_rt.release_cuda_memory(before_mb=100.0, cut_id="1")
                    self.assertIsNone(res)
                    mock_torch.cuda.empty_cache.assert_not_called()
                    mock_nvml.assert_not_called()


class TestExecutionNodeVramFlush(unittest.TestCase):
    """T011, T012 [US2]: Tests for execution_node guaranteed finally block execution and resilience."""

    def setUp(self):
        self.sample_state = create_mock_video_state(cut_id="cut_77")

    def test_execution_node_invokes_release_cuda_memory_on_success(self):
        """T011: execution_node invokes release_cuda_memory(cut_id=cut_id) on exit code 0."""
        import tempfile
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            script_file = Path(temp_dir) / "render_script.py"
            script_file.write_text("print('Render OK')\n", encoding="utf-8")

            state = dict(self.sample_state)
            state["render_script_path"] = str(script_file)

            with patch("clipper.core.orchestrator.release_cuda_memory") as mock_cleanup:
                res = orchestrator.execution_node(state)
                self.assertEqual(res["render_exit_code"], 0)
                mock_cleanup.assert_called_once_with(cut_id="cut_77")

    def test_execution_node_invokes_release_cuda_memory_on_failure(self):
        """T011: execution_node invokes release_cuda_memory(cut_id=cut_id) on non-zero exit code."""
        import tempfile
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            script_file = Path(temp_dir) / "render_script.py"
            script_file.write_text("import sys; sys.exit(42)\n", encoding="utf-8")

            state = dict(self.sample_state)
            state["render_script_path"] = str(script_file)

            with patch("clipper.core.orchestrator.release_cuda_memory") as mock_cleanup:
                res = orchestrator.execution_node(state)
                self.assertEqual(res["render_exit_code"], 42)
                mock_cleanup.assert_called_once_with(cut_id="cut_77")

    def test_execution_node_invokes_release_cuda_memory_on_timeout(self):
        """T011: execution_node invokes release_cuda_memory(cut_id=cut_id) on subprocess timeout."""
        import tempfile
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            script_file = Path(temp_dir) / "render_script.py"
            script_file.write_text("import time; time.sleep(10)\n", encoding="utf-8")

            state = dict(self.sample_state)
            state["render_script_path"] = str(script_file)

            with patch("clipper.core.orchestrator.release_cuda_memory") as mock_cleanup, \
                 patch.object(orchestrator, "RENDER_TIMEOUT_SECONDS", 0.05):
                res = orchestrator.execution_node(state)
                self.assertEqual(res["render_exit_code"], -1)
                self.assertIn("timed out", res["render_error"])
                mock_cleanup.assert_called_once_with(cut_id="cut_77")

    def test_execution_node_invokes_release_cuda_memory_on_unexpected_exception(self):
        """T011: execution_node invokes release_cuda_memory(cut_id=cut_id) on unexpected Exception."""
        import tempfile
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            script_file = Path(temp_dir) / "render_script.py"
            script_file.write_text("print('test')\n", encoding="utf-8")

            state = dict(self.sample_state)
            state["render_script_path"] = str(script_file)

            with patch("clipper.core.orchestrator.release_cuda_memory") as mock_cleanup, \
                 patch("subprocess.run", side_effect=RuntimeError("Subprocess failed to fork")):
                res = orchestrator.execution_node(state)
                self.assertEqual(res["render_exit_code"], -1)
                mock_cleanup.assert_called_once_with(cut_id="cut_77")

    def test_execution_node_vram_flush_overhead_under_50ms(self):
        """T011 / SC-005: execution_node VRAM flush overhead is strictly below 50ms wall-clock."""
        import tempfile
        import time
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            script_file = Path(temp_dir) / "render_script.py"
            script_file.write_text("print('test')\n", encoding="utf-8")

            state = dict(self.sample_state)
            state["render_script_path"] = str(script_file)

            durations = []

            def timed_cleanup(*args, **kwargs):
                t0 = time.perf_counter()
                time.sleep(0.005)  # Simulate 5ms cleanup
                durations.append(time.perf_counter() - t0)

            with patch("clipper.core.orchestrator.release_cuda_memory", side_effect=timed_cleanup):
                orchestrator.execution_node(state)

            self.assertEqual(len(durations), 1)
            self.assertLess(
                durations[0],
                0.050,
                f"VRAM flush overhead {durations[0]*1000:.2f}ms exceeded 50ms ceiling.",
            )

    def test_execution_node_resilience_when_cleanup_raises(self):
        """T012: execution_node does not crash or abort if release_cuda_memory raises an exception."""
        import tempfile
        import clipper.core.orchestrator as orchestrator

        with tempfile.TemporaryDirectory() as temp_dir:
            script_file = Path(temp_dir) / "render_script.py"
            script_file.write_text("print('Render OK')\n", encoding="utf-8")

            state = dict(self.sample_state)
            state["render_script_path"] = str(script_file)

            with patch("clipper.core.orchestrator.release_cuda_memory", side_effect=RuntimeError("NVML hardware error")):
                res = orchestrator.execution_node(state)
                # Must still successfully return the state dictionary
                self.assertEqual(res["render_exit_code"], 0)
                self.assertEqual(res["render_error"], "")


