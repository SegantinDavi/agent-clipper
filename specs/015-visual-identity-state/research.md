# Research: Visual Identity & Global State (015)

**Branch**: `015-visual-identity-state` | **Date**: 2026-10-31

---

## 1. How should `estilo.json` be parsed and validated?

**Decision**: Use a Pydantic `BaseModel` (`VisualIdentityConfig`) with all fields optional and explicit defaults.

**Rationale**: The spec mandates per-field fallback with WARNING logging for each missing key (FR-003). Pydantic's `model_validate` with `model_config = ConfigDict(extra="ignore")` silently ignores unrecognized keys (edge-case requirement) and raises `ValidationError` only on type-level failures. Custom `field_validator` on hex color fields lets us detect malformed colors like `#ZZZZZZ` and substitute defaults with a WARNING — without crashing (edge-case requirement).

**Alternatives considered**:
- `json.loads` + manual dict merge: Rejected — no type validation, no per-field defaulting without boilerplate, violates the "no manual dict scraping" spirit of AGENTS.md Rule 5.
- `jsonschema` library: Rejected — extra dependency, no Python-object output, no per-field default injection.

---

## 2. Where does `estilo.json` live and how is the path resolved?

**Decision**: The file is resolved at pipeline startup relative to `PROJECT_ROOT` (defined in `config.py` as `Path(__file__).resolve().parents[3]`). The loader receives the path as a parameter to stay testable without monkeypatching `os`.

**Rationale**: The spec says "project root directory" (FR-001). `config.py` already defines `PROJECT_ROOT` for other modules. Injecting the path as a parameter enables pure unit testing without touching the filesystem globals.

**Alternatives considered**:
- Hardcoded absolute path: Rejected — makes tests fragile and violates 12-factor config philosophy.
- Reading from an env var: Rejected — the spec treats `estilo.json` as a convention file, not a configurable path.

---

## 3. What fields does the initial `estilo.json` schema contain?

**Decision**: The schema maps 1-to-1 with the current `CAPTION_*` constants in `config.py` — exactly the keys that downstream `editor.py` reads. The Pydantic model default for each field matches the `config.py` default, ensuring zero behavioral change when `estilo.json` is absent.

| `estilo.json` key | Pydantic field | `config.py` fallback |
|---|---|---|
| `palette.caption_color` | `caption_color: str = "#25E600"` | `CAPTION_COLOR` |
| `palette.caption_stroke_color` | `caption_stroke_color: str = "#000000"` | `CAPTION_STROKE_COLOR` |
| `typography.caption_font_size` | `caption_font_size: int = 80` | `CAPTION_FONT_SIZE` |
| `typography.caption_stroke_width` | `caption_stroke_width: int = 8` | `CAPTION_STROKE_WIDTH` |
| `typography.caption_reference_width` | `caption_reference_width: int = 1080` | `CAPTION_REFERENCE_WIDTH` |
| `layout.caption_center_x_ratio` | `caption_center_x_ratio: float = 0.5` | `CAPTION_CENTER_X_RATIO` |
| `layout.caption_center_y_ratio` | `caption_center_y_ratio: float = 0.79` | `CAPTION_CENTER_Y_RATIO` |
| `layout.caption_safe_width_ratio` | `caption_safe_width_ratio: float = 0.9` | `CAPTION_SAFE_WIDTH_RATIO` |
| `motion.caption_max_words` | `caption_max_words: int = 3` | `CAPTION_MAX_WORDS` |
| `motion.caption_max_gap` | `caption_max_gap: float = 0.5` | `CAPTION_MAX_GAP` |
| `motion.caption_max_duration` | `caption_max_duration: float = 2.0` | `CAPTION_MAX_DURATION` |

**Rationale**: Limits scope to keys currently consumed by `editor.py` (FR-010). Does not remove `CAPTION_*` from `config.py` (these remain as ultimate fallback). The spec explicitly states `estilo.json` is a "project-defined schema" and "at minimum" must include the caption keys.

**Nested vs. flat structure**: `estilo.json` uses a nested layout (`palette`, `typography`, `layout`, `motion`) for human readability. After Pydantic validation, the model is exported as a **flat dict** for `VideoState.visual_identity` (all primitives, no nested objects), satisfying FR-005 (SQLite-serializable).

---

## 4. How does `editor.py` consume `visual_identity` without breaking the node signature?

**Decision**: `cut_and_format_video` receives a new optional `visual_identity: dict | None = None` parameter. Helper functions (`create_caption_clip`, `group_caption_words`, etc.) read from this dict with `.get(key, CONFIG_FALLBACK)`. The default `None` means no behavioral change when the parameter is absent.

**Rationale**: `cut_and_format_video` is called from `editor_node` in `orchestrator.py`, which has access to `VideoState.visual_identity`. Adding a keyword argument with a default preserves backward compatibility with existing tests.

**Alternatives considered**:
- Module-level global override: Rejected — would cause cross-test contamination and is not thread-safe.
- Passing the full `VideoState` to `editor.py`: Rejected — breaks separation of concerns and makes the video module depend on the orchestrator's state type.

---

## 5. How is `visual_identity` checkpointed and restored?

**Decision**: No special handling needed. `SqliteSaver` serializes all `VideoState` values as JSON. A `dict[str, str | int | float | bool]` is natively JSON-serializable. When the pipeline resumes after a crash, LangGraph restores the entire state dict including `visual_identity` — `style_node` is not re-executed (the checkpoint already contains its output).

**Rationale**: SC-003 requires byte-for-byte identity after checkpoint round-trip. Since all values are Python primitives, JSON round-trip is lossless for strings, ints, and floats within normal precision. The spec confirms `visual_identity` contains "only serializable primitive values."

**Alternatives considered**:
- Custom serializer/deserializer: Rejected — unnecessary; primitives already satisfy `SqliteSaver` requirements.

---

## 6. Where does `style_node` sit in the DAG?

**Decision**: `style_node` is inserted **between `fatiamento_node` and `transcription_node`** (i.e., after chunking and before any LLM/CPU-intensive work).

**Rationale**: The spec (Assumption section) states "positioned in the DAG after `fatiamento_node` and before `thinker_node`." Placing it before `transcription_node` also means transcription happens with the final state in place, making the checkpoint after `style_node` complete. Since `style_node` is pure I/O (< 100ms), it does not delay the expensive path meaningfully.

**DAG after this feature**:
```
download → fatiamento → style → transcricao → pensador → extrator → preview → approval → editor
```

---

## 7. How are malformed hex colors validated?

**Decision**: A Pydantic `@field_validator` on `caption_color` and `caption_stroke_color` uses `re.fullmatch(r"#[0-9A-Fa-f]{6}", value)`. If it fails, the validator logs a WARNING and returns the field's default value instead of raising `ValidationError`.

**Rationale**: The spec edge case says "the field falls back to the hardcoded default for that specific key and a WARNING is logged" — the pipeline must NOT crash. Using a validator that returns the default on failure (instead of raising) achieves this. This is the one place where a `re` pattern is acceptable: it validates a precisely-defined format (`#RRGGBB`), not scraping LLM output.

**Note**: This is distinct from AGENTS.md Rule 5, which prohibits `re.search` to parse LLM responses. Color format validation is deterministic schema enforcement.
