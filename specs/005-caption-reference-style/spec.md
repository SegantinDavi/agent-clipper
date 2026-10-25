# Feature Specification: Podcast captions matching the visual reference

**Created**: 2026-10-25
**Status**: Authorized by the user's caption request and position clarification.
**Input**: Match the supplied green, bold, black-outline podcast caption reference.

Uses the official Spec Kit specification template workflow, as in specification
004. The Spec Kit CLI is not installed; no CLI execution is claimed.

## User Scenarios & Testing

### User Story 1 - Read short phrases over the video (Priority: P1)

Render bright green Liberation Sans Bold text with a thick black outline and a
transparent background. Group up to three consecutive timestamped words instead
of showing isolated words, matching the reference's short phrase treatment.

### User Story 2 - Match the reference position (Priority: P1)

The user explicitly selected the reference image position after being informed
that literal MoviePy coordinates (0, -1075) would place text offscreen. Center the
caption horizontally and place its center at 79% of the output frame height.
Scale typography and outline with frame width; fit long text within a 90% safe
width without stretching glyphs or moving the caption center outside the frame.

Acceptance scenarios:
1. Rendered text has green fill, black outline and transparent surrounding pixels.
2. A three-word phrase appears together for its timed interval at the chosen position.
3. A pause over 0.5s, sentence ending, 3-word count or 2-second duration starts a
   new phrase. Show phrases from the first word's start to the last word's end.
4. Clip boundaries trim overlapping word intervals; captions never extend beyond
   the cut, and words crossing the start boundary are not silently lost.
5. Small and full-HD frames retain visible, centered captions and even dimensions.

## Requirements

- Keep MoviePy 1.0.3, Pillow rendering, Liberation fonts, the existing crop and
  H.264 export settings. Do not add ImageMagick policy changes or dependencies.
- Read caption color, font size, outline width, center ratios, safe width and
  phrase limits from environment-backed config values.
- Keep word timestamps out of LLM prompts; grouping is deterministic in the editor.
- Preserve case, accents and punctuation; join timestamped words with spaces.
- Process captions only inside approved cuts and release render resources per cut.
- Add targeted grouping, pixel-placement and actual MP4 export tests. Generate
  and visually inspect a PNG preview from available local video, without API calls.

## Success Criteria

- Unit and actual export tests pass with the revised green caption style.
- A preview verifies readable green text with a dark outline, centered near the
  lower portion of the frame, matching the supplied reference's placement.
- No transcript, provider configuration or cut-selection behavior is changed.

## Validation

- PASS: 5 caption tests covering fill/outline/transparency, safe-width fitting,
  position at small and full-HD resolutions, phrase boundaries and an actual MP4.
- PASS: 7 existing mocked-LLM regression tests and Python source parsing.
- PASS: git diff whitespace check.
- Generated and visually inspected output/caption_style_preview.png (1080x1920)
  using a frame from a local downloaded podcast. The sample phrase is centered
  at approximately y=1517, with green fill, bold Liberation font and black outline.
- The preview uses Pillow for still-image scaling: MoviePy 1.0.3's optional resize
  fallback references Image.ANTIALIAS, absent in the installed Pillow. The video
  pipeline retains its existing crop and does not invoke that resize fallback.
