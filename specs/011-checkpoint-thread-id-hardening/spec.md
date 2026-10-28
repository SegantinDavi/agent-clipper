# Feature Specification: Checkpoint Thread ID Hardening

**Feature Branch**: `011-checkpoint-thread-id-hardening`  
**Created**: 2026-10-28  
**Status**: Draft  
**Input**: User description: "Blindar o Thread ID do Checkpointer contra colisão de contexto"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Retomada Segura em Perfil Diferente (Priority: P1)

Um operador rodou o pipeline para um vídeo com `LLM_PROVIDER=ollama` e os checkpoints foram salvos no SQLite. Em seguida, ele roda o mesmo vídeo com `LLM_PROVIDER=gemini`. O pipeline deve tratar essa execução como um estado completamente novo, gerando um novo `thread_id`, ignorando os checkpoints anteriores e iniciando o processamento do zero.

**Why this priority**: Sem esta proteção, o LangGraph reaproveitará um checkpoint gerado com Ollama para uma run Gemini, causando conflitos de schema, consumo inesperado de VRAM e resultados de edição incorretos.

**Independent Test**: Pode ser testado isoladamente executando o pipeline duas vezes para o mesmo vídeo com providers distintos e verificando que o `thread_id` gerado é diferente em cada execução.

**Acceptance Scenarios**:

1. **Given** um checkpoint existente para o vídeo X com `LLM_PROVIDER=ollama`, **When** o pipeline é iniciado para o vídeo X com `LLM_PROVIDER=gemini`, **Then** o pipeline gera um novo `thread_id` único e não reutiliza nenhum dado do checkpoint anterior.
2. **Given** dois ambientes com o mesmo vídeo e mesmo provider, **When** ambos os pipelines são iniciados simultaneamente, **Then** ambos produzem o mesmo `thread_id` determinístico (idempotência).

---

### User Story 2 - Retomada Segura com Configuração de Silêncio Diferente (Priority: P2)

Um operador processou um vídeo sem corte de silêncio (`SILENCE_CUT_ENABLED=false`) e aprovou os clipes. Ao reprocessar o mesmo vídeo com corte de silêncio habilitado (`SILENCE_CUT_ENABLED=true` e `SILENCE_MIN_PAUSE=0.8`), o pipeline não deve reaproveitar o `review.json` anterior — que contém intervalos de tempo inconsistentes com o novo plano de edição.

**Why this priority**: Reutilizar um `review.json` gerado sem corte de silêncio em uma run com corte geraria tempos errados nos clipes aprovados, corrompendo o output final.

**Independent Test**: Testável rodando o pipeline para o mesmo vídeo com `SILENCE_CUT_ENABLED=false` e depois com `true`, verificando que o `thread_id` difere e que o arquivo `review.json` é gerado do zero na segunda run.

**Acceptance Scenarios**:

1. **Given** um checkpoint com `SILENCE_CUT_ENABLED=false`, **When** o pipeline roda com `SILENCE_CUT_ENABLED=true`, **Then** o `thread_id` é diferente e nenhum `review.json` antigo é carregado.
2. **Given** `SILENCE_CUT_ENABLED=true` e `SILENCE_MIN_PAUSE=0.6`, **When** o mesmo pipeline roda com `SILENCE_MIN_PAUSE=1.0`, **Then** um novo `thread_id` é gerado, garantindo que o novo plano de pausas seja calculado do zero.

---

### User Story 3 - Retomada Legítima do Estado (Priority: P3)

Um operador iniciou o pipeline para um vídeo com os mesmos parâmetros de uma run anterior que sofreu crash. O sistema deve identificar o mesmo `thread_id` e retomar o processamento exatamente do ponto onde parou, sem reprocessar etapas já concluídas.

**Why this priority**: A retomada de crash é um requisito de resiliência já existente; o hardening não deve quebrá-la — ao contrário, deve garantir que a retomada só ocorra quando todos os parâmetros são identicamente iguais.

**Independent Test**: Testável simulando um crash após a transcrição e reiniciando com os mesmos parâmetros, verificando que a transcrição não é reexecutada.

**Acceptance Scenarios**:

1. **Given** um pipeline interrompido após a transcrição (vídeo X, gemini, modelo Y, silêncio off), **When** o pipeline é reiniciado com os mesmos parâmetros, **Then** o `thread_id` é idêntico e o grafo retoma a partir do nó pós-transcrição.
2. **Given** a flag `--restart` ativa, **When** o pipeline é iniciado para qualquer combinação de parâmetros, **Then** os checkpoints da thread correspondente são purgados e um novo ciclo começa.

