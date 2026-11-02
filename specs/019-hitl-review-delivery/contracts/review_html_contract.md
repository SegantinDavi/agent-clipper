# Contract: Review HTML Presentation & Responsiveness

**Feature**: 019-hitl-review-delivery  
**Contract ID**: CTR-019-01  
**Applies to**: `src/clipper/review/review.py` (`render_review_page`)  

---

## 1. Scene Presentation Requirements

### 1.1 Non-Empty Scenes
When a cut contains one or more `Scene` objects (`cut.scenes`), `render_review_page()` must render a container adhering to the following DOM structure:

```html
<div class="scenes">
  <h3 class="scenes-title">Cenas Planejadas ({count})</h3>
  <ol class="scenes-list">
    <li class="scene-item">
      <span class="scene-words">"{escaped_start_word} … {escaped_end_word}"</span> · 
      <span class="scene-metaphor">Metáfora: <em>{escaped_visual_metaphor}</em></span> · 
      <span class="scene-trigger">Gatilho: <code>{escaped_animation_trigger}</code></span>
    </li>
    <!-- additional scenes in order -->
  </ol>
</div>
```

### 1.2 Empty or Null Scenes Fallback (FR-004)
When a cut has no scenes (`not cut.scenes` or `cut.scenes is None`):

```html
<div class="scenes scenes-empty">
  <h3 class="scenes-title">Cenas Planejadas</h3>
  <p class="scenes-fallback">No scene script available</p>
</div>
```

The string `"No scene script available"` MUST be present in the output HTML.

### 1.3 Null or Empty Field Placeholders (FR-005)
For every `Scene` instance, fields that are `None`, empty string `""`, or whitespace-only MUST be rendered as the literal Unicode em-dash character `"—"` (U+2014):
- `start_word`: `"—"` if empty
- `end_word`: `"—"` if empty
- `visual_metaphor`: `"—"` if empty
- `animation_trigger`: `"—"` if empty

All non-empty text must be passed through `html.escape()` to prevent script or style injection. (Placeholders `"—"` are injected directly without double-escaping).

---

## 2. Viewport & Responsiveness Contract (FR-003, SC-005)

1. **Meta Viewport**: The HTML page must contain `<meta name="viewport" content="width=device-width, initial-scale=1">`.
2. **Horizontal Overflow Ceiling**:
   - `box-sizing: border-box` applied to all elements.
   - Body or main container width strictly capped at 100vw; no horizontal scrollbar at viewports between 320 px and 1920 px.
   - `.scenes`, `.scenes-list`, `.scene-item` must specify `word-break: break-word` and `overflow-wrap: anywhere` (or `break-word`).
3. **Mobile Adaptability**:
   - For viewports `<= 480px`, grid columns must collapse to `1fr` and padding must not exceed 12px horizontal margins, ensuring cards fit on a 320px screen.
