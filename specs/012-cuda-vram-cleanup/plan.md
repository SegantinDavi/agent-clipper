# Implementation Plan: Deep CUDA VRAM Cleanup in Gemini Profile

**Branch**: `012-cuda-vram-cleanup` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/012-cuda-vram-cleanup/spec.md`

---

## Summary

This feature eliminates CUDA Out-Of-Memory (OOM) risks during multi-chunk transcription in the Gemini API profile (`LLM_PROVIDER=gemini`) by implementing deep and deterministic VRAM cleanup between consecutive audio chunks.

The solution ensures that:
- In the Gemini profile (`WHISPER_DEVICE=cuda`), every chunk transcription in `src/clipper/core/ingestion.py` executes a structured cleanup sequence in its `finally` block: baseline VRAM sampling (`get_gpu_memory_info()`), safe generator closure (`segments.close()`), CTranslate2 model unloading (`ct2_model.unload_model()`), Python garbage collection (`del model; gc.collect()`), and deep CUDA cache eviction via `release_cuda_memory(before_mb=before_mb)` in `src/clipper/runtime/cuda_runtime.py` (flushing `torch.cuda.empty_cache()` if PyTorch is present).
- In the Ollama profile (`LLM_PROVIDER=ollama`, `WHISPER_DEVICE=cpu`), zero CUDA libraries, drivers, or cleanup calls are executed, maintaining complete CPU isolation.
- Fast, non-invasive VRAM observability is achieved via native NVML (`libnvidia-ml.so.1`) through `ctypes`, writing structured `INFO` confirmation logs (`"GPU memory flushed successfully: before=%.1f MB, after=%.1f MB (freed=%.1f MB)"` or `"GPU memory flushed successfully."` fallback) directly to `pipeline.log` without introducing external telemetry or CLI subshell latency.
- Failures in the cleanup routine are caught and logged at `WARNING` level without propagating exceptions or halting the pipeline.

---

## Technical Context

**Language/Version**: Python 3.12+ (tested on Python 3.12 - 3.14)  
**Primary Dependencies**: `ctranslate2==4.8.3`, `faster-whisper==1.2.1`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` (from `requirements-cuda.txt`), `torch` (optional fallback if present)  
**Storage**: File logging in `/app/output/pipeline.log`  
**Testing**: Python `unittest` suite (new `tests/test_cuda_cleanup.py` + updates to `tests/test_transcription.py`)  
**Target Platform**: Linux WSL2 / Docker (Debian-slim), 8GB RAM, 8GB Swap, NVIDIA GeForce RTX 3060 (12GB VRAM)  
**Project Type**: Single project / Python domain package under `src/`  
**Performance Goals**:
- Cleanup execution time <5ms per chunk.
- VRAM usage between chunks does not grow monotonically across 10+ chunks (0% cumulative leak).
- NVML memory query latency <0.1ms via direct `ctypes` bindings.  
**Constraints**:
- Strict compliance with `AGENTS.md` Rule 1 (preserve memory release between chunks, no silent fallbacks, Ollama CPU profile isolation).
- Strict compliance with `AGENTS.md` Rule 9 (no external telemetry like Langfuse or Arize Phoenix; logging to `pipeline.log` only).
- No new heavy dependencies introduced into `requirements.txt` or `requirements-cuda.txt` (FR-006).
- English naming, clean code, comments documenting the "why" only.  
**Scale/Scope**:
- `src/clipper/runtime/cuda_runtime.py`: Add `get_gpu_memory_info()` and `release_cuda_memory()`.
- `src/clipper/core/ingestion.py`: Harden `transcribe_audio_chunk()` `finally` block to close generator, unload CTranslate2 model, and invoke `release_cuda_memory()` when `WHISPER_DEVICE == "cuda"`.
- `tests/test_cuda_cleanup.py`: New comprehensive test suite covering normal execution, error handling, generator leaks, and Ollama profile isolation.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Regra Arquitetural (AGENTS.md) | Status | Avaliação / Justificativa |
|---|---|---|
| **1. Gerenciamento de Memória (WSL 8GB / RTX 3060 12GB)** | **PASS** | Cumpre diretamente o mandato da Regra 1: "Preserve a liberação de memória entre chunks". Libera VRAM em GPU CUDA/float16 no perfil Gemini e mantém CPU/int8 no perfil Ollama. |
| **2. Ingestão & Fatiamento Preventivo** | **PASS** | O fatiamento via FFmpeg em `node_0.py` permanece inalterado; o cleanup opera individualmente após cada chunk fatiado. |
| **3. Orquestração Obrigatória (LangGraph)** | **PASS** | Mantém a estrutura de grafo StateGraph e checkpointer SQLite intactos sem alterar a assinatura do estado. |
| **4. Cognitive Routing (Single-Model)** | **PASS** | Não afeta os nós Pensador e Extrator. |
| **5. Constrained Decoding (Sem Regex)** | **PASS** | Não afeta schemas Pydantic ou Instructor. |
| **6. Manipulação de Vídeo (MoviePy/ImageMagick)** | **PASS** | Inalterado. |
| **7. Containerização e Variáveis** | **PASS** | Compatível com o Dockerfile e variáveis de ambiente existentes (`LLM_PROVIDER`, `WHISPER_DEVICE`). Sem novas dependências pesadas. |
| **8. Padrões de Código (Clean Code & English)** | **PASS** | Nomenclatura 100% em inglês com comentários explicativos restritos ao "porquê". |
| **9. SDD e Observabilidade Restrita** | **PASS** | Especificação SDD gerada e aprovada. Observabilidade restrita a logs tradicionais em `pipeline.log`, sem Langfuse ou coletores externos. |
| **10. Atualização Contínua de Documentação (Doc Sync)** | **PASS** | Documentação e contexto sincronizados em `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md` e `GEMINI.md`. |

---

## Project Structure

### Documentation (this feature)

```text
specs/012-cuda-vram-cleanup/
├── spec.md              # Requisitos funcionais, cenários de aceitação e critérios de sucesso
├── plan.md              # Este plano de implementação
├── research.md          # Fase 0: Pesquisa técnica e decisões arquiteturais de liberação de VRAM
├── data-model.md        # Fase 1: Modelo de dados, entidades e ciclo de vida do cleanup
├── quickstart.md        # Fase 1: Guia prático de testes e validação
├── contracts/           # Fase 1: Contratos de interface e observabilidade
│   └── cuda-vram-cleanup-contract.md
└── checklists/
    └── requirements.md  # Checklist de qualidade da especificação
```

### Source Code (Target Layout)

```text
src/clipper/
├── core/
│   ├── ingestion.py     # ATUALIZAR: Refatorar o bloco finally de transcribe_audio_chunk
│   └── orchestrator.py  # REUTILIZAR: Chamada sequencial de chunks via transcribe_audio_chunk
├── runtime/
│   ├── cuda_runtime.py  # ATUALIZAR: Implementar get_gpu_memory_info e release_cuda_memory
│   └── config.py        # REUTILIZAR: WHISPER_DEVICE, LLM_PROVIDER
tests/
├── test_cuda_cleanup.py # NOVO: Testes unitários para release_cuda_memory, isolamento e logs
└── test_transcription.py# ATUALIZAR: Validar garantia de fechamento de generator e del model
```

---

## Complexity Tracking

*No constitutional violations; no additional complexity exemptions required.*
