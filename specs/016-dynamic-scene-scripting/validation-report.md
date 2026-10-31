# Validation Report: Dynamic Scene Scripting via Constrained Decoding (Feature 016)

**Date**: 2026-10-31T18:58:35-03:00  
**Feature Branch**: `016-dynamic-scene-scripting`  
**Status**: PASS  

---

## Coverage Summary

| Metric | Count | Percentage |
|--------|-------|------------|
| Functional Requirements Covered | 9/9 | 100% |
| Acceptance Criteria Met | 9/9 | 100% |
| Edge Cases Handled | 6/6 | 100% |
| Success Criteria Satisfied | 5/5 | 100% |
| Tests Present | 9/9 | 100% |

---

## Requirements Verification Matrix

| Requirement | Description | Implementation File | Test Verification | Status |
|-------------|-------------|---------------------|-------------------|:------:|
| **FR-001** | Entidade `Scene` com quatro campos obrigatórios (`start_word`, `end_word`, `visual_metaphor`, `animation_trigger`) e `min_length=1`. | `src/clipper/core/schemas.py:4-21` | `tests/test_scene_scripting.py:43-102` (`TestSceneValidationConstraints`) | **PASS** |
| **FR-002** | Campo `scenes: list[Scene]` obrigatório em `CorteVideo` com no mínimo um item por corte e contrato JSON Schema validado. | `src/clipper/core/schemas.py:30-34`, `contracts/corte_video_schema.json` | `tests/test_scene_scripting.py:13-41, 104-145` (`TestSceneScriptingSchemaContract`, `TestCorteVideoBackwardCompatibilityAndScenes`) | **PASS** |
| **FR-003** | Decodificação restrita via `instructor` + Pydantic como único mecanismo de extração (zero regex ou `json.loads` manual). | `src/clipper/core/orchestrator.py:384-416` | `tests/test_scene_scripting.py:723-755` (`TestExtractionStaticAnalysisCompliance` - AST scan) | **PASS** |
| **FR-004** | `EXTRACTOR_SYSTEM_PROMPT_TEMPLATE` instrui divisão em cenas de 2–4s, metáforas visuais variadas e gatilhos de animação. | `src/clipper/core/prompts.py:145-156` | `tests/test_scene_scripting.py:483-497` (`test_extractor_system_prompt_contains_scene_scripting_instructions`) | **PASS** |
| **FR-005** | `EXTRACTOR_FEW_SHOT_EXAMPLES` contém ≥ 2 exemplos completos demonstrando mapeamento frase → `Scene` com metáforas e gatilhos dinâmicos. | `src/clipper/core/prompts.py:163-275` | `tests/test_scene_scripting.py:499-569` (`test_extractor_few_shot_examples_assistant_payloads_parse_strictly_with_scenes`, `test_extractor_few_shot_examples_demonstrate_diverse_metaphors_and_triggers`) | **PASS** |
| **FR-006** | `extractor_node` síncrono retorna lista de `CorteVideo` com cenas sem alterar a assinatura nem o fluxo do LangGraph. | `src/clipper/core/orchestrator.py:368-450` | `tests/test_scene_scripting.py:147-215` (`TestExtractorNodeSceneExtraction`), `tests/test_instructor_sync_contract.py:522-556` | **PASS** |
| **FR-007** | Neutralidade de provedor LLM (`ollama` local e `gemini` API) sem alteração de roteamento. | `src/clipper/core/orchestrator.py:382-418` | `tests/test_scene_scripting.py:571-626` (`TestLLMProviderNeutralitySceneExtraction`) | **PASS** |
| **FR-008** | Serialização transparente de `scenes` no `VideoState` via `SqliteSaver`, garantindo retomada de checkpoint sem perda de dados. | `src/clipper/core/orchestrator.py:450`, `src/clipper/review/review.py:19-30` | `tests/test_scene_scripting.py:628-721` (`TestSqliteSaverScenePersistence`), `tests/test_review.py:539-572` | **PASS** |
| **FR-009** | Erro explícito (`ValueError` fail-fast) quando o LLM retornar uma lista vazia de cenas para qualquer corte. | `src/clipper/core/orchestrator.py:423-430` | `tests/test_scene_scripting.py:217-295` (`TestExtractorNodeEmptyScenesFailFast`) | **PASS** |

