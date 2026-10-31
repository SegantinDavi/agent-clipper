# Quickstart: Feature 016 — Dynamic Scene Scripting via Constrained Decoding

**Branch**: `016-dynamic-scene-scripting`

---

## Overview

Feature 016 implements Phase 2 of the AI agent pipeline: **Dynamic Scene Scripting via Constrained Decoding**. It expands the Pydantic data model with a `Scene` entity and refactors the Extractor node prompts (`EXTRACTOR_SYSTEM_PROMPT_TEMPLATE`, `EXTRACTOR_FEW_SHOT_EXAMPLES`) so that every validated cut is autonomously partitioned into 2–4 second scenes with contextual visual metaphors and dynamic animation triggers.

---

## Modified Files

| File | Changes |
|---|---|
| `src/clipper/core/schemas.py` | Defines `Scene(BaseModel)` and adds `scenes: list[Scene]` to `CorteVideo` |
| `src/clipper/core/prompts.py` | Refactors `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` and updates few-shot assistant messages with concrete `scenes` |
| `src/clipper/core/orchestrator.py` | Hardens `extractor_node` with fail-fast validation for empty scenes and editorial duration logging (> 4s) |
| `src/clipper/review/review.py` | Updates `render_review_page` to display scene breakdowns inside preview cards |
| `tests/test_scene_scripting.py` | **New file**: Comprehensive test suite covering schema constraints, extractor prompts, SQLite persistence, and HITL rendering |

---

## Verification & Testing

### 1. Run Feature-Specific Test Suite

Execute the dedicated scene scripting test suite:

```bash
PYTHONPATH=src venv/bin/python -m unittest tests/test_scene_scripting.py
```

### 2. Run Synchronous Contract & Review Tests

Ensure Instructor integration and human-in-the-loop review continue operating smoothly:

```bash
PYTHONPATH=src venv/bin/python -m unittest tests/test_instructor_sync_contract.py tests/test_review.py
```

### 3. Run Full Discovery Regression Suite

Verify that all existing functionality (CUDA runtime, pause editing, visual identity, etc.) remains 100% regression-free (≥ 172 tests):

```bash
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
```

---

## Inspecting Generated Scenes

### 1. In `pipeline.log`

Run the pipeline and check extractor logs:

```bash
grep -E "Extraction completed|Scene" output/pipeline.log
```

Expected output:
```text
Extraction completed successfully: 2 cuts validated.
  [1] 'Seis meses construindo algo sem demanda' (120.00s - 175.00s) - 4 scenes
```

### 2. In `review.json`

Check the generated review manifest:

```bash
cat output/reviews/*/review.json | jq '.cuts[0].scenes'
```

Expected JSON output:
```json
[
  {
    "start_word": "O",
    "end_word": "problema",
    "visual_metaphor": "alvo com flecha errada",
    "animation_trigger": "zoom_in"
  },
  {
    "start_word": "Passamos",
    "end_word": "prioridade",
    "visual_metaphor": "calendário folheando",
    "animation_trigger": "cut_transition"
  }
]
```

### 3. In the Web Review Interface

When `approval_node` launches the local review server, visit `http://localhost:8765`:
- Each cut card displays the video preview alongside a numbered list of scenes with spoken word ranges, visual metaphors, and animation triggers.