---

### Edge Cases

- O que acontece se `SILENCE_MIN_PAUSE` não estiver definido (valor `None` ou ausente)? A função de hash deve usar um valor padrão documentado para garantir consistência entre ambientes.
- O que acontece se o `MODEL_NAME` estiver vazio ou indefinido no ambiente? O hash deve usar uma string vazia ou o nome padrão do modelo, nunca falhar silenciosamente.
- O que acontece se o banco `estado.db` contiver checkpoints de versões antigas (antes do hardening)? Esses checkpoints se tornam inacessíveis — o comportamento é equivalente a uma run completamente nova.
- O que acontece se dois vídeos diferentes compartilharem o mesmo ID após normalização? O ID de vídeo deve ser incluído na forma bruta (sem transformação) para preservar unicidade.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE gerar o `thread_id` do checkpointer como um hash SHA-256 determinístico, truncado para 16 caracteres hexadecimais, garantindo unicidade e legibilidade nos logs.
- **FR-002**: O hash DEVE ser composto pela concatenação ordenada de: `[video_id] + [LLM_PROVIDER] + [MODEL_NAME] + [SILENCE_CUT_ENABLED] + [SILENCE_MIN_PAUSE]`, com separador `|` entre campos.
- **FR-003**: A função `checkpoint_thread_id` DEVE retornar resultados idênticos para os mesmos valores de entrada em qualquer execução (propriedade determinística).
- **FR-004**: A função DEVE tolerar valores `None` ou ausentes para parâmetros opcionais, substituindo-os por valores padrão definidos e documentados (ex: `SILENCE_MIN_PAUSE` ausente → `"0.6"`).
- **FR-005**: O código DEVE incluir um comentário de aviso inline documentando que alterações nesta função invalidam checkpoints existentes no `estado.db`.
- **FR-006**: O `orchestrator.py` DEVE exibir no log de nível `INFO` o `thread_id` calculado a cada execução, permitindo rastreabilidade.
- **FR-007**: Os testes unitários DEVEM cobrir ao menos os seguintes cenários: mesmo vídeo + provider diferente → thread_id diferente; mesmo vídeo + silêncio diferente → thread_id diferente; mesmos parâmetros → thread_id idêntico.

### Key Entities

- **`checkpoint_thread_id`**: Função pura em `orchestrator.py` responsável por derivar o identificador único de sessão do LangGraph a partir dos parâmetros de execução. Atributos: `video_id`, `llm_provider`, `model_name`, `silence_cut_enabled`, `silence_min_pause`.
- **`thread_id`**: String hexadecimal de 16 caracteres usada como chave primária da thread no banco SQLite do checkpointer. Determina qual sequência de estados será retomada ou iniciada.
- **`estado.db`**: Banco SQLite persistido em `/app/output/` que armazena todos os checkpoints do LangGraph. Afetado diretamente pela mudança de algoritmo de geração do `thread_id`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% dos cenários de isolamento de contexto validados nos testes unitários passam sem falha — mesmo vídeo com provider diferente, modelo diferente e configuração de silêncio diferente geram `thread_id` distintos.
- **SC-002**: O `thread_id` gerado para os mesmos parâmetros é sempre idêntico em 100% das execuções (propriedade determinística verificável por teste).
- **SC-003**: Zero reaproveitamento de checkpoint entre runs com parâmetros distintos em qualquer teste de integração que cubra a retomada de estado.
- **SC-004**: O tempo de geração do `thread_id` é imperceptível para o operador — inferior a 1ms, sem impacto no tempo total do pipeline.
- **SC-005**: Nenhum checkpoint existente no `estado.db` gerado antes desta feature é retomado silenciosamente; runs com parâmetros iguais aos antigos iniciam do zero (comportamento verificável por inspeção do log de `thread_id`).

## Assumptions

- O `LLM_PROVIDER`, `MODEL_NAME`, `SILENCE_CUT_ENABLED` e `SILENCE_MIN_PAUSE` já estão disponíveis como variáveis de ambiente ou atributos do objeto de configuração no momento em que `checkpoint_thread_id` é chamado.
- O `video_id` é o identificador bruto do YouTube (ex: `dQw4w9WgXcQ`), sem normalização ou codificação adicional.
- SHA-256 truncado a 16 caracteres hexadecimais oferece espaço de colisão suficiente (2^64) para o volume de vídeos e configurações esperados neste projeto.
- Checkpoints existentes no `estado.db` não serão migrados — a invalidação é aceita como trade-off documentado.
