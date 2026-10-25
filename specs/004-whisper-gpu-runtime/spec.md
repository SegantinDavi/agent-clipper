# Feature Specification: Restore reliable Whisper GPU execution

**Created**: 2026-10-25
**Status**: Implementation authorized by the user's GPU restoration request.
**Input**: Remove the CPU-only directive and use the GPU without repeating the cuBLAS loading failure.

Prepared with the official Spec Kit specification template:
https://github.com/github/spec-kit/blob/main/templates/spec-template.md.
The Specify/Spec Kit CLI is not installed in this environment; this document uses
the template workflow without claiming CLI execution.

## User Scenarios & Testing

### User Story 1 - Transcribe on the GPU (Priority: P1)

Run the existing pipeline on WSL/Linux using Whisper small, CUDA and float16.
The user explicitly supersedes the CPU-only rule in AGENTS.md. Keep chunking,
sequential processing, iterator closure and garbage collection unchanged.

Acceptance scenarios:
1. Starting through the shell launcher discovers the active venv's NVIDIA libraries
   before loading CTranslate2 and validates the driver, libraries and compute type.
2. Starting orchestrator.py directly performs the same setup before media work.
3. A cached Whisper model actually consumes audio on the GPU without a library error.

### User Story 2 - Diagnose incompatible installations (Priority: P2)

Missing packages, absent libraries, unavailable GPUs or unsupported compute types
must produce actionable errors before downloading or transcribing media. Do not
silently switch to the CPU. Explicit CPU/int8 remains available when requested.

### Edge Cases

- Existing LD_LIBRARY_PATH entries are preserved after the venv's runtime paths.
- A process requiring new loader paths restarts once before importing GPU packages;
  preserve interpreter flags and arguments, and do not restart inside graph nodes.
- Missing pip runtime directories report the requirements installation command.
- The Linux/WSL/Docker runtime is the supported GPU bootstrap target.
- Old shell exports override defaults; document how to replace cpu/int8 exports.
- Docker requires GPU passthrough; a build without a visible GPU remains possible.

## Requirements

- FR-001: Default to cuda/float16 and remove the transcription CPU-only guard.
- FR-002: Add a standard-library-only CUDA bootstrap, discover runtime directories
  from installed NVIDIA packages, and configure LD_LIBRARY_PATH before inference.
- FR-003: Bootstrap both the launcher and direct orchestrator entry point. Validate
  libcublasLt.so.12, libcublas.so.12 and libcudnn.so.9, GPU availability and compute type.
- FR-004: Pin the tested combination: faster-whisper 1.2.1, CTranslate2 4.8.3,
  nvidia-cublas-cu12 12.9.2.10 and nvidia-cudnn-cu12 9.27.0.42. Share the runtime
  requirements between WSL installation and Docker, keeping heavy installs separate.
- FR-005: Update AGENTS.md, the environment example and README. Preserve existing
  backend credentials, graph, persistence, prompts, editing and resource cleanup.
- FR-006: Test environment preservation, missing runtime/GPU diagnostics, CPU bypass,
  argument preservation and mocked transcription cleanup. Run the cached-model GPU
  smoke test, consuming the lazy iterator, without downloading models or API calls.

## Success Criteria

- The installed GPU accepts float16 and the real cached-model smoke test passes.
- Regression tests pass, including timestamps, cleanup and extraction behavior.
- Both entry points initialize the same runtime; CPU overrides need no CUDA packages.
- No new external telemetry, LLM, inference API call or model download is introduced.

## References

- https://github.com/SYSTRAN/faster-whisper#gpu
- https://github.com/SYSTRAN/faster-whisper#install-with-pip-linux-only

## Validation results

- PASS: 2 real GPU integration tests in the WSL venv: cached Whisper small decoded
  synthetic audio on CUDA/float16; direct orchestrator startup succeeded after
  explicitly removing LD_LIBRARY_PATH from the child environment.
- PASS: 16 bootstrap, transcription and mocked-LLM regression tests.
- PASS: Python source parsing and git diff whitespace checks.
- Existing installed versions match requirements-cuda.txt; no dependency install,
  inference API request or model download was needed.
- Dockerfile updated to install the same pinned runtime, but Docker was not tested.
  No Docker executable was available in the Windows command inventory; WSL results
  do not imply a container validation.
