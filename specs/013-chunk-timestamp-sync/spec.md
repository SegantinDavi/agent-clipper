# Feature Specification: Chunk Timestamp Absolute Sync

**Feature Branch**: `013-chunk-timestamp-sync`  
**Created**: 2026-10-29  
**Status**: Draft  
**Input**: User description: "Sincronizar timestamps relativos dos chunks para o tempo absoluto do vídeo"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Legendas Alinhadas ao Vídeo Original (Priority: P1)

Um operador inicia o pipeline com um vídeo longo (acima de 15 min). O vídeo é dividido em chunks. Após o processamento completo, os legendas exibidas no preview e no vídeo aprovado aparecem sincronizadas com a fala, independente de qual chunk gerou aquele trecho de transcrição.

**Why this priority**: Sem esse alinhamento, legendas de qualquer chunk posterior ao primeiro estarão dessincronizadas, tornando o produto final inutilizável. É o defeito mais visível para o revisor humano.

**Independent Test**: Pode ser testado de forma isolada processando um vídeo com exatamente dois chunks e verificando que as palavras do chunk 2 possuem `word["start"]` ≥ duração do chunk 1, sem nenhuma palavra aparecendo com tempo menor que o offset esperado.

**Acceptance Scenarios**:

1. **Given** um vídeo de 20 minutos dividido em dois chunks (0–12 min e 12–20 min), **When** a transcrição do chunk 2 é concluída, **Then** cada palavra da transcrição do chunk 2 possui `start` e `end` somados ao offset de 12 min (720 s), resultando em tempos entre 720 s e 1200 s.
2. **Given** o array `word_timestamps_list` consolidado no `VideoState`, **When** o nó de edição (`editor.py`) aplica as legendas ao vídeo, **Then** cada segmento de legenda é posicionado no instante correto do vídeo original, sem deslocamento perceptível (≤ 0,1 s de drift).
3. **Given** um vídeo com apenas um chunk (duração < 15 min), **When** a transcrição é concluída, **Then** os timestamps permanecem inalterados (offset = 0), garantindo retrocompatibilidade.

---

### User Story 2 — Planos de Pausa Corretos nos Cortes Aprovados (Priority: P2)

Um revisor humano aprova um conjunto de cortes. Após a aprovação, o vídeo final renderizado remove as pausas nos momentos exatos identificados pelo FFmpeg e confirmados pelo Whisper, mesmo que os silêncios estejam em chunks diferentes do início.

**Why this priority**: O `pause_editing.py` consome os mesmos timestamps para calcular os intervalos de silêncio a remover. Timestamps relativos causariam remoção de pausas erradas no vídeo final, gerando artefatos de corte visíveis.

**Independent Test**: Pode ser testado verificando que os intervalos em `review.json` / `.pauses.json` referenciam tempos absolutos do vídeo original e que o mesmo plano aplicado ao áudio e ao vídeo resulta em sincronização perfeita.

**Acceptance Scenarios**:

1. **Given** um vídeo com silêncio detectado aos 18 min (chunk 2, tempo relativo 6 min), **When** `pause_editing.py` calcula os intervalos de corte, **Then** o intervalo registrado em `.pauses.json` é `[1080 s, 1080 s + duração_pausa]` e não `[360 s, ...]`.
2. **Given** o plano de pausa salvo em `.pauses.json`, **When** o mesmo plano é reutilizado em uma retomada de sessão (restart), **Then** os cortes são aplicados nas mesmas posições absolutas, sem recalcular offsets.

---

### User Story 3 — Remapeamento de Grupos de Palavras Preservado (Priority: P3)

Após a consolidação dos timestamps absolutos no `VideoState`, a função `remap_word_groups` recebe o array completo com tempos globais e produz grupos de legendas sem quebra de frases através de uma fronteira de chunk.

**Why this priority**: Sem isso, palavras no limite de dois chunks poderiam ser agrupadas incorretamente, criando legendas que começam antes de serem faladas ou que saltam para o início do vídeo.

**Independent Test**: Pode ser testado com um array sintético onde palavras de dois chunks são intercaladas na fronteira, verificando que `remap_word_groups` produz grupos contíguos e ordenados cronologicamente.

**Acceptance Scenarios**:

1. **Given** dois chunks com timestamps absolutos corretos concatenados em `word_timestamps_list`, **When** `remap_word_groups` é chamado, **Then** as palavras são agrupadas em segmentos contíguos sem gaps negativos ou sobreposições de tempo.
2. **Given** uma palavra no limite de dois chunks (última do chunk N e primeira do chunk N+1), **When** `remap_word_groups` processa o array, **Then** a palavra do chunk N+1 tem `start` maior que o `end` da última palavra do chunk N.

---

### Edge Cases

