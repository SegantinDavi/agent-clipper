# Data Model: Chunk Timestamp Absolute Sync

**Feature**: `013-chunk-timestamp-sync`  
**Phase**: 1 — Design & Contracts

## Entidades Existentes (sem alteração de schema)

### `AudioChunk` (dict estruturado — `node_0.py` → `VideoState.audio_chunks`)

Produzido por `node_0_preventive_slicing()`. Sem mudança de estrutura.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `chunk_path` | `str` | Caminho absoluto do arquivo WAV do chunk |
| `offset` | `float` | Tempo absoluto (segundos) em que o chunk começa no vídeo original |

> [!IMPORTANT]
> `offset` é o único campo novo que esta feature consome. Ele **já existe** na saída de
> `node_0_preventive_slicing()` (veja `node_0.py` linha 90 e 109). Não há mudança de
> schema aqui.

---

### `WordTimestamp` (dict — `VideoState.word_timestamps`)

Gerado pelo Whisper via `transcribe_audio_chunk()` com tempos **relativos ao chunk**.
Após `apply_chunk_offset()`, os campos `start`/`end` tornam-se **absolutos**.

| Campo | Tipo | Origem | Estado antes do offset | Estado após `apply_chunk_offset` |
|-------|------|--------|------------------------|----------------------------------|
| `word` | `str` | Whisper | Texto da palavra | Inalterado |
| `start` | `float` | Whisper | Relativo ao chunk (ex: `3.2`) | Absoluto (ex: `723.2`) |
| `end` | `float` | Whisper | Relativo ao chunk (ex: `3.8`) | Absoluto (ex: `723.8`) |

> [!NOTE]
> Os campos `start` e `end` são arredondados a 2 casas decimais após o offset
> (`round(..., 2)`) — comportamento atual preservado para evitar drift de ponto flutuante.

---

### `VideoState` (TypedDict — `orchestrator.py`)

Sem mudança de campos. A garantia semântica do campo `word_timestamps` é fortalecida:

| Campo | Tipo | Garantia **antes** desta feature | Garantia **depois** |
|-------|------|----------------------------------|---------------------|
| `audio_chunks` | `list` | Lista de dicts `{chunk_path, offset}` | **Idem** |
| `word_timestamps` | `list[dict]` | Absoluto na prática, sem teste | **Absoluto, verificado por testes** |
| `transcript_grouped` | `str` | Timestamps absolutos para offset > 0 via regex | **Idem** |

---

## Nova Entidade: `apply_chunk_offset` (função pura — `ingestion.py`)

Não é um modelo de dados, mas define o contrato de transformação:

**Entrada**:
- `words: list[dict]` — lista de WordTimestamp com tempos relativos ao chunk
- `offset: float` — `chunk["offset"]` do AudioChunk
- `chunk_index: int` — índice do chunk (0-based), usado apenas para log

**Saída**: `list[dict]` — lista de WordTimestamp com `start`/`end` absolutos

**Invariantes**:
- Se `offset == 0.0`, retorna lista nova com mesmos valores (sem mutação in-place)
- Se `words` é vazia, retorna lista vazia
- Cada item de saída tem exatamente os campos `{"word", "start", "end"}`
- `result[i]["start"] == round(words[i]["start"] + offset, 2)` para todo `i`
- `result[i]["end"] == round(words[i]["end"] + offset, 2)` para todo `i`

## Fluxo de dados completo

```text
node_0_preventive_slicing()
    → chunks: [{"chunk_path": "audio_chunk_000.wav", "offset": 0.0},
               {"chunk_path": "audio_chunk_001.wav", "offset": 720.0}, ...]

transcription_node()  [por chunk]
    → transcribe_audio_chunk(chunk_path)
        → words_relative: [{"word": "Olá", "start": 0.1, "end": 0.4}, ...]
    → apply_chunk_offset(words_relative, offset=720.0, chunk_index=1)
        → words_absolute: [{"word": "Olá", "start": 720.1, "end": 720.4}, ...]
    → agrega em aggregated_word_timestamps

VideoState.word_timestamps = aggregated_word_timestamps
    ↓
preview_node / build_pause_plan(video_path, start=720.0, end=840.0, words=word_timestamps)
    ↓  [speech_intervals filtra words com start/end dentro de [720.0, 840.0]]
remap_word_groups(word_timestamps, plan)
    ↓  [subtrai plan.source_start de cada word["start"]]
group_caption_words(words, start_time=0, end_time=plan.duration)
    ↓  [subtrai start_time=0 — timestamps já são relativos ao corte após remap]
editor_node / cut_and_format_video()
```
