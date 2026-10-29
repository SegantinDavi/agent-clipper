# Developer Quickstart: Checkpoint Thread ID Hardening

**Feature Branch**: `011-checkpoint-thread-id-hardening`  
**Date**: 2026-10-28  
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

This quickstart guides developers through testing and validating the deterministic context isolation and thread ID derivation for LangGraph SQLite checkpoints.

---

## 1. Running Unit Tests

Execute the unit tests covering deterministic hashing, provider isolation, pause configuration sensitivity, and safe default fallbacks:

```bash
# Run the dedicated checkpoint thread ID test suite:
PYTHONPATH=src venv/bin/python -m unittest tests/test_checkpoint_thread_id.py

# Run all test suites across the project:
PYTHONPATH=src venv/bin/python -m unittest discover tests/ -p "test_*.py"
```

---

## 2. Interactive Testing in Python REPL

You can directly inspect and verify thread derivation behavior in a Python session:

```python
from clipper.core.orchestrator import checkpoint_thread_id

# 1. Generate baseline thread ID
t1 = checkpoint_thread_id("dQw4w9WgXcQ", "gemini", "gemini-3.6-flash", "https://generativelanguage.googleapis.com/v1beta/openai/", True, 0.6)
print(f"Thread 1 (Gemini): {t1} (length: {len(t1)})")
# Expected: 16-character hex string, e.g. 'a1b2c3d4e5f67890'

# 2. Verify determinism (idempotency)
t2 = checkpoint_thread_id("dQw4w9WgXcQ", "gemini", "gemini-3.6-flash", "https://generativelanguage.googleapis.com/v1beta/openai/", True, 0.6)
assert t1 == t2, "Thread IDs must be strictly identical for same inputs"

# 3. Verify provider & endpoint isolation
t_ollama = checkpoint_thread_id("dQw4w9WgXcQ", "ollama", "qwen2.5:14b", "http://localhost:11434/v1", True, 0.6)
print(f"Thread 2 (Ollama): {t_ollama}")
assert t1 != t_ollama, "Switching provider must produce different thread ID"

t_endpoint_diff = checkpoint_thread_id("dQw4w9WgXcQ", "gemini", "gemini-3.6-flash", "https://proxy.example.com/v1", True, 0.6)
assert t1 != t_endpoint_diff, "Switching endpoint must produce different thread ID"

# 4. Verify silence configuration isolation
t_silence_off = checkpoint_thread_id("dQw4w9WgXcQ", "gemini", "gemini-3.6-flash", "https://generativelanguage.googleapis.com/v1beta/openai/", False, 0.6)
assert t1 != t_silence_off, "Toggling silence cut must produce different thread ID"

t_pause_diff = checkpoint_thread_id("dQw4w9WgXcQ", "gemini", "gemini-3.6-flash", "https://generativelanguage.googleapis.com/v1beta/openai/", True, 1.0)
assert t1 != t_pause_diff, "Modifying min pause must produce different thread ID"

# 5. Verify safe fallback on None
t_default = checkpoint_thread_id("dQw4w9WgXcQ")
print(f"Thread 3 (Defaults): {t_default}")
assert len(t_default) == 16, "Must generate valid 16-character hex hash with defaults"
```

---

## 3. End-to-End Pipeline Verification

When running the pipeline via CLI or Docker:

```bash
# Set environment variables
export YOUTUBE_URL="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
export LLM_PROVIDER="gemini"
export GEMINI_MODEL="gemini-3.6-flash"

# Run orchestrator
PYTHONPATH=src venv/bin/python -m clipper.core.orchestrator
```

Inspect `/app/output/pipeline.log` to confirm the generated thread ID:
```text
2026-10-28 20:55:00,123 - clipper.core.orchestrator - INFO - Calculated checkpoint thread_id: 4f8a3c2b1e0d9a7f (video_id: dQw4w9WgXcQ)
2026-10-28 20:55:00,124 - clipper.core.orchestrator - INFO - Graph compiled. Starting execution (Thread: 4f8a3c2b1e0d9a7f)...
```
