# Contract: `apply_chunk_offset`

**Módulo**: `clipper.core.ingestion`  
**Feature**: `013-chunk-timestamp-sync`

## Assinatura

```python
def apply_chunk_offset(
    words: list[dict],
    offset: float,
    chunk_index: int,
) -> list[dict]:
```

## Descrição

Função pura que desloca os campos `start` e `end` de cada `WordTimestamp` pelo valor
de `offset` (segundos), convertendo timestamps relativos ao chunk para tempo absoluto
do vídeo original.

Emite um log `INFO` com índice do chunk, offset aplicado e total de palavras remapeadas.

## Parâmetros

| Parâmetro | Tipo | Restrições | Descrição |
|-----------|------|------------|-----------|
| `words` | `list[dict]` | Cada dict deve ter `"word"`, `"start"`, `"end"` | WordTimestamps relativos ao chunk, retornados por `transcribe_audio_chunk()` |
| `offset` | `float` | `≥ 0.0` | Tempo absoluto (segundos) do início do chunk no vídeo original. Valor `0.0` retorna cópia sem modificação numérica. |
| `chunk_index` | `int` | `≥ 0` | Índice 0-based do chunk; usado exclusivamente para o log INFO. |

## Retorno

`list[dict]` — Nova lista (sem mutação da entrada) onde cada elemento é:

```python
{
    "word":  str,    # copiado sem alteração
    "start": float,  # round(word["start"] + offset, 2)
    "end":   float,  # round(word["end"]   + offset, 2)
}
```

## Comportamento em edge cases

| Situação | Comportamento |
|----------|---------------|
| `words` é lista vazia | Retorna `[]`; log INFO com `0 words remapped` |
| `offset == 0.0` | Retorna lista nova com `start`/`end` inalterados (round não muda valores inteiros ou de 2 casas) |
| Item de `words` com campo ausente | **Não deve ocorrer** — `transcribe_audio_chunk()` garante a estrutura. Se ocorrer, `KeyError` é propagado para o chamador (fail-fast) |

## Chamador

`transcription_node()` em `orchestrator.py`:

```python
# ANTES (código atual inline, sem nome):
for word_info in result.get("word_timestamps", []):
    aggregated_word_timestamps.append({
        "word": word_info.get("word", ""),
        "start": round(float(word_info.get("start", 0.0)) + offset, 2),
        "end": round(float(word_info.get("end", 0.0)) + offset, 2),
    })

# DEPOIS (com apply_chunk_offset):
remapped = apply_chunk_offset(
    result.get("word_timestamps", []),
    offset=offset,
    chunk_index=index,
)
aggregated_word_timestamps.extend(remapped)
```

## Log emitido (FR-009)

```
INFO clipper.core.ingestion - Chunk 1 offset applied: +720.00s → 143 words remapped
```

Formato: `"Chunk %d offset applied: +%.2fs → %d words remapped"`

## O que NÃO é responsabilidade desta função

- Validar se `offset` é coerente com a duração do vídeo original
- Reordenar palavras (preserva a ordem da entrada)
- Modificar o `transcript_string` (texto de transcrição para o LLM — isso fica no `transcription_node`)
- Tratar `chunk` sem o campo `"offset"` (isso é responsabilidade do `transcription_node` antes de chamar esta função — FR-010)
