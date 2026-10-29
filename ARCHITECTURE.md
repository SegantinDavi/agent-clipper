# Architecture & Project Layout

## Overview
`agent-clipper` is an automated Docker-based video clipping pipeline designed to turn long YouTube videos into vertical short clips (Shorts/TikTok/Reels) with human approval (HITL) and dual LLM backend profiles (local Ollama or Gemini API).

## Directory Structure
- `src/clipper/`
  - `core/`: Pipeline nodes, LangGraph DAG orchestration, transcription, ingestion, editing, and pause detection.
  - `runtime/`: Configuration, runtime options, and CUDA setup.
- `tests/`: Unit and integration test suite (`unittest`).
- `specs/`: Feature specifications, architectures, plans, and task breakdowns following Spec-Driven Development (SDD).
- `tools/`: Utility scripts for model management and diagnostics.
- `dockerfile`, `run_pipeline.sh`: Container and execution scripts.
