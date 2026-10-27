# Developer Quickstart: Modular Domain Layout

**Feature Branch**: `009-repo-restructure`  
**Date**: 2026-10-27  

This guide provides immediate instructions for navigating, developing, and testing within the new modular domain structure of `agent-clipper`.

---

## Directory Overview

```text
agent-clipper/
├── src/clipper/               # All application source code
│   ├── core/                  # Orchestrator, LangGraph nodes, schemas, prompts, ingestion
│   ├── video/                 # MoviePy editor, pause shortening, speaker focus
│   ├── review/                # Approval web server and review manifests
│   └── runtime/               # Environment config, CUDA runtime, runtime CLI options
├── tests/                     # All test modules
├── docs/                      # Reference documents and notes
├── tools/                     # Auxiliary offline utilities
├── assets/                    # Static models and assets
├── specs/                     # Specification-driven development (SDD) specs
├── output/                    # Pipeline outputs, renders, and checkpoints (mapped volume)
├── dockerfile                 # Container image specification
└── run_pipeline.sh            # Root runner script
```

---

## Common Developer Tasks

### 1. Running Unit & Regression Tests

Run all tests from the repository root:

```bash
# Using Python directly (requires PYTHONPATH=src):
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"

# Or using run_pipeline.sh (automatically manages PYTHONPATH):
./run_pipeline.sh -m unittest discover tests/ -p "test_*.py"

# Running a specific test file:
PYTHONPATH=src venv/bin/python -m unittest tests/test_editor_render.py
```

### 2. Running the Pipeline Locally

```bash
# Interactive menu:
./run_pipeline.sh

# Non-interactive CLI flags:
./run_pipeline.sh --provider ollama --no-silence-cuts
./run_pipeline.sh --provider gemini --silence-cuts
```

### 3. Building and Running with Docker

```bash
# Build Docker image:
docker build -t agent-clipper .

# Run with output volume mounted:
docker run --rm -it \
  -v $(pwd)/output:/app/output \
  -e YOUTUBE_URL="https://www.youtube.com/watch?v=EXAMPLE" \
  agent-clipper
```

---

## Coding Guidelines Under the Modular Layout

1. **Where does new code go?**
   - New graph steps or ingestion logic: `src/clipper/core/`
   - New audio/video filters or computer vision helpers: `src/clipper/video/`
   - User approval UI or API alterations: `src/clipper/review/`
   - Environment variables or hardware detection: `src/clipper/runtime/`
   - **Never add new Python modules directly to the root directory.**

2. **How to import?**
   - Always use absolute imports starting with `clipper.<domain>.<module>`:
     ```python
     from clipper.runtime.config import OUTPUT_DIR
     from clipper.core.schemas import CorteVideo
     from clipper.video.editor import cut_and_format_video
     ```
