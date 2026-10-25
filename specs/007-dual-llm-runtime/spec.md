# Feature Specification: Local and paid API runtime profiles

**Created**: 2026-10-25
**Status**: Implementation authorized by the user's dual-backend and terminal-menu request.
**Input**: Restore local inference from commit 3661fd5 while retaining Gemini.

Uses the Spec Kit specification workflow and sections, following specs 004–006.
Neither the Spec Kit CLI nor its project commands are installed in this checkout
or its WSL environment; this document does not claim CLI generation.

## User Scenarios & Testing

### User Story 1 - Choose a runtime before processing (Priority: P1)

An interactive invocation of orchestrator.py or run_pipeline.sh shows a basic
terminal menu for Gemini or local Ollama, then model and video URL. Enter accepts
the displayed defaults. Missing Gemini credentials can be entered without echo.
Selection happens before importing config, CUDA or inference libraries. CUDA
loader re-execution preserves selection without prompting a second time.

### User Story 2 - Respect the hardware profile (Priority: P1)

Local uses one Qwen2.5:14b model through Ollama's OpenAI-compatible endpoint,
Whisper CPU/int8, and no Gemini credentials or CUDA validation. Gemini uses the
configured paid API model and Whisper CUDA/float16 with existing preflight checks.
Legacy WHISPER_DEVICE/WHISPER_COMPUTE_TYPE exports cannot override these profiles.
Failures never switch provider or hardware automatically.

### User Story 3 - Run unattended and resume safely (Priority: P1)

--provider ollama|gemini, --model, --url and --non-interactive support automation.
Without a TTY, use environment configuration without input. Load optional .env
without overriding exported variables. Secrets remain in environment/.env, never
tracked code, prompts, checkpoints or logs. Preserve existing user credentials
and model selection by migrating the current code customization into ignored .env.
Checkpoint identity includes video, provider, model and endpoint; switching profile
cannot reuse another profile's reasoning, cuts or approvals. Existing unscoped
checkpoints remain on disk but are not resumed by the new version.

## Requirements

- FR-001: Centralize provider, endpoint, model, API key and transcription profile
  in config; default unattended provider remains Gemini for compatibility.
- FR-002: Both thinker and extractor use the selected single model and endpoint.
  Retain Instructor/Pydantic JSON Schema constrained decoding for both providers,
  client cleanup, output token limits, current prompts and few-shot examples.
- FR-003: Preserve the LangGraph DAG, SQLite durability, review, rendering,
  segment-only LLM timestamps and finally-based Whisper cleanup after each chunk.
- FR-004: Keep local defaults at http://localhost:11434/v1 and qwen2.5:14b;
  allow OLLAMA_BASE_URL for Docker networking. No new LLM or telemetry service.
- FR-005: Update AGENTS.md, README and .env.example with the hardware matrix,
  interactive/unattended usage, credentials, Docker networking and checkpoint scope.

## Success Criteria

- Mock both endpoints through thinker/extractor and verify schema and model.
- Verify missing credentials only block Gemini, and CPU local ignores CUDA exports.
- Test menu defaults, invalid input, cancellation, non-TTY, CLI overrides and
  re-execution without repeated prompts. Help works without CUDA initialization.
- Test checkpoint isolation; run transcription, CUDA bootstrap, approval and editor
  regressions without paid API calls. Record environment limitations honestly.

## Sources

- https://github.com/github/spec-kit
- https://ollama.com/blog/structured-outputs

## Validation

- PASS: 47 tests covering terminal selection, cancellation, noninteractive CLI,
  provider validation, enforced CPU/GPU profiles, checkpoint isolation, mocked
  Gemini/Ollama JSON Schema extraction, transcription cleanup, CUDA bootstrap,
  review, captions, rendering and speaker focus in the existing WSL venv.
- PASS: 2 real CUDA smoke tests through run_pipeline.sh, including cached Whisper
  small transcription on GPU and direct orchestrator --help invocation.
- PASS: real cached Whisper small transcription on CPU/int8 with LLM_PROVIDER=ollama,
  empty Gemini credentials and deliberately conflicting legacy CUDA exports.
- PASS: python-dotenv installed in the existing WSL venv; previous uncommitted
  model/key customization preserved in ignored .env, without tracked credentials.
- Ollama's localhost endpoint was unavailable from this WSL environment. Both
  LLM protocols were tested using httpx mock transports; no live Ollama generation,
  paid Gemini request or full YouTube pipeline was performed.
- Docker image was not built or run. Existing MoviePy/NumPy deprecation warnings
  appeared during passing regression tests.
