import os
import re
import gc
import hashlib
import logging
from typing import TypedDict

import openai
import instructor
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from schemas import CorteVideo
from ingestion import download_video, transcribe_audio_chunk
from node_0 import node_0_preventive_slicing
from editor import cut_and_format_video

from config import (
    DB_PATH,
    DOWNLOADS_DIR,
    LOG_FILE,
    MODEL_NAME,
    OLLAMA_BASE_URL,
    OUTPUT_DIR,
    YOUTUBE_URL,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
    force=True,
)
logger = logging.getLogger(__name__)


class VideoState(TypedDict):
    video_url: str
    video_path: str
    audio_chunks: list
    transcript_grouped: str
    word_timestamps: list
    raciocinio_bruto: str
    cortes_finais: list


def download_node(state: VideoState) -> dict:
    """Nó 1: Download do vídeo fonte via yt-dlp."""
    video_url = state.get("video_url")
    if not video_url:
        logger.error("Missing 'video_url' in state.")
        raise ValueError("A chave 'video_url' não foi fornecida no estado.")

    logger.info("Starting video download: %s", video_url)
    result = download_video(url=video_url, output_dir=DOWNLOADS_DIR)

    if result.get("status") == "error":
        logger.error("Video download failed: %s", result.get("message"))
        raise RuntimeError(f"Erro no download do vídeo: {result.get('message')}")

    video_path = result.get("video_path")
    logger.info("Video download completed successfully: %s", video_path)
    return {"video_path": video_path}


def fatiamento_node(state: VideoState) -> dict:
    """Nó 2: Fatiamento preventivo do áudio em silêncios para vídeos longos."""
    video_path = state.get("video_path")
    if not video_path or not os.path.exists(video_path):
        logger.error("Video file not found for slicing: %s", video_path)
        raise FileNotFoundError(
            f"Arquivo de vídeo não encontrado para fatiamento: {video_path}"
        )

    logger.info("Slicing audio with FFmpeg silence detection: %s", video_path)
    chunks = node_0_preventive_slicing(
        video_path=video_path, output_dir=OUTPUT_DIR, max_chunk_sec=600
    )
    logger.info("Audio chunks generated successfully: %d", len(chunks))
    return {"audio_chunks": chunks}


def transcription_node(state: VideoState) -> dict:
    """Nó 3: Transcrição local na CPU com faster-whisper iterando sobre os chunks."""
    audio_chunks = state.get("audio_chunks", [])
    if not audio_chunks:
        logger.error("No audio chunks found in state for transcription.")
        raise ValueError("Nenhum chunk de áudio encontrado no estado para transcrição.")

    logger.info(
        "Transcribing %d chunks via faster-whisper (CPU int8)...",
        len(audio_chunks),
    )

    aggregated_transcript_parts: list[str] = []
    aggregated_word_timestamps: list[dict] = []

    for index, chunk in enumerate(audio_chunks):
        if isinstance(chunk, dict):
            chunk_path = chunk.get("chunk_path", "")
            offset = float(chunk.get("offset", 0.0))
        else:
            chunk_path = str(chunk)
            offset = 0.0

        logger.info(
            "Transcribing chunk %d/%d: %s (offset: %.2fs)",
            index + 1,
            len(audio_chunks),
            chunk_path,
            offset,
        )
        result = transcribe_audio_chunk(chunk_path)

        if result.get("status") == "error":
            logger.error(
                "Error transcribing chunk %s: %s", chunk_path, result.get("message")
            )
            raise RuntimeError(
                f"Erro na transcrição do chunk {chunk_path}: {result.get('message')}"
            )
        chunk_transcript = result.get("transcript", "")

        if offset > 0:

            def adjust_timestamp(match: re.Match) -> str:
                start = float(match.group(1)) + offset
                end = float(match.group(2)) + offset
                return f"[{start:.2f} - {end:.2f}]"

            chunk_transcript = re.sub(
                r"\[([0-9.]+) - ([0-9.]+)\]", adjust_timestamp, chunk_transcript
            )

        if chunk_transcript.strip():
            aggregated_transcript_parts.append(chunk_transcript.strip())

        for word_info in result.get("word_timestamps", []):
            aggregated_word_timestamps.append(
                {
                    "word": word_info.get("word", ""),
                    "start": round(float(word_info.get("start", 0.0)) + offset, 2),
                    "end": round(float(word_info.get("end", 0.0)) + offset, 2),
                }
            )

        gc.collect()

    full_transcript = " ".join(aggregated_transcript_parts)
    logger.info(
        "Transcription completed. Recorded words: %d",
        len(aggregated_word_timestamps),
    )

    return {
        "transcript_grouped": full_transcript,
        "word_timestamps": aggregated_word_timestamps,
    }


