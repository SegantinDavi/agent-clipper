# Feature Specification: Modular Domain Repository Restructuring

**Feature Branch**: `009-repo-restructure`  
**Created**: 2026-10-27  
**Status**: Draft  
**Input**: User description: "Quero organizar os arquivos e diretorios do projeto, pois ele cresceu e agora tem um monte de arquivo na raiz, está ficando ruim de se achar. Poderia me propor uma estrutura para organizar o repositorio? (...) vamos proceguir fazendo o spec seguindo a opção 1 por domínio."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Clear Codebase Navigation by Domain (Priority: P1)

As a developer or maintainer working on agent-clipper, I want the codebase organized into logical domain packages (`core`, `video`, `review`, `runtime`) under `src/clipper` and all test suites under `tests/`, so that I can easily locate code, understand module responsibilities, and avoid clutter in the repository root.

**Why this priority**: Directly resolves the primary pain point of having 31+ mixed files in the root directory, establishing architectural order without modifying business logic.

**Independent Test**: Can be tested by inspecting the directory tree to verify that all functional code is cleanly grouped under `src/clipper/` subpackages, all test files are located under `tests/`, and root files are limited strictly to project-level configuration, entrypoints, and documentation.

**Acceptance Scenarios**:

1. **Given** the restructured repository, **When** examining the root directory, **Then** only project-level files (`dockerfile`, `run_pipeline.sh`, `requirements*.txt`, `README.md`, `AGENTS.md`, `.env.example`, `.gitignore`, `.dockerignore`) and standard top-level directories (`src`, `tests`, `docs`, `tools`, `assets`, `specs`, `output`) are present.
2. **Given** a developer looking for video rendering, speaker tracking, or silence pause trimming, **When** navigating `src/clipper/video/`, **Then** `editor.py`, `pause_editing.py`, and `speaker_focus.py` are found in that dedicated directory.
3. **Given** a developer looking for orchestration, transcription, or LLM prompts/schemas, **When** navigating `src/clipper/core/`, **Then** `orchestrator.py`, `ingestion.py`, `node_0.py`, `prompts.py`, and `schemas.py` are found in that dedicated directory.
4. **Given** a developer looking for runtime profiles, CUDA bootstrap, or environment config, **When** navigating `src/clipper/runtime/`, **Then** `config.py`, `cuda_runtime.py`, and `runtime_options.py` are found in that dedicated directory.
5. **Given** a developer looking for human-in-the-loop cut approval, **When** navigating `src/clipper/review/`, **Then** `review.py` is found in that dedicated directory.

---

### User Story 2 - Seamless Execution and Container Compatibility (Priority: P1)

As an operator running the pipeline via `run_pipeline.sh` or inside the Docker container, I want the restructured application to execute identically without import errors, broken paths, or regressions in CLI flags, profile selection, or output generation.

**Why this priority**: A directory refactoring must never break execution, container build, or developer workflow.

**Independent Test**: Can be tested by invoking `./run_pipeline.sh --help` (or interactive mode) and building/running the Docker container image with `python -m clipper.core.orchestrator`.

**Acceptance Scenarios**:

1. **Given** the updated entrypoints, **When** running `./run_pipeline.sh` from the repository root, **Then** it correctly resolves the Python environment and launches the orchestrator or CUDA runtime without `ModuleNotFoundError` or broken relative paths.
2. **Given** the updated `dockerfile`, **When** the container image is built and run, **Then** `src/` is packaged properly, Python finds the `clipper` package, and execution starts as expected.
3. **Given** existing output artifacts and checkpoint paths (`/app/output` / `./output`), **When** running the pipeline, **Then** paths continue to resolve to the external volume without path regressions.

---

### User Story 3 - Comprehensive Test Suite Execution (Priority: P2)

As a developer running automated tests, I want all unit and integration tests located under `tests/` to run cleanly via standard test runners without manual path hacks or broken cross-module imports.

**Why this priority**: Ensures continuous integration and regression testing remain automated, standard, and easy to run.

**Independent Test**: Can be tested by executing `python -m unittest discover tests/ -p "test_*.py"` from the repository root and verifying that all tests pass identically to the baseline.

**Acceptance Scenarios**:

