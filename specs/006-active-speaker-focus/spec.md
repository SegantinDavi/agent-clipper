# Feature Specification: Close framing of the active speaker

**Created**: 2026-10-25
**Status**: Implementation authorized by the user's active-speaker framing request.
**Input**: Keep approved cuts close on the person speaking rather than on the frame center.

Uses the official Spec Kit specification template workflow, as specifications
004 and 005. The Spec Kit CLI is unavailable; no CLI execution is claimed.

## User Scenarios & Testing

### User Story 1 - Follow a visible speaker (Priority: P1)

Detect visible faces with OpenCV YuNet. Match faces across consecutive frames and
rank their synchronized audio/video using the pretrained Light-ASD model, exported
to ONNX. Run both visual models on CPU, sequentially, only for approved cuts.
Do not infer the active speaker from face size alone or introduce another LLM.

### User Story 2 - Keep close framing comfortable (Priority: P1)

Maintain a 9:16 output with even dimensions, a configurable head-and-shoulders
crop and stable output size. Per the user's follow-up, lock position and zoom
throughout each continuous speaker turn within a source shot. Use all detected
face bounds in that turn to choose a single fixed composition. Do not pan,
interpolate, zoom or recenter in response to head/body motion. Require a short
confirmation before changing speaker, and reset on source camera cuts.
If no face is visible or speech is offscreen, retain the last reliable crop,
using a centered fallback when there is no prior framing. Log the fallback;
never promise visibility of a person absent from the source image.

### User Story 3 - Preserve the existing pipeline (Priority: P1)

Do not change transcription, LLMs, cut selection, approval, captions or timing.
Keep output audio and the existing H.264 parameters. Analyze each approved cut
before rendering it; no frames, model objects or face arrays enter VideoState.

## Requirements

- FR-001: Add a default-enabled, environment-configurable speaker-focus module.
  Face detection, ONNX inference and fixed-turn composition are deterministic local
  processing. Use serializable bounded framing timelines saved under output.
- FR-002: Use a small pretrained YuNet detector and Light-ASD audio/video network.
  Preserve upstream licenses, model provenance and checksums. Model preparation is
  a separate reproducible tool; production inference never downloads code/models.
- FR-003: Use ONNX Runtime CPUExecutionProvider and a bounded thread count. PyTorch
  is allowed only in an isolated export environment, not as a runtime dependency,
  avoiding changes to the pinned NVIDIA runtime used by Whisper.
- FR-004: Decode approved cut frames at 25fps; detect faces every 5 frames at a
  reduced resolution. Process at most 4 seconds of face patches per inference
  window, limiting face candidates. Retain only small patches and numeric tracks,
  never whole-video RGB frames. Extract mono 16kHz PCM only for the current cut.
- FR-005: Follow upstream Light-ASD preprocessing: 13 MFCC coefficients per 10ms,
  central 112x112 grayscale face patches at 25fps, trained AV classifier scores.
  Keep scores synchronized and use confidence/hold hysteresis for speaker changes.
- FR-006: Apply the framing transformation before captions. Use Pillow/OpenCV for
  resizing rather than MoviePy's old Pillow ANTIALIAS fallback. Keep clips/readers
  and ONNX sessions bounded to a cut and close all resources on success/failure.
- FR-007: Missing enabled focus dependencies/models fail with setup instructions;
  explicitly disabling focus preserves the original centered crop. Include the
  models in Docker without requiring internet during inference.
- FR-008: Document that learned active-speaker selection is probabilistic; overlapping
  speech, occlusions, offscreen voices and reaction shots can remain ambiguous.
- FR-009: Temporary missed detections retain the selected speaker and fixed crop.
  A speaker change or source camera cut applies the new fixed composition as a
  direct cut, with no animated transition. Framing cannot compensate arbitrary
  offscreen movement while also remaining static.

## Success Criteria

- Test geometric bounds, portrait/landscape dimensions, face association, camera
  cuts, speaker switching, silence/fallback and caption/audio preservation.
- Verify exported ONNX scores against the source model on two sequence lengths.
- Run real face and active-speaker inference on an existing local podcast sample,
  render a short MP4 and inspect frames showing the chosen close framing.
- Run existing editor, approval and mocked-LLM regression checks without API calls.

## Sources

- https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
- https://github.com/Junhua-Liao/Light-ASD (CVPR 2023; MIT)
- https://github.com/Junhua-Liao/Light-ASD/blob/main/Columbia_test.py

## Validation

- PASS: 31 speaker-focus, caption, approval, mocked-LLM, transcription and real
  CUDA runtime regression tests in the WSL venv.
- PASS: exported ONNX and unmodified PyTorch network agree for 25- and 50-frame
  sequences; maximum absolute errors 1.91e-6 and 2.39e-6. The export tool adapts
  the source audio encoder's unbatched 3D pooling to equivalent 2D ONNX pooling.
- PASS: actual face detection and audiovisual inference on 12 seconds of a
  previously approved local podcast cut. 300 frames, 5 short face tracks; analysis
  completed in approximately 3.2 seconds with two CPU threads in this environment.
  32% of frames were marked uncertain/offscreen and used the documented fallback.
- PASS: MP4 duration, audio and captions preserved; inspected four comparison
  frames at 1, 4, 8 and 11 seconds. Corrected smoothing lag and stale face
  candidates at source-camera changes; regression coverage added.
- Artifacts: output/speaker_focus_validation/speaker_focus_preview.mp4,
  contact_sheet.png and speaker_focus_preview.focus.json.
- PASS: source parsing, diff whitespace checks and runtime dependency inspection.
  PyTorch is absent from the production venv; NVIDIA package versions remain
  unchanged. New runtime packages support Python 3.12 or newer.
- Docker was not built or executed. Assets and runtime dependencies are included
  by its existing copy/install steps; WSL validation does not imply container testing.
- Static-framing amendment: 27 speaker-focus, caption, review and mocked-LLM tests
  passed. Re-rendered the 12-second sample and asserted all 300 timeline samples
  retain exactly the same rectangle until a speaker/shot reset, including temporary
  face loss. Inspected the regenerated comparison sheet. Position and zoom are
  locked; no interpolation or motion-following correction remains in the camera plan.
