# Feature Specification: Shorten confirmed pauses between speech

**Created**: 2026-10-25
**Status**: Authorized by the user's approval of the proposed conservative design.

This follows the Spec Kit specification workflow used by specs 004–007. The CLI
and project commands were unavailable in this environment at the previous check;
no CLI generation is claimed.

## User Scenarios & Testing

### User Story 1 - Shorten pauses naturally (P1)

Enable pause shortening by default, with environment-configurable minimum pause
0.6s, retained pause 0.2s, speech-edge protection 0.1s and noise threshold -35dB.
Only cut silence confirmed by FFmpeg inside gaps bounded by Whisper words. Merge
overlapping word intervals before finding gaps, protecting concurrent speech.
Keep uncertain audio, words, laughter above the threshold, clip edges and clips
without valid word timing/audio unchanged. Do not add a VAD/LLM or GPU workload.

### User Story 2 - Approve the resulting rhythm (P1)

During preview preparation, build a serializable per-cut plan of retained source
intervals. Store plans alongside cut metadata in review.json and include them in
review identity. Render previews using those intervals for both audio and video.
Display original and edited durations. After approval, use precisely the saved
plan, rather than detecting pauses again or relying on current settings.

### User Story 3 - Preserve timing and resumability (P1)

Final rendering applies speaker framing on the original continuous cut, then
concatenates retained intervals with MoviePy 1.0.3's chain method. Framing thus
continues to read source timestamps correctly. Map each caption word to its new
time, grouping captions separately within each retained interval so groups cannot
cross removed content. Keep audio/video cuts identical, even dimensions, H.264
settings and bounded resource lifetime. Save the applied pause plan next to each
MP4; .focus.json remains explicitly in original-cut time coordinates.

## Requirements

- FR-001: A lightweight pause_editing.py module owns validated settings, plans,
  FFmpeg detection, interval math, caption time mapping and preview filter assembly.
  Keep only plan URIs in graph state (reuse review_directory), never audio arrays.
  Preview video uses one select/setpts branch to avoid buffering full-resolution
  segments. Only audio uses trim/concat; output duration is explicitly capped to
  the saved plan to avoid AAC seek-padding extending an unchanged preview.
- FR-002: Add SILENCE_CUT_ENABLED, SILENCE_MIN_PAUSE, SILENCE_KEEP_PAUSE,
  SILENCE_SPEECH_PADDING and SILENCE_THRESHOLD_DB to config/.env.example. Validate
  finite, meaningful ranges before processing. Menu offers on/off; CLI supports
  --silence-cuts / --no-silence-cuts. Preserve selections over CUDA re-execution.
- FR-003: Scope new checkpoints to pause settings as well as LLM identity, so an
  existing approval cannot silently authorize a new editing policy. Existing
  checkpoint files remain intact but the new version uses a separate namespace.
- FR-004: Disabled mode skips detection and keeps original timing. No fallback on
  FFmpeg errors; missing words/audio explicitly produce an unchanged plan and log.
  Write local logs with original/edited duration, seconds removed and edit count.
- FR-005: Final renderer checks that each persisted plan matches its source cut.
  Missing plans on the new reviewed pipeline must fail rather than modify approved
  pacing. Direct editor callers retain identity timing when no plan is provided.
- FR-006: Preserve providers, CPU/GPU profile rules, LLM extraction, approval gate,
  speaker-focus rules and source media. Update README and AGENTS.md.

## Success Criteria

- Test pauses near thresholds, retained padding, overlapping words, multiple gaps,
  absent/invalid timestamps, trailing silences and settings validation.
- Test remapping of words/framing and identical plan use after SQLite resumption.
- Generate synthetic video with known words/tone regions and silent gaps; use real
  FFmpeg and MoviePy to verify preview/final durations, audio/video sync, captions
  and retained frame positions. Verify disabled/no-audio paths and preview identity.
- Run runtime-menu, LLM, transcription, approval, editor, speaker-focus and CUDA
  bootstrap regressions without paid API calls; inspect a rendered contact sheet.

## Sources

- https://ffmpeg.org/ffmpeg-filters.html#silencedetect
- https://ffmpeg.org/ffmpeg-filters.html#concat

## Validation

- PASS: 65 tests in the existing WSL venv, including all new pause tests and
  runtime selection, both mocked LLMs, transcription cleanup, CUDA bootstrap,
  SQLite approval resumption, caption rendering and speaker-focus regressions.
- PASS: real FFmpeg detection and preview encoding, plus MoviePy final export of
  synthetic media. A 1.5s pause becomes 0.2s; seven successive edits reduce a
  12s clip to 6.4s while preserving audible words throughout preview/final output.
- PASS: protected overlapping/quiet words, edge retention, invalid/out-of-cut word
  timestamps, settings validation, source-plan validation, disabled/no-audio paths,
  detection failure propagation and two exports sharing one source reader.
- PASS: source focus plan is sampled correctly after edits; second-speaker crop
  and remapped captions appear at their compressed output times. Reviewed plans
  are passed through approval unchanged, without a second silence detection.
- PASS: generated preview/final on 30s of cached podcast video and its existing
  transcript, with actual CPU face/speaker inference. This particular sample has
  no eligible confirmed silence under conservative defaults, so it remains 30s.
  Inspected contact_sheet.png for framing, captions and source/output agreement.
- Artifacts: output/pause_validation/{source.mp4,Pause_validation.mp4,
  Pause_validation.pauses.json,Pause_validation.focus.json,contact_sheet.png,tests.log}
  and its reviews directory. Existing source files were not modified.
- PASS: source parsing and diff whitespace checks. No new runtime dependency,
  download, GPU inference workload or paid API call was introduced for this feature.
- Docker was not built or executed. Existing MoviePy/NumPy deprecation warnings
  appear during passing tests; no runtime package versions were changed.