1. **Given** test files relocated to `tests/`, **When** running `python -m unittest discover tests/ -p "test_*.py"`, **Then** all test modules are discovered automatically.
2. **Given** any test importing production modules, **When** tests execute, **Then** all package imports (`from clipper.core...`, `from clipper.video...`, etc.) resolve cleanly without requiring changes to PYTHONPATH outside standard project execution.
3. **Given** test mocks for MoviePy, faster-whisper, and LLM completions, **When** running tests, **Then** mocked target paths correctly match the new module paths.

---

### Edge Cases

- **Relative file path assumptions**: If any module relied on `__file__` or `Path.cwd()` to locate `assets/` or `output/`, moving modules one or two directory levels deeper (`src/clipper/<domain>/`) must not break path resolution to root assets or output directories.
- **Mock targets in unit tests**: Tests patching symbols (e.g., `@patch("editor.cut_and_format_video")` or `@patch("orchestrator.download_video")`) will fail if patch target strings are not updated to match the new package namespace (e.g. `@patch("clipper.core.orchestrator.download_video")`).
- **Draft documents in root**: Loose non-code files like `prompts_revisado.txt` must be preserved in a dedicated `docs/` folder rather than deleted.
- **Docker caching and COPY layers**: `dockerfile` must copy `src/` and dependencies in an optimal order while keeping `av<19` and CUDA dependencies isolated as mandated by AGENTS.md.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST package all functional Python code under a top-level source package `src/clipper/` with appropriate `__init__.py` files.
- **FR-002**: The system MUST organize the application into four distinct domain subpackages:
  - `src/clipper/core/`: contains `orchestrator.py`, `ingestion.py`, `node_0.py`, `prompts.py`, `schemas.py`.
  - `src/clipper/video/`: contains `editor.py`, `pause_editing.py`, `speaker_focus.py`.
  - `src/clipper/review/`: contains `review.py`.
  - `src/clipper/runtime/`: contains `config.py`, `cuda_runtime.py`, `runtime_options.py`.
- **FR-003**: The system MUST move all test files (`test_*.py`) from the root directory into `tests/`.
- **FR-004**: The system MUST update internal import statements across all modules and tests to use clear package imports (e.g. `from clipper.core.schemas import CorteVideo`, `from clipper.video.editor import cut_and_format_video`).
- **FR-005**: Path references to root directories (`output/`, `assets/`, `.env`) in `config.py` and other modules MUST remain anchored to the project root regardless of the file's directory depth.
- **FR-006**: The system MUST move loose documentation and draft notes (such as `prompts_revisado.txt`) to a `docs/` directory.
- **FR-007**: The system MUST update `run_pipeline.sh` and `dockerfile` to invoke the orchestrator and runtime via the new package structure (e.g., `python -m clipper.core.orchestrator` or equivalent entrypoint).
- **FR-008**: The refactoring MUST NOT alter any business logic, LLM prompt content, video processing algorithms, silence detection thresholds, or hardware-specific constraints established in AGENTS.md.

### Key Entities *(Package Structure)*

- **`clipper.core`**: Represents the orchestration and data flow domain, defining the LangGraph state machine, YouTube ingestion, preventative chunking, and LLM reasoning/extraction.
- **`clipper.video`**: Represents the media processing domain, handling MoviePy composition, silence pause reduction, subtitle burning, and speaker facial framing.
- **`clipper.review`**: Represents the human-in-the-loop domain, managing review HTTP servers, interactive approval UI, and cut authorization manifests.
- **`clipper.runtime`**: Represents the execution environment and infrastructure domain, handling environment variable parsing, hardware profiles (Ollama CPU vs Gemini GPU), and CUDA runtime dynamic library loading.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Root directory file count is reduced by at least 60% (from 31 files down to standard root configuration and documentation files).
- **SC-002**: 100% of existing unit and regression tests in `tests/` pass without errors under the new package structure.
- **SC-003**: Pipeline entrypoint (`./run_pipeline.sh`) executes and displays help/options cleanly from the repository root.
- **SC-004**: Zero functional regressions in video rendering, pause calculation, or cut approval data structures.
- **SC-005**: All imports conform to standard Python package conventions without circular dependencies or runtime warnings.