---

## Acceptance Criteria Verification

### User Story 1 — Cortes com cenas segmentadas e enriquecidas (P1)
- [x] **AC-1.1**: Ao processar recomendação de 30s, cada `CorteVideo` retornado contém ao menos 1 item em `scenes`.  
  *Evidence*: `tests/test_scene_scripting.py:150-215`, `tests/test_instructor_sync_contract.py:522-556`.
- [x] **AC-1.2**: Cada `Scene` possui duração aproximada de 2 a 4s; cenas com duração > 4s geram aviso editorial (WARNING) sem descartar o corte.  
  *Evidence*: `src/clipper/core/orchestrator.py:295-366`, `tests/test_scene_scripting.py:300-356`.
- [x] **AC-1.3**: Decodificação restrita garante presença e tipos corretos de todos os 4 campos (`start_word`, `end_word`, `visual_metaphor`, `animation_trigger`) sem parsing manual.  
  *Evidence*: `tests/test_scene_scripting.py:43-102, 723-755`.

### User Story 2 — Instruções claras para mapear falas em gatilhos visuais (P2)
- [x] **AC-2.1**: Em momentos de revelação/surpresa, gatilhos de impacto ou zoom são orientados no prompt do sistema.  
  *Evidence*: `src/clipper/core/prompts.py:153-156`, `tests/test_scene_scripting.py:483-497`.
- [x] **AC-2.2**: Exemplos few-shot demonstram metáforas visuais diversas sem repetições monótonas dentro do mesmo corte.  
  *Evidence*: `src/clipper/core/prompts.py:195-217, 250-272`, `tests/test_scene_scripting.py:542-569`.
- [x] **AC-2.3**: Perfis Ollama e Gemini produzem estruturas `CorteVideo` idênticas segundo o schema Pydantic.  
  *Evidence*: `tests/test_scene_scripting.py:571-626`.

### User Story 3 — Cenas persistidas e visíveis na revisão humana (P3)
- [x] **AC-3.1**: `approval_node` serializa `scenes` para `review.json` sem perda de dados via `ReviewManifest`.  
  *Evidence*: `src/clipper/review/review.py:19-30, 99`, `tests/test_review.py:539-572`.
- [x] **AC-3.2**: Servidor de revisão renderiza cards com `<div class="scenes">`, exibindo limites textuais, metáforas e gatilhos com sanitização HTML.  
  *Evidence*: `src/clipper/review/review.py:145-168`, `tests/test_review.py:573-657`.
- [x] **AC-3.3**: Checkpointer `SqliteSaver` restaura `cortes_finais` com cenas íntegras após crash simulado e retomada via `Command(resume=...)`.  
  *Evidence*: `tests/test_scene_scripting.py:628-721`.

---

## Edge Case Handling Verification

