# Data Model: Visual Identity & Global State (015)

**Branch**: `015-visual-identity-state` | **Date**: 2026-10-31

---

## Entities

### 1. `VisualIdentityConfig` (Pydantic BaseModel)

**Location**: `src/clipper/core/style_loader.py`  
**Purpose**: Validates and normalizes `estilo.json` content with per-field defaults and hex color guards.

```python
from pydantic import BaseModel, ConfigDict, field_validator
import re, logging

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

class VisualIdentityConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # palette
    caption_color: str = "#25E600"
    caption_stroke_color: str = "#000000"

    # typography
    caption_font_size: int = 80
    caption_stroke_width: int = 8
    caption_reference_width: int = 1080

    # layout
    caption_center_x_ratio: float = 0.5
    caption_center_y_ratio: float = 0.79
    caption_safe_width_ratio: float = 0.9

    # motion
    caption_max_words: int = 3
    caption_max_gap: float = 0.5
    caption_max_duration: float = 2.0
```

| Field | Type | Default | Source constant |
|---|---|---|---|
| `caption_color` | `str` (hex) | `"#25E600"` | `CAPTION_COLOR` |
| `caption_stroke_color` | `str` (hex) | `"#000000"` | `CAPTION_STROKE_COLOR` |
| `caption_font_size` | `int` | `80` | `CAPTION_FONT_SIZE` |
| `caption_stroke_width` | `int` | `8` | `CAPTION_STROKE_WIDTH` |
| `caption_reference_width` | `int` | `1080` | `CAPTION_REFERENCE_WIDTH` |
| `caption_center_x_ratio` | `float` | `0.5` | `CAPTION_CENTER_X_RATIO` |
| `caption_center_y_ratio` | `float` | `0.79` | `CAPTION_CENTER_Y_RATIO` |
| `caption_safe_width_ratio` | `float` | `0.9` | `CAPTION_SAFE_WIDTH_RATIO` |
| `caption_max_words` | `int` | `3` | `CAPTION_MAX_WORDS` |
| `caption_max_gap` | `float` | `0.5` | `CAPTION_MAX_GAP` |
| `caption_max_duration` | `float` | `2.0` | `CAPTION_MAX_DURATION` |

**Validation Rules**:
- `caption_color` and `caption_stroke_color`: must match `#RRGGBB` (6-digit hex). On failure → log WARNING + return field default.
- `caption_font_size`, `caption_stroke_width`, `caption_reference_width`, `caption_max_words`, `caption_max_gap`, `caption_max_duration`: must be `> 0`. On non-positive or malformed numeric input → log WARNING + return field default.
- Invalid JSON syntax / non-dict JSON structure: caught gracefully → log WARNING + return full default dictionary.
- `extra="ignore"`: unrecognized keys are silently discarded.

---

### 2. `VideoState` (TypedDict) — extended field

**Location**: `src/clipper/core/orchestrator.py`  
**Change**: Add `visual_identity: dict` field.

```python
class VideoState(TypedDict):
    # ... existing fields ...
    visual_identity: dict   # NEW: populated by style_node; normalized 11 fields
```

**Serialization**: `dict[str, str | int | float | bool]` — natively JSON-serializable by `SqliteSaver`. No custom encoder/decoder needed.

**Initial value** in `main()`:
```python
"visual_identity": {}
```

---

### 3. `estilo.json` file schema

**Location**: `{PROJECT_ROOT}/estilo.json` (optional file; absence is not an error)

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

**Flattening rule**: The loader flattens nested categories into a single-level dict before storing in `VideoState.visual_identity`:

```python
# Result after flattening:
{
  "caption_color": "#25E600",
  "caption_stroke_color": "#000000",
  "caption_font_size": 80,
  # ...
}
```

---

## State Transitions

```
[pipeline start]
       │
       ▼
VideoState.visual_identity = {}     ← initial state
       │
       ▼
style_node executes
  ├─ estilo.json FOUND → validate → flatten → visual_identity = {all 11 fields}
  └─ estilo.json ABSENT/INVALID → log WARNING → visual_identity = {all 11 default fields}
       │
       ▼
SQLite checkpoint written           ← visual_identity is part of checkpoint
       │
       ▼
[crash recovery: visual_identity restored from checkpoint; style_node skipped]
       │
       ▼
editor_node reads visual_identity.get("caption_color", CAPTION_COLOR)
```

---

## Relationships

- `style_loader.load_visual_identity(path)` → returns `dict` (flattened primitives)
- `style_node(state)` → calls `style_loader.load_visual_identity` → returns `{"visual_identity": {...}}`
- `editor_node(state)` → passes `state.get("visual_identity", {})` to `cut_and_format_video`
- `cut_and_format_video(... visual_identity=None)` → reads style with `.get(key, CONFIG_DEFAULT)`
