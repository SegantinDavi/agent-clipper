# Feature Specification: Deep CUDA VRAM Cleanup in Gemini Profile

**Feature Branch**: `012-cuda-vram-cleanup`  
**Created**: 2026-10-29  
**Status**: Draft  
**Issue**: #012 — [Arquitetura] Garantir liberação profunda de VRAM no perfil Gemini (CUDA)

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Long-video Processing Without OOM Crash (Priority: P1)

An operator runs the pipeline in the Gemini profile against a YouTube video of 1 hour or more. The video is split into multiple audio chunks and each chunk is transcribed by Whisper running on the GPU. After processing, the operator expects the pipeline to complete without triggering a CUDA out-of-memory (OOM) error on the RTX 3060, regardless of video length.

**Why this priority**: This is the highest-risk failure mode in the Gemini profile. A gradual VRAM leak across chunks will eventually crash the process, making long-video support unreliable in production.

**Independent Test**: Can be validated by processing a ≥60-minute video in Gemini profile and monitoring VRAM usage with `nvidia-smi` between each chunk — VRAM must drop back to baseline after each chunk completes.

**Acceptance Scenarios**:

1. **Given** a video longer than 15 minutes processed in the Gemini profile, **When** each audio chunk finishes transcription, **Then** the GPU memory used by the transcription process is fully released before the next chunk begins.
2. **Given** the Gemini profile is active and five or more consecutive chunks are transcribed, **When** monitoring VRAM usage externally, **Then** the VRAM consumption does not grow monotonically between chunks (i.e., no cumulative leak).
3. **Given** a GPU with 12 GB VRAM running the Gemini profile, **When** transcribing a 90-minute video split into 10 chunks, **Then** the pipeline completes successfully without any OOM error or CUDA crash.

---

### User Story 2 — Observability of VRAM Release Events (Priority: P2)

An operator wants to confirm that VRAM cleanup is actually happening between chunks, without needing to attach an external profiler. Log entries should record before-and-after VRAM state (or at minimum confirm cleanup was triggered) so issues can be diagnosed from `pipeline.log` alone.

**Why this priority**: Silent leaks are hard to detect retroactively. Logging cleanup events allows post-mortem diagnosis even if `nvidia-smi` was not monitored in real time.

**Independent Test**: Can be validated by inspecting `pipeline.log` after a multi-chunk run and confirming that a cleanup confirmation entry appears after each chunk's transcription.

**Acceptance Scenarios**:

1. **Given** the Gemini profile is active and a chunk is transcribed, **When** the cleanup routine finishes, **Then** a log entry at INFO level is written confirming GPU memory was flushed.
2. **Given** cleanup is triggered but the GPU backend returns an error or is unavailable, **When** the error occurs, **Then** the pipeline logs a WARNING and continues — cleanup failure must not abort processing.

---

### User Story 3 — Ollama Profile Is Unaffected (Priority: P3)

An operator running the pipeline in the Ollama (local/CPU) profile expects no change in behavior. The CUDA cleanup path must be completely isolated from the CPU/Ollama profile so that no CUDA import or call is made in that mode.

**Why this priority**: Importing CUDA libraries when Ollama is active wastes memory and may raise errors on machines without a compatible CUDA installation.

**Independent Test**: Can be validated by running the pipeline in the Ollama profile on a machine with no GPU and confirming no CUDA-related import error or warning appears in logs.

**Acceptance Scenarios**:

1. **Given** `LLM_PROVIDER=ollama`, **When** a chunk transcription completes, **Then** no CUDA or GPU cleanup call is made and no CUDA library is imported.
2. **Given** `LLM_PROVIDER=ollama` on a CPU-only machine, **When** the pipeline runs end-to-end, **Then** it completes without any CUDA-related exception.

---

### Edge Cases

- What happens when the GPU cleanup call itself raises an exception (e.g., CUDA driver not initialised)?
- How does the system handle a machine where CUDA is installed but the GPU has already been claimed by another process?
- What happens if the chunk iterator (`segments`) has not been fully consumed before `del model` is called — does the generator hold a reference that prevents cleanup?
- How does cleanup behave when `av<19` raises a metadata error mid-chunk extraction, leaving the model partially loaded?

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After each audio chunk transcription in the Gemini profile, the system MUST explicitly release all GPU memory allocated by the transcription model before loading the next chunk.
- **FR-002**: The GPU memory release routine MUST be invoked only when the active provider profile is Gemini (CUDA); it MUST NOT execute in the Ollama (CPU) profile.
- **FR-003**: The cleanup routine MUST fully exhaust or close the lazy segment iterator before destroying the model, preventing dangling generator references that could retain GPU allocations.
- **FR-004**: The system MUST log a confirmation at INFO level each time GPU memory is explicitly flushed between chunks.
- **FR-005**: A failure in the GPU cleanup routine MUST be caught, logged as a WARNING, and MUST NOT propagate as an exception that aborts chunk processing.
- **FR-006**: The cleanup implementation MUST use only libraries already present in the authorised stack (`ctranslate2`, `torch` — if available in the CUDA bootstrap) with no new heavyweight dependencies introduced.
- **FR-007**: The existing Python garbage-collection sequence (`del model`, `gc.collect()`) in `clipper.core.ingestion` MUST be preserved, preceded by explicit CTranslate2 model deallocation (`model.model.unload_model()` if available) and followed by the deep GPU cache flush (`release_cuda_memory()`).

### Key Entities

- **Transcription Chunk**: A single audio file segment produced by FFmpeg silence detection, fed as input to one Whisper model instance.
- **GPU Cleanup Routine**: The deterministic sequence of steps — close iterator, delete model, run GC, flush GPU cache — executed after each chunk in the Gemini profile.
- **Provider Profile**: The runtime mode (`ollama` | `gemini`) that governs hardware usage rules, determined at startup via `LLM_PROVIDER` before any CUDA libraries are imported.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A video of 60 minutes or longer, split into at least 6 chunks, completes transcription in the Gemini profile without any OOM or CUDA crash.
- **SC-002**: VRAM usage measured between consecutive chunk transcriptions does not exceed the peak of the first chunk by more than 5% — confirming no cumulative leak.
- **SC-003**: For every chunk processed in the Gemini profile, exactly one GPU flush confirmation log entry appears in `pipeline.log`.
- **SC-004**: Running the same pipeline with `LLM_PROVIDER=ollama` produces zero CUDA-related log warnings or errors.
- **SC-005**: The cleanup failure path (simulated by mocking the flush call to raise an exception) results in a WARNING log entry and the pipeline continues to the next chunk without crashing.

---

## Assumptions

- The existing chunking (FFmpeg silence detection) and the `transcribe_audio_chunk` function in `clipper.core.ingestion` are the sole transcription entry points and are the correct location for the fix.
- `faster-whisper` and `ctranslate2` are the primary inference packages in `requirements-cuda.txt`. Device model unloading (`ct2_model.unload_model()`) combined with Python garbage collection (`del model`, `gc.collect()`) is the primary GPU VRAM release mechanism. `torch` is not a required dependency in `requirements-cuda.txt` and is handled strictly as an optional runtime probe if already present in `sys.modules`.
- The Gemini profile detection relies on the already-established `LLM_PROVIDER` environment variable, which is resolved before any CUDA imports per Rule 1.
- No new telemetry, profiling library, or external monitoring tool is introduced — observability is achieved solely through the existing `logging` infrastructure writing to `pipeline.log`.
- The fix is confined to `clipper.core.ingestion` (and possibly `clipper.runtime.cuda_runtime`) with no changes to the LangGraph graph structure, node definitions, or checkpointer configuration.