| Edge Case | Expected Behavior | Code Implementation | Verification Test | Status |
|-----------|-------------------|---------------------|-------------------|:------:|
| **EC-1**: Lista de cenas vazia (`scenes: []`) | Falha explícita (fail-fast) com `ValueError` | `orchestrator.py:423-430` | `test_extractor_node_raises_value_error_on_empty_scenes`, `test_extractor_node_fails_fast_when_any_cut_has_empty_scenes` | **PASS** |
| **EC-2**: `start_word` ou `end_word` vazios | Rejeição imediata no Pydantic via `min_length=1` | `schemas.py:5-12` | `test_empty_start_word_raises_validation_error`, `test_empty_end_word_raises_validation_error` | **PASS** |
| **EC-3**: Duração da cena excede 4.0s | Emissão de warning editorial no logger sem rejeitar corte | `orchestrator.py:357-365` | `test_extractor_node_logs_warning_when_scene_duration_exceeds_4s` | **PASS** |
| **EC-4**: Gatilho fora de vocabulário restrito | Aceito como string arbitrária sem quebrar validação | `schemas.py:17-20` | `test_valid_scene_creation` | **PASS** |
| **EC-5**: LLM tenta escapar da decodificação | `instructor` retenta até `max_retries=2` e lança erro de validação | `orchestrator.py:404` | `tests/test_instructor_sync_contract.py:476-506` | **PASS** |
| **EC-6**: Falta de timestamps de palavras | Fallback gracioso: validação de pacing é ignorada sem exceções | `orchestrator.py:303-304` | `test_extractor_node_graceful_fallback_when_word_timestamps_empty`, `test_extractor_node_graceful_fallback_when_word_timestamps_missing` | **PASS** |

---

## Success Criteria Verification

- [x] **SC-001**: 100% dos cortes extraídos contêm ao menos uma `Scene` com todos os 4 campos obrigatórios preenchidos.
- [x] **SC-002**: Análise estática AST confirma zero chamadas a `json.loads/load` manual ou `re.*` na camada de extração (`extractor_node`).
- [x] **SC-003**: Benchmark de overhead de execução mock do `extractor_node` registrou execução em < 1ms, amplamente inferior ao teto de 50ms wall-clock.
- [x] **SC-004**: Suite completa de testes automatizados executou 202 testes (0 falhas, 0 erros, 1 skip justificado) garantindo zero regressões sobre os 172 testes baseline.
- [x] **SC-005**: Persistência SQLite (`SqliteSaver`) e recuperação pós-crash do campo `scenes` verificada com 100% de integridade estrutural.

---

## Constitution & Architecture Constraints Check

| Rule / Constraint | Verification | Status |
|-------------------|--------------|:------:|
| **Hardware Constraints (8GB RAM / 12GB VRAM)** | Nenhuma nova dependência adicionada; zero impacto de consumo de memória | **PASS** |
| **Strict Constrained Decoding (AGENTS.md Rule 5)** | Apenas `instructor` + Pydantic com `openai.pydantic_function_tool` strict | **PASS** |
| **Synchronous Node Contracts (AGENTS.md Rule 3)** | Todos os nós são funções convencionais `def`; `raw_client.close()` garantido em `finally` | **PASS** |
| **State Machine Persistence (AGENTS.md Rule 3)** | Dicionários primitivos em `cortes_finais` serializáveis transparentemente em SQLite | **PASS** |
| **Human-in-the-Loop Integration (AGENTS.md Rule 3, 6)** | Primitiva `interrupt()`, HTML seguro com sanitização em `render_review_page` | **PASS** |
| **Single-Model Cognitive Routing (AGENTS.md Rule 4)** | Mesmo modelo e cliente entre Thinker e Extractor sem hot-swapping de modelos | **PASS** |
| **Documentation Synchronization (AGENTS.md Rule 10)** | `README.md`, `AGENTS.md`, `GEMINI.md` sincronizados | **PASS** |

---

## Uncovered Requirements

*Nenhum requisito descoberto ou pendente. 100% dos requisitos, cenários de aceitação e critérios de sucesso foram implementados e validados por testes automatizados.*

---

## Recommendations

1. **Avanço para Fase 3 (Edição Baseada em Cenas)**: Com o schema `Scene` consolidado e testado ponta a ponta, a próxima feature de renderização de vídeo pode utilizar diretamente `corte.scenes` para orquestrar transições e B-rolls específicos por intervalo de cena.
2. **Vocabulário Controlado Opcional**: No futuro, se a engine de vídeo exigir um enum fixo de transições (ex: `zoom_in`, `cut_transition`, `impact`), um `Enum` Pydantic pode ser adicionado como refinamento adicional sem quebrar a estrutura existente.
