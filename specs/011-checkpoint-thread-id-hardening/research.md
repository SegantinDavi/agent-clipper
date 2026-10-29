# Research & Technical Decisions: Checkpoint Thread ID Hardening

**Feature**: `011-checkpoint-thread-id-hardening`  
**Date**: 2026-10-28  
**Status**: Completed  
**Spec**: [spec.md](spec.md)

---

## 1. Executive Summary

In LangGraph-based persistent architectures, the `thread_id` acts as the primary key identifying distinct workflow executions in the SQLite checkpointer (`/app/output/estado.db`). Previously, the `thread_id` was formed using a combination of `video_url`, `LLM_PROVIDER`, `MODEL_NAME`, `LLM_BASE_URL`, and serialized `PauseSettings`, prefixed with `"clipper_review_v3_"` and truncated to 24 characters.

This feature hardens the derivation of `thread_id` to prevent context collision when switching LLM providers (e.g. `ollama` vs `gemini`), models, endpoints (`LLM_BASE_URL`), or silence cutting configurations (`SILENCE_CUT_ENABLED`, `SILENCE_MIN_PAUSE`). By standardizing on a deterministic 16-character SHA-256 hexadecimal digest derived strictly from `[video_id] + [LLM_PROVIDER] + [MODEL_NAME] + [LLM_BASE_URL] + [SILENCE_CUT_ENABLED] + [SILENCE_MIN_PAUSE]` separated by `|`, the system guarantees:
1. Complete isolation between runs with different model providers, endpoints, or silence trimming parameters.
2. 100% deterministic idempotency across runs with identical parameters.
3. Clean logging and traceability without risking context bleed or schema mismatches in SQLite.
4. Documented invalidation of pre-existing checkpoints without accidental resumption of incompatible state.

---

## 2. Technical Decisions & Analysis

### Decision 1: Hash Algorithm, Truncation & Prefix Policy

- **Chosen Approach**: Pure SHA-256 hexadecimal digest truncated to 16 characters (`hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]`), without arbitrary version prefixes.
- **Rationale**:
  - A 16-character hexadecimal string provides $16^4 = 2^{64} \approx 1.84 \times 10^{19}$ possible states, virtually eliminating any risk of collision within a single user workspace or batch run.
  - Omission of arbitrary version prefixes (like `"clipper_review_v3_"`) ensures clean, compact thread IDs in CLI logs and SQLite query filters, satisfying FR-001.
  - Standard hex characters `[0-9a-f]` are safe across all filesystems, database collations, and URL encodings.
- **Alternatives Considered & Rejected**:
  - *Full 64-char SHA-256*: Excessive length adds noise to CLI logs (`logger.info`) without providing practical collision benefit over $2^{64}$ states.
  - *Prefixing `clip_<hash>`*: Adding custom prefixes adds string maintenance overhead and conflicts with FR-001 which mandates a 16-character hexadecimal hash.
  - *MD5 / SHA-1*: Cryptographically obsolete; SHA-256 is native in Python standard library (`hashlib`) and runs in <0.01ms.

---

### Decision 2: Canonical Payload Format & Field Delimiter

- **Chosen Approach**: Pipe-separated string format:
  ```text
  f"{clean_video_id}|{clean_provider}|{clean_model}|{clean_endpoint}|{clean_silence_enabled}|{clean_silence_min_pause}"
  ```
- **Rationale**:
  - The pipe delimiter (`|`) is distinct from characters found in YouTube IDs (`[0-9A-Za-z_-]{11}`), model names (e.g., `qwen2.5:14b`, `gemini-3.6-flash`), and floating point numbers (`0.6`).
  - Strict field ordering ensures canonical deterministic evaluation across different runs, operating systems, and Python minor versions.
  - Matches the exact specification mandated in FR-002: `[video_id] + [LLM_PROVIDER] + [MODEL_NAME] + [LLM_BASE_URL] + [SILENCE_CUT_ENABLED] + [SILENCE_MIN_PAUSE]` separated by `|`, honoring `AGENTS.md` Rule 7.
- **Alternatives Considered & Rejected**:
  - *Null byte delimiter (`\0`)*: Harder to debug and inspect in logs/prints if an intermediate payload needs to be logged or tested.
  - *JSON serialization (`model_dump_json()`)*: Key sorting differences or whitespace variances across JSON encoders can introduce non-deterministic hashes. A plain delimited string is simple, fast, and unambiguous.

---

### Decision 3: Parameter Normalization and Default Fallbacks

- **Chosen Approach**:
  - `video_id`: Raw string, trimmed of surrounding whitespace. Crucially, raw video IDs (e.g., YouTube 11-char IDs or explicit test video IDs like `"video-a"`) are preserved as-is without destructive normalization. If `video_id` is empty, fallback to `""`.
  - `llm_provider`: Lowercase string, trimmed. If `None` or empty, default to runtime configuration (`LLM_PROVIDER` or `"gemini"`).
  - `model_name`: String, trimmed. If `None` or empty, default to runtime configuration (`MODEL_NAME` or `""`).
  - `llm_base_url`: String, trimmed and trailing slashes stripped. If `None` or empty, default to runtime configuration (`LLM_BASE_URL` or `""`).
  - `silence_cut_enabled`: Canonical string `"true"` or `"false"`. If `None`, default to runtime configuration (`SILENCE_CUT_ENABLED` boolean). If passed as string/int/bool, converted via `str(bool(val)).lower()` or explicit boolean parsing (`val in {True, "1", "true", "yes"}`).
  - `silence_min_pause`: Canonical float string formatted as `str(float(val))` (e.g. `0.6` -> `"0.6"`, `1.0` -> `"1.0"`). If `None` or invalid, default to runtime configuration (`SILENCE_MIN_PAUSE` or `"0.6"`).
- **Rationale**:
  - Ensures robust handling of optional or `None` values (FR-004) while eliminating semantic ambiguities (e.g., `"True"` vs `True` vs `"1"` all evaluate to `"true"`).
  - Guarantees strict determinism (FR-003).
- **Alternatives Considered & Rejected**:
  - *Failing with `ValueError` on `None`*: Would break backward compatibility where callers invoked `checkpoint_thread_id(video_id)` expecting config defaults to be resolved automatically.

---

### Decision 4: Observability and Inline Safety Warnings

- **Chosen Approach**:
  - Include an explicit inline warning comment directly above the definition of `checkpoint_thread_id` in `src/clipper/core/orchestrator.py` stating that modifications to the identity calculation invalidate pre-existing SQLite checkpoints.
  - Log the derived `thread_id` at `INFO` level in `orchestrator.py` upon derivation, stating the identity parameters for clear traceability (FR-006).
- **Rationale**:
  - Fulfills FR-005 and FR-006.
  - Adheres strictly to `AGENTS.md` Rule 9 (Observability restricted to traditional file/stream logging, no heavy telemetry).

---

### Decision 5: Invalidation of Legacy Checkpoints

- **Chosen Approach**:
  - Acknowledge that the transition to the hardened 16-hex format naturally orphans old checkpoints (which used `"clipper_review_v3_" + hash[:24]`).
  - Do not implement database migration scripts or fallback lookups. Runs on previous videos will compute the new hardened `thread_id` and start fresh.
- **Rationale**:
  - Explicitly aligned with Assumption 4 and Success Criterion SC-005 in `spec.md`.
  - Migrating legacy checkpoints could restore invalid state created under incompatible providers, defeating the very purpose of this feature.
