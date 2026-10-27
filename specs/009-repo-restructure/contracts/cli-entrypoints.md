# Contract: CLI Entrypoints & Container Invocation

**Feature Branch**: `009-repo-restructure`  
**Date**: 2026-10-27  
**Spec**: [spec.md](../spec.md)  

## CLI & Execution Contracts

### 1. `run_pipeline.sh` Contract

`./run_pipeline.sh` is the primary entrypoint for host/WSL2 execution.

```bash
# Running without arguments launches the interactive runtime options or default pipeline
./run_pipeline.sh

# Passing pipeline CLI flags forwards directly to clipper.core.orchestrator
./run_pipeline.sh --help
./run_pipeline.sh --provider gemini --silence-cuts

# Passing test or custom python commands forwards via python -m
./run_pipeline.sh -m unittest discover tests/ -p "test_*.py"
```

#### Environment Export in Script
```bash
export PYTHONPATH="$project_dir/src${PYTHONPATH:+:$PYTHONPATH}"
```

---

### 2. Docker Container Contract

The container build and entrypoint must remain compatible with Docker workflows.

#### Dockerfile Updates
```dockerfile
# Working directory remains /app
WORKDIR /app

# Dependencies installed as before...
COPY requirements.txt .
COPY requirements-cuda.txt .
RUN pip install ...

# Copy source repository
COPY . .

# Set PYTHONPATH to include src
ENV PYTHONPATH=/app/src

# Default command invokes orchestrator via package module
CMD ["python", "-m", "clipper.core.orchestrator"]
```

---

### 3. Test Runner Contract

All tests must be executable with standard discovery from the repository root:

```bash
# Unittest execution:
PYTHONPATH=src python -m unittest discover tests/ -p "test_*.py"

# Or through run_pipeline.sh wrapper:
./run_pipeline.sh -m unittest discover tests/ -p "test_*.py"
```