def thinker_node(state: VideoState) -> dict:
    """
    Nó 4 (Pensador): Analisa a transcrição e 'pensa alto' em formato livre (Chain of Thought),
    identificando ganchos, quebras de padrão e momentos de retenção viral.
    Sem Pydantic/Instructor para máxima liberdade de raciocínio.
    """
    transcript = state.get("transcript_grouped", "")
    if not transcript:
        logger.error("Empty or missing transcript in state for thinker node.")
        raise ValueError("Transcrição vazia ou ausente no estado para o nó pensador.")

    logger.info(
        "Analyzing retention moments and generating strategic reasoning (Qwen2.5:14b)..."
    )

    raw_client = openai.OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

    system_prompt = (
        "Você é um Diretor Criativo e Estrategista Viral de vídeos curtos (Shorts/TikTok/Reels).\n"
        "Sua função é analisar a transcrição agrupada com timestamps e 'pensar alto' detalhadamente "
        "sobre os momentos com maior potencial de retenção da audiência.\n"
        "Identifique momentos que possuem um gancho forte (hook) nos primeiros 3 segundos, "
        "uma narrativa coerente e um clímax ou fechamento interessante.\n"
        "Escreva um parágrafo denso de raciocínio crítico justificando por que esses segmentos selecionados "
        "irão prender a atenção do espectador e quais são os intervalos de tempo correspondentes."
    )

    user_prompt = (
        f"Transcrição do vídeo com timestamps:\n\n"
        f"{transcript}\n\n"
        f"Pense criticamente e descreva sua análise dos melhores momentos virais."
    )

    response = raw_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )

    raciocinio = response.choices[0].message.content or ""
    logger.info("Strategic reasoning generated (%d characters).", len(raciocinio))
    return {"raciocinio_bruto": raciocinio}


def extractor_node(state: VideoState) -> dict:
    """
    Nó 5 (Extrator): Lê o raciocínio livre do Pensador e a transcrição,
    forçando a saída estrita via Instructor (JSON Mode) com o schema CorteVideo.
    """
    transcript = state.get("transcript_grouped", "")
    raciocinio = state.get("raciocinio_bruto", "")

    if not raciocinio:
        logger.error("Raw reasoning missing in state for extractor node.")
        raise ValueError("Raciocínio bruto ausente no estado para o nó extrator.")

    logger.info("Formatting final decisions into Pydantic schema via Instructor...")

    raw_client = openai.OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")
    instructor_client = instructor.from_openai(raw_client, mode=instructor.Mode.JSON)

    system_prompt = (
        "Você é um Extrator de Dados Especialista para YouTube Shorts.\n"
        "Com base estrita na transcrição e no raciocínio estratégico fornecido, extraia a lista com os melhores cortes.\n"
        "Regras Inegociáveis:\n"
        "1. Os tempos (start_time e end_time) em segundos DEVEM coincidir com timestamps presentes na transcrição.\n"
        "2. A duração de cada corte deve ser ideal para Shorts (entre 15s e 60s).\n"
        "3. Defina um título chamativo e viral para cada corte no campo 'title'.\n"
        "4. Retorne exclusivamente a estrutura solicitada."
    )

    user_prompt = (
        f"Transcrição do vídeo:\n{transcript}\n\n"
        f"Raciocínio Estratégico:\n{raciocinio}\n\n"
        f"Extraia a lista final dos cortes ideais conforme as instruções."
    )

    cortes: list[CorteVideo] = instructor_client.chat.completions.create(
        model=MODEL_NAME,
        response_model=list[CorteVideo],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )

    logger.info("Extraction completed successfully: %d cuts validated.", len(cortes))
    for idx, corte in enumerate(cortes, start=1):
        logger.info(
            "  [%d] '%s' (%.2fs - %.2fs)",
            idx,
            corte.title,
            corte.start_time,
            corte.end_time,
        )

    return {"cortes_finais": cortes}


