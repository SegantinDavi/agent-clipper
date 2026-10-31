# Quickstart: Feature 015 — Visual Identity & Global State

**Branch**: `015-visual-identity-state`

---

## Overview

This feature adds a `style_node` to the LangGraph pipeline that loads brand style configuration from an optional `estilo.json` file and propagates it through `VideoState.visual_identity` to all caption-rendering nodes.

---

## New Files

| File | Purpose |
|---|---|
| `src/clipper/core/style_loader.py` | Pure I/O module — `load_visual_identity(path)` + `VisualIdentityConfig` Pydantic model |
| `tests/test_style_node.py` | Unit + integration test suite |
| `estilo.json` (project root, optional) | Brand style file (not committed; see example below) |

---

## Modified Files

| File | Change |
|---|---|
| `src/clipper/core/orchestrator.py` | Add `visual_identity: dict` to `VideoState`; add `style_node`; wire DAG edge `fatiamento → style → transcricao`; add `"visual_identity": {}` to `initial_state` |
| `src/clipper/video/editor.py` | `cut_and_format_video` accepts `visual_identity: dict \| None = None`; helpers read style via `.get(key, CONFIG_DEFAULT)` |

---

## Usage

### Option A — Run with defaults (no style file)

```bash
# No estilo.json → pipeline uses all hardcoded CAPTION_* defaults
bash run_pipeline.sh
```

### Option B — Run with custom brand style

```bash
# Create estilo.json in project root
cat > estilo.json << 'EOF'
{
  "palette": {
    "caption_color": "#FF4500",
    "caption_stroke_color": "#000000"
  },
  "typography": {
    "caption_font_size": 90
  }
}
EOF

bash run_pipeline.sh
# pipeline.log will contain: INFO style_node loaded visual_identity: {caption_color: '#FF4500', ...}
```

### Option C — Verify style was applied

```bash
grep -E "style_node|visual_identity" output/pipeline.log
```

---

## `estilo.json` Reference

All fields are optional. Missing fields fall back to `config.py` defaults.

```json
{
  "palette": {
    "caption_color": "#25E600",
    "caption_stroke_color": "#000000"
  },
  "typography": {
    "caption_font_size": 80,
    "caption_stroke_width": 8,
    "caption_reference_width": 1080
  },
  "layout": {
    "caption_center_x_ratio": 0.5,
    "caption_center_y_ratio": 0.79,
    "caption_safe_width_ratio": 0.9
  },
  "motion": {
    "caption_max_words": 3,
    "caption_max_gap": 0.5,
    "caption_max_duration": 2.0
  }
}
```

---

## Running Tests

```bash
# All tests (including new style tests)
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"

# Only the new style node tests
PYTHONPATH=src venv/bin/python -m unittest tests/test_style_node.py -v
```

---

## DAG Topology (after this feature)

```
download → fatiamento → style → transcricao → pensador → extrator → preview → approval → editor
```

---

## Log Signals

| Scenario | Level | Message pattern |
|---|---|---|
| `estilo.json` found and loaded | INFO | `style_node loaded visual_identity: {caption_color: ...}` |
| `estilo.json` not found | WARNING | `style_node: estilo.json not found at {path}; using all defaults` |
| Individual field missing | WARNING | `style_node: field '{key}' missing from estilo.json; using default {default}` |
| Malformed hex color | WARNING | `style_node: field '{key}' has invalid hex color '{value}'; using default {default}` |

---

## Rollback

If this feature must be reverted:
1. Remove `visual_identity` from `VideoState` and `initial_state`
2. Remove `style_node` and its DAG edge from `create_graph()`
3. Delete `src/clipper/core/style_loader.py`
4. Revert `editor.py` — remove `visual_identity` parameter; restore direct `config.py` constant reads
5. Purge SQLite checkpoints (old checkpoints carry `visual_identity`; safe to ignore on rollback)