- O que acontece quando um chunk tem duração zero ou falha de transcrição? O offset deve ser propagado corretamente para o próximo chunk válido, sem corromper o array global.
- O que acontece quando o arquivo de chunk não possui metadado de `start_time`? O sistema deve falhar explicitamente com mensagem de erro descritiva em vez de silenciosamente usar offset 0.
- O que acontece com vídeos de um único chunk (duração < 15 min)? O offset deve ser 0.0 s e o array de palavras deve passar sem modificação.
- O que acontece se palavras do mesmo chunk chegarem fora de ordem cronológica do Whisper? O remapeamento não deve reordenar — apenas deslocar — preservando a estrutura original do Whisper.
- O que acontece quando `word_timestamps_list` está vazio para um chunk (sem fala detectada)? O sistema deve pular o offset desse chunk e prosseguir normalmente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema DEVE somar o `start_time` absoluto de cada chunk ao `start` e `end` de cada palavra transcrita por esse chunk antes de agregar ao `VideoState`.
- **FR-002**: O sistema DEVE preservar a estrutura de dados de cada palavra (todos os campos originais do Whisper) após o remapeamento, alterando apenas os campos `start` e `end`.
- **FR-003**: O sistema DEVE garantir que `word_timestamps_list` no `VideoState` contenha exclusivamente timestamps em tempo absoluto do vídeo original ao final da fase de transcrição.
- **FR-004**: O sistema DEVE expor o `start_time` de cada chunk no estado intermediário de processamento para que o remapeamento possa ser realizado sem acesso ao arquivo de vídeo original.
- **FR-005**: A função `remap_word_groups` DEVE receber e operar exclusivamente sobre timestamps absolutos, sem conhecimento de offsets de chunks.
- **FR-006**: O nó de edição (`editor.py`) DEVE consumir `word_timestamps_list` já com timestamps absolutos, sem realizar nenhuma conversão adicional de offset.
- **FR-007**: O módulo `pause_editing.py` DEVE calcular os intervalos de silêncio com base em timestamps absolutos, e o plano salvo em `.pauses.json` DEVE referenciar apenas tempos absolutos.
- **FR-008**: O sistema DEVE garantir retrocompatibilidade: vídeos processados como chunk único (offset = 0.0 s) NÃO devem ter comportamento alterado.
- **FR-009**: O sistema DEVE registrar em log o offset aplicado por chunk (nível INFO), incluindo o índice do chunk, o `start_time` usado e a contagem de palavras remapeadas.
- **FR-010**: O sistema DEVE falhar com erro explícito e descritivo caso o `start_time` de um chunk não esteja disponível no estado de processamento.

### Key Entities *(include if feature involves data)*

- **Chunk**: Segmento de vídeo/áudio gerado pelo fatiamento preventivo via FFmpeg. Possui atributos de índice, caminho do arquivo, `start_time` (tempo absoluto no vídeo original em segundos) e `end_time`.
- **WordTimestamp**: Estrutura de dado gerada pelo Whisper para cada palavra transcrita. Possui `word` (texto), `start` (tempo relativo ao chunk) e `end` (tempo relativo ao chunk). Após o remapeamento, `start` e `end` devem ser absolutos.
- **word_timestamps_list**: Array global no `VideoState` que agrega todas as `WordTimestamp` de todos os chunks, com timestamps absolutos após a fase de transcrição.
- **VideoState**: Estado global do grafo LangGraph que transporta dados entre nós. Deve conter o array `word_timestamps_list` com valores absolutos e a lista de chunks com seus `start_time`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Para qualquer vídeo processado com 2 ou mais chunks, 100% das palavras em `word_timestamps_list` possuem `start` ≥ `start_time` do chunk que as originou — verificável por inspeção do estado do grafo após a fase de transcrição.
- **SC-002**: O drift máximo entre o timestamp de uma palavra remapeada e a posição real da fala no áudio original é ≤ 0,1 s — verificável por comparação auditiva ou por teste automatizado com fixture de áudio sintético.
- **SC-003**: Vídeos de chunk único processados antes e depois desta mudança produzem `word_timestamps_list` idênticos — verificável por teste de regressão que compara os arrays palavra por palavra.
- **SC-004**: O plano de pausas em `.pauses.json` gerado para um vídeo de múltiplos chunks referencia apenas intervalos dentro do intervalo `[start_time_chunk_N, end_time_chunk_N]` para as pausas originadas no chunk N — verificável por validação automatizada do JSON.
- **SC-005**: Nenhum erro de renderização de legenda (legenda fora de sincronia com a fala) é relatado pelo revisor humano para vídeos processados após esta correção — verificável via aprovação HITL em sessão de teste.

## Assumptions

- O `start_time` de cada chunk já está disponível no estado intermediário do grafo, derivado do fatiamento FFmpeg (via `silencedetect` ou corte por duração fixa). Caso não esteja, será tratado como bloqueio de implementação.
- O Whisper fornece `word_timestamps` em tempo relativo ao áudio do chunk — comportamento documentado e verificado empiricamente no projeto.
- A operação de remapeamento deve ocorrer no nó de transcrição (`clipper.core.ingestion`), antes da agregação ao `VideoState`, para garantir que nenhum consumidor downstream precise conhecer offsets de chunks.
- O formato de `WordTimestamp` retornado pelo faster-whisper é um objeto com atributos `.start`, `.end` e `.word`, convertido para `dict` antes do armazenamento no estado.