def editor_node(state: VideoState) -> dict:
    """Nó 6: Edição e renderização vertical com MoviePy e ImageMagick."""
    video_path = state.get("video_path", "")
    cortes = state.get("cortes_finais", [])
    word_timestamps = state.get("word_timestamps", [])

    if not video_path or not os.path.exists(video_path):
        logger.error("Video file not found for editing: %s", video_path)
        raise FileNotFoundError(
            f"Arquivo de vídeo não encontrado para edição: {video_path}"
        )

    if not cortes:
        logger.warning("No structured cuts found to render.")
        return {}

    cortes_validados = [
        corte if isinstance(corte, CorteVideo) else CorteVideo(**corte)
        for corte in cortes
    ]

    logger.info("Rendering %d vertical videos (9:16)...", len(cortes_validados))
    arquivos_gerados = cut_and_format_video(
        video_path=video_path,
        cortes_validados=cortes_validados,
        word_timestamps=word_timestamps,
        output_dir=OUTPUT_DIR,
    )

    logger.info("Rendering completed! %d files created:", len(arquivos_gerados))
    for arq in arquivos_gerados:
        logger.info("  - %s", arq)

    return {}


# Aliases para máxima flexibilidade e compatibilidade
preventive_slicing_node = fatiamento_node
transcricao_node = transcription_node


def create_graph():
    """Constrói o Directed Acyclic Graph (DAG) sequencial do pipeline."""
    workflow = StateGraph(VideoState)

    workflow.add_node("download", download_node)
    workflow.add_node("fatiamento", fatiamento_node)
    workflow.add_node("transcricao", transcription_node)
    workflow.add_node("pensador", thinker_node)
    workflow.add_node("extrator", extractor_node)
    workflow.add_node("editor", editor_node)

    workflow.add_edge(START, "download")
    workflow.add_edge("download", "fatiamento")
    workflow.add_edge("fatiamento", "transcricao")
    workflow.add_edge("transcricao", "pensador")
    workflow.add_edge("pensador", "extrator")
    workflow.add_edge("extrator", "editor")
    workflow.add_edge("editor", END)

    return workflow


if __name__ == "__main__":
    video_url = os.getenv("YOUTUBE_URL")
    if not video_url:
        logger.error("Environment variable 'YOUTUBE_URL' is not set.")
        raise ValueError("Environment variable 'YOUTUBE_URL' is required.")
    logger.info("==================================================")
    logger.info("AGENT-CLIPPER: Autonomous LangGraph Pipeline")
    logger.info("Target URL: %s", video_url)
    logger.info("Output Dir: %s", OUTPUT_DIR)
    logger.info("LLM Model: %s (%s)", MODEL_NAME, OLLAMA_BASE_URL)
    logger.info("==================================================")

    initial_state: VideoState = {
        "video_url": video_url,
        "video_path": "",
        "audio_chunks": [],
        "transcript_grouped": "",
        "word_timestamps": [],
        "raciocinio_bruto": "",
        "cortes_finais": [],
    }

    thread_id = hashlib.md5(video_url.encode("utf-8")).hexdigest()[:12]
    config = {"configurable": {"thread_id": f"clipper_{thread_id}"}}

    workflow = create_graph()

    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        checkpointer.setup()
        app = workflow.compile(checkpointer=checkpointer)

        logger.info(
            "Graph compiled. Starting execution (Thread: clipper_%s)...",
            thread_id,
        )
        final_state = app.invoke(initial_state, config=config)

    logger.info("Pipeline completed successfully!")
