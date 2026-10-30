# Implementation Plan: Chunk Timestamp Absolute Sync

**Branch**: `013-chunk-timestamp-sync` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/013-chunk-timestamp-sync/spec.md`

## Summary

O pipeline de transcrição multi-chunk do agent-clipper aplica o offset de tempo absoluto
ao `transcript_string` e ao `word_timestamps_list` dentro do `transcription_node`
(orchestrator.py, linhas 179–200). Contudo, **o remapeamento está implementado porém
não testado e não validado de ponta a ponta**. Esta feature garante:

1. Cobertura de testes unitários e de integração para o caminho de offset no
   `transcription_node`.
2. Extração da lógica de offset para a função `apply_chunk_offset` em
   `clipper.core.ingestion`, tornando-a reutilizável, rastreável e testável de forma
   isolada.
3. Log INFO explícito por chunk (índice, offset, contagem de palavras remapeadas),
   exigido por FR-009 da spec.
4. Falha explícita quando `chunk["offset"]` não está presente no dict do chunk (FR-010).
5. Validação de que `remap_word_groups`, `group_caption_words`, `speech_intervals` e
   `build_pause_plan` já operam corretamente sobre timestamps absolutos (nenhuma mudança
   de produção necessária nessas funções — confirmado pela inspeção do código).

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: faster-whisper, langgraph, moviepy==1.0.3, pydantic, instructor  
**Storage**: SQLite (`/app/output/estado.db` via `SqliteSaver`), arquivos WAV de chunk em `/app/output/`  
**Testing**: unittest (padrão do projeto), `PYTHONPATH=src python -m unittest discover tests/`  
**Target Platform**: Docker sobre WSL2 (Debian-slim), 8 GB RAM, RTX 3060 12 GB VRAM  
**Project Type**: Single project Python (pipeline de CLI)  
**Performance Goals**: O remapeamento é uma operação O(n) sobre a lista de palavras — sem impacto mensurável no throughput do pipeline  
**Constraints**: Sem CUDA durante remapeamento (operação pure-Python); zero dependências novas; sem alteração de interface pública de nenhum nó LangGraph existente  
**Scale/Scope**: Vídeos de até ~2 h divididos em ≤ 12 chunks de 10 min; `word_timestamps_list` com até ~12.000 palavras por vídeo

## Constitution Check

*GATE: Verificado contra AGENTS.md antes do design.*

| Regra AGENTS.md | Status | Observação |
|----------------|--------|------------|
| Sem regex/json.loads manual para limpar saída de IA (§5) | ✅ Não aplicável | Sem interação com LLM nesta feature |
| MoviePy: dimensões pares, yuv420p, Liberation Sans (§6) | ✅ Não alterado | Sem mudanças no editor |
| Transcrição: CPU/int8 (Ollama) ou CUDA/float16 (Gemini) (§1) | ✅ Preservado | `transcribe_audio_chunk` não muda de assinatura |
| Unload de modelo + GC após chunk (§1, §2) | ✅ Preservado | `finally` block em `ingestion.py` não alterado |
| Sem telemetria externa (§9) | ✅ Cumprido | Apenas logging via `logger.info` |
| LangGraph StateGraph + interrupt() HITL (§3) | ✅ Preservado | `VideoState` e grafo não sofrem mudança estrutural |
| Nomenclatura em inglês (§8) | ✅ Será cumprido | Toda nova função e parâmetro em inglês |
| Sem hardcode de URL/parâmetro (§7) | ✅ Não aplicável | Sem novos parâmetros de ambiente |
| Checkpoints incluem identidade completa (§7) | ✅ Não alterado | `checkpoint_thread_id` intacto |
| Doc Sync ao finalizar (§10) | 🔲 Pendente | GEMINI.md e AGENTS.md a atualizar após merge |

**Resultado:** ✅ Sem violações. Nenhuma entrada na tabela Complexity Tracking.

## Phase 0: Research

### Finding 1 — O offset já é calculado, mas na camada errada

**Decisão**: Mover `apply_chunk_offset` para `clipper.core.ingestion` (nova função pura),
chamada pelo `transcription_node` em `orchestrator.py`.

**Rationale**: O cálculo de offset hoje está embutido diretamente no loop do
`transcription_node` sem nome, sem log e sem testes unitários. Ao extraí-lo para
`ingestion.py` como função pura (`apply_chunk_offset`), o remapeamento torna-se:
- Testável de forma isolada (sem mock do grafo LangGraph)
- Rastreável via `logger.info` com índice, offset e contagem
- Reutilizável por qualquer consumidor futuro sem acesso ao orquestrador

**Alternatives considered**:
- *Deixar no orquestrador*: Mantém o bug de não-testabilidade e viola o princípio de
  Single Responsibility — o nó de transcrição não deveria saber de matemática de offset.
- *Mover para `node_0.py`*: Incorreto — `node_0.py` produz chunks mas não transcreve.

### Finding 2 — `remap_word_groups` já opera corretamente sobre timestamps absolutos

**Decisão**: Nenhuma alteração em `pause_editing.py` ou `editor.py`.

**Rationale**: Inspecção do código confirmou:
- `remap_word_groups` (`pause_editing.py` L198-219): subtrai `plan.source_start` de cada
  `word["start"]` — espera timestamps absolutos ✅
- `speech_intervals` (`pause_editing.py` L89-112): compara `word["start"]` com
  `start`/`end` absolutas do corte ✅
- `group_caption_words` (`editor.py` L79-112): subtrai `start_time` absoluto do corte ✅
- `build_pause_plan` chamado em `review.py` L97-98 com `cut.start_time` absoluto ✅

**Alternatives considered**: Adicionar assert de sanidade em `remap_word_groups` para
detectar timestamps relativos — rejeitado por overhead desnecessário; a garantia vem dos
testes do `transcription_node`.

### Finding 3 — Falha silenciosa quando chunk não é dict (fallback para offset 0.0)

**Decisão**: Lançar `ValueError` explícito quando `chunk_path` é inferido de um objeto
não-dict sem `offset`.

**Rationale**: O `transcription_node` atual tem:
```python
else:
    chunk_path = str(chunk)
    offset = 0.0  # silently ignores missing offset
