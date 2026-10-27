# Phase 0 Research: Modular Domain Repository Restructuring

**Feature Branch**: `009-repo-restructure`  
**Date**: 2026-10-27  
**Spec**: [spec.md](spec.md)  

## Overview

The goal of this refactoring is to transition the `agent-clipper` repository from a flat root layout (where 12 application modules, 9 test files, and miscellaneous drafts reside together) to a clean, domain-driven structure under `src/clipper/` with dedicated subpackages and an isolated `tests/` directory, while preserving 100% of the runtime behavior, memory management rules, and Docker workflows defined in `AGENTS.md`.

---

## Technical Decisions

### Decision 1: Domain Package Hierarchy (`src/clipper/`)

- **Decision**: Group functional Python code under `src/clipper/` with four distinct subpackages:
  - `core/`: State management, LangGraph orchestration, prompts, Pydantic schemas, ingestion, chunking.
  - `video/`: Media editing, vertical 9:16 layout, caption burning, pause shortening, active speaker tracking.
  - `review/`: Cut approval server, review HTML/JSON manifests, and human-in-the-loop coordination.
  - `runtime/`: Configuration, hardware profile options (Ollama/Gemini), and CUDA runtime bootstrap.
- **Rationale**:
  - `src/` layout prevents accidental imports of uninstalled/incomplete local code over system packages and is the Python packaging standard (PEP 518/PEP 621).
  - Clear domain separation reduces cognitive load: changes to video rendering do not risk touching orchestration or configuration.
  - Keeps package boundaries strictly acyclic: `runtime` has no internal dependencies; `core.schemas` is standalone; `video` and `review` import schemas/config; `orchestrator` connects the graph.
- **Alternatives Considered**:
  - *Flat `src/` (no subpackages)*: Simpler, but only moves the clutter from root into `src/`. Does not solve domain organization as the codebase grows.
  - *Feature slicing (vertical slices per feature like `cut_approval/`, `speaker_focus/`)*: Over-fragments shared utilities (MoviePy clips, schemas, config) leading to circular dependencies.

---

### Decision 2: Project Root Anchoring for Paths (`config.py`)

- **Decision**: Update `config.py` to anchor the project root dynamically using:
  ```python
  # In src/clipper/runtime/config.py
  PROJECT_ROOT = Path(__file__).resolve().parents[3]  # src/clipper/runtime/ -> agent-clipper/
  ```
  And anchor paths such as `OUTPUT_DIR`, `ASSETS_DIR`, and `.env` loading to `PROJECT_ROOT`.
- **Rationale**:
  - In a flat structure, `Path(__file__).resolve().parent` pointed directly to the root. Moving `config.py` to `src/clipper/runtime/` is 3 levels down.
  - Explicitly anchoring paths ensures that `OUTPUT_DIR` (`/app/output` or `./output`) and `assets/speaker_focus` resolve identically in both Docker (`/app`) and local WSL2 development.
- **Alternatives Considered**:
  - *Relying on `Path.cwd()`*: Fragile if commands or tests are executed from a subdirectory or subshell.
  - *Hardcoding paths*: Violates AGENTS.md rule 7 ("Nenhuma URL ou parâmetro deve ficar hardcoded").

---

### Decision 3: Import Resolution & Execution Strategy

- **Decision**: Use standardized absolute imports starting from `clipper`:
  ```python
  from clipper.core.schemas import CorteVideo
  from clipper.runtime.config import OUTPUT_DIR, WHISPER_DEVICE
  from clipper.video.editor import cut_and_format_video
  ```
  Execution will support both:
  1. `PYTHONPATH=src python -m clipper.core.orchestrator`
  2. `run_pipeline.sh` setting `PYTHONPATH="$project_dir/src${PYTHONPATH:+:$PYTHONPATH}"`.
- **Rationale**:
  - Avoids brittle relative imports (`from ...runtime.config import ...`).
  - Standardizes test discovery and container execution.
  - `run_pipeline.sh` continues to work out-of-the-box for developers without requiring `pip install -e .`.
- **Alternatives Considered**:
  - *Relative imports (`from ..runtime import config`)*: Fails when scripts or entrypoints are run directly (`python src/clipper/core/orchestrator.py`).
  - *Forcing editable install (`pip install -e .`)*: Adds unnecessary friction for container building and minimal dev environments.

---

### Decision 4: Unit Test Suite Migration & Mock Targets

- **Decision**: Relocate all `test_*.py` files from repository root into `tests/` and update all `unittest.mock.patch` target strings.
- **Rationale**:
  - Test files in the root pollute the directory and cause confusion between test code and production code.
  - When tests use `@patch("editor.cut_and_format_video")` or `@patch("orchestrator.download_video")`, these strings must be updated to target the new module paths (e.g., `@patch("clipper.video.editor.cut_and_format_video")` or `@patch("clipper.core.orchestrator.download_video")`).
  - Test runners can now simply execute `python -m unittest discover tests/ -p "test_*.py"` or `pytest tests/`.
- **Alternatives Considered**:
  - *Leaving tests in root*: Rejected because cleaning up the root is a core requirement of this feature.
  - *Splitting tests into subdirectories per domain*: Unnecessary overhead for 9 test files; a single `tests/` folder is standard and clean.

---

### Decision 5: Dockerfile & Pipeline Script Harmonization

- **Decision**:
  - Update `dockerfile`:
    - Set `ENV PYTHONPATH=/app/src`
    - Update `CMD ["python", "-m", "clipper.core.orchestrator"]`
  - Update `run_pipeline.sh`:
    - Add `export PYTHONPATH="$project_dir/src${PYTHONPATH:+:$PYTHONPATH}"`
    - Update script checks for `orchestrator` and `cuda_runtime` to invoke via `clipper.core.orchestrator` and `clipper.runtime.cuda_runtime`.
- **Rationale**:
  - Completely preserves external volume mounting (`/app/output`), memory limits, and dependency caching layers (`av<19`, `requirements-cuda.txt`).
- **Alternatives Considered**:
  - *Creating a root wrapper `orchestrator.py`*: Defeats the purpose of cleaning the root directory.

---

## Constitution & Memory Compliance

| Principle / Rule | Compliance Analysis |
|---|---|
| **WSL 8GB RAM / RTX 3060 12GB VRAM** | Structural refactoring only. Zero change to memory allocation, tensor shapes, or model lifecycles. |
| **Ingestion & Preventative Slicing** | `node_0.py` and `ingestion.py` moved to `clipper.core` without logic alterations. |
| **LangGraph DAG Persistence** | `SqliteSaver` database location remains `/app/output/estado.db`. |
| **Single-Model Cognitive Routing** | `prompts.py` and `orchestrator.py` logic untouched. |
| **MoviePy 1.0.3 & ImageMagick** | Video dimensions, pix_fmt, and chain concatenation preserved in `clipper.video`. |
| **Clean Code & English Naming** | Package and module names are concise, standard English (`clipper.core`, `clipper.video`, `clipper.review`, `clipper.runtime`). |
| **Zero External Heavy Telemetry** | No new telemetry libraries introduced. |
| **SDD Preceding Changes** | Comprehensive SDD in `specs/009-repo-restructure/` before touching any code. |