```
Isso é um bug latente: se `node_0_preventive_slicing` retornar um formato inesperado, o
pipeline prossegue com offset 0.0 sem aviso, dessincronizando todos os chunks. A falha
explícita está exigida por FR-010.

**Alternatives considered**: Warning ao invés de erro — rejeitado porque offset errado
produz vídeo inutilizável; falha rápida é preferível.

### Finding 4 — `transcript_string` remapeado apenas quando `offset > 0`

**Decisão**: Preservar o comportamento atual (sem mudança).

**Rationale**: O `transcript_string` é consumido apenas pelo `thinker_node` e
`extractor_node` para análise editorial. Timestamps absolutos no texto já são gerados
corretamente para `offset > 0` via regex substituição (L181-188 do orquestrador). Para
`offset == 0` (chunk único ou primeiro chunk), os tempos já são absolutos sem ajuste.
Nenhum consumidor downstream da `transcript_string` depende de precisão sub-segundo; a
granularidade de segundos é suficiente para o Thinker/Extractor.

## Phase 1: Design & Contracts

### Data Model

Ver [`data-model.md`](data-model.md) para a especificação completa dos tipos envolvidos.

### Arquitetura de mudanças

```text
ANTES (fluxo atual):
  node_0_preventive_slicing()  →  chunks: list[{"chunk_path": str, "offset": float}]
  transcription_node()         →  loop inline: offset aplicado sem nome, sem log, sem teste
  word_timestamps no estado    →  absoluto (correctamente), mas sem garantia testada

DEPOIS (fluxo proposto):
  node_0_preventive_slicing()  →  chunks: list[{"chunk_path": str, "offset": float}]  [INALTERADO]
  apply_chunk_offset()         →  nova função pura em ingestion.py
  transcription_node()         →  delega a apply_chunk_offset(); falha explícita se offset ausente
  word_timestamps no estado    →  absoluto, garantido por testes unitários
```

### Contratos internos (sem API HTTP — pipeline CLI)

**`apply_chunk_offset(words, offset, chunk_index)`** — ver [`contracts/apply_chunk_offset.md`](contracts/apply_chunk_offset.md)

### Estrutura de arquivos afetados

```text
src/
└── clipper/
    └── core/
        ├── ingestion.py          # +apply_chunk_offset() nova função pura
        └── orchestrator.py       # transcription_node: delega offset + falha explícita

tests/
├── test_chunk_timestamp_sync.py  # NOVO: testes unitários e de integração da feature
└── test_transcription.py         # EXISTENTE: nenhuma alteração (continua passando)
```

## Project Structure

### Documentation (this feature)

```text
specs/013-chunk-timestamp-sync/
├── plan.md                        # Este arquivo
├── research.md                    # Consolidado nas seções Phase 0 acima
├── data-model.md                  # Tipos e fluxo de dados
├── contracts/
│   └── apply_chunk_offset.md      # Contrato da nova função pura
└── tasks.md                       # Gerado por /speckit.tasks
```

### Source Code (repository root)

```text
src/
└── clipper/
    └── core/
        ├── ingestion.py          # Modificado: +apply_chunk_offset()
        └── orchestrator.py       # Modificado: transcription_node usa apply_chunk_offset()

tests/
└── test_chunk_timestamp_sync.py  # Novo arquivo de testes
```

**Structure Decision**: Single project Python (sem novos módulos ou pacotes). Todas as
mudanças ficam dentro da estrutura `src/clipper/core/` existente.
