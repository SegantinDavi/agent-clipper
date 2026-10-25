import os
import re
import gc
import hashlib
import logging
import argparse
import uuid
from typing import TypedDict

if __name__ == "__main__":
    from cuda_runtime import prepare_cuda_environment, validate_cuda_runtime

    prepare_cuda_environment()
    validate_cuda_runtime()

import openai
import instructor
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt

from schemas import CorteVideo, CortesResponse
from prompts import (
    EXTRACTOR_FEW_SHOT_EXAMPLES,
    EXTRACTOR_SYSTEM_PROMPT_TEMPLATE,
    THINKER_SYSTEM_PROMPT,
)
from ingestion import download_video, transcribe_audio_chunk
from node_0 import node_0_preventive_slicing
from editor import cut_and_format_video
from review import prepare_review, validate_approval, wait_for_approval

from config import (
    DB_PATH,
    DOWNLOADS_DIR,
    LOG_FILE,
    MODEL_NAME,
    GEMINI_API_KEY,
    GEMINI_BASE_URL,
    LLM_MAX_COMPLETION_TOKENS,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    validate_llm_config,
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
    review_directory: str
    review_session: str
    approved_cut_ids: list[int]
    approval_complete: bool


def create_llm_client() -> openai.OpenAI:
    validate_llm_config()
    return openai.OpenAI(
        api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL,
        timeout=180.0, max_retries=2,
    )


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
    """Nó 3: Transcrição local com faster-whisper iterando sobre os chunks."""
    audio_chunks = state.get("audio_chunks", [])
    if not audio_chunks:
        logger.error("No audio chunks found in state for transcription.")
        raise ValueError("Nenhum chunk de áudio encontrado no estado para transcrição.")

    logger.info(
        "Transcribing %d chunks via faster-whisper (%s %s)...",
        len(audio_chunks),
        WHISPER_DEVICE,
        WHISPER_COMPUTE_TYPE,
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
    Nó 4 (Pensador): Analisa a transcrição e produz recomendações editoriais concisas,
    identificando ganchos, quebras de padrão e momentos de retenção viral.
    Sem Pydantic/Instructor para máxima liberdade de raciocínio.
    """
    transcript = state.get("transcript_grouped", "")
    if not transcript:
        logger.error("Empty or missing transcript in state for thinker node.")
        raise ValueError("Transcrição vazia ou ausente no estado para o nó pensador.")

    logger.info(
        "Analyzing retention moments with %s...", MODEL_NAME
    )

    raw_client = create_llm_client()

    user_prompt = (
        f"Transcrição do vídeo com timestamps:\n\n"
        f"{transcript}\n\n"
        f"Identifique todos os momentos adequados com alto potencial editorial, sem quantidade predefinida. "
        f"Indique os intervalos de tempo exatos [INÍCIO - FIM] na transcrição e descreva a estratégia de retenção de cada corte."
    )

    try:
        response = raw_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": THINKER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=LLM_MAX_COMPLETION_TOKENS,
        )
    finally:
        raw_client.close()

    raciocinio = response.choices[0].message.content or ""
    if not raciocinio.strip():
        raise RuntimeError("The thinker returned no editorial recommendations.")
    logger.info("Strategic reasoning generated (%d characters).", len(raciocinio))
    return {"raciocinio_bruto": raciocinio}


def extractor_node(state: VideoState) -> dict:
    """
    Nó 5 (Extrator): Lê o raciocínio livre do Pensador e a transcrição,
    forçando a saída estrita via Instructor (JSON Schema) com o schema CorteVideo.
    """
    transcript = state.get("transcript_grouped", "")
    raciocinio = state.get("raciocinio_bruto", "")

    if not raciocinio:
        logger.error("Raw reasoning missing in state for extractor node.")
        raise ValueError("Raciocínio bruto ausente no estado para o nó extrator.")

    logger.info("Formatting final decisions into Pydantic schema via Instructor...")

    raw_client = create_llm_client()
    instructor_client = instructor.from_openai(raw_client, mode=instructor.Mode.JSON_SCHEMA)

    user_prompt = (
        f"Transcrição do vídeo:\n{transcript}\n\n"
        f"Raciocínio Estratégico:\n{raciocinio}\n\n"
        f"Com base na transcrição e no raciocínio acima, extraia todos os cortes adequados, sem quantidade predefinida, respeitando as regras de duração fornecidas. "
        f"Preencha start_time e end_time com os segundos exatos dos trechos na transcrição e description com um breve resumo do tema."
    )

    messages = (
        [{"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT_TEMPLATE}]
        + list(EXTRACTOR_FEW_SHOT_EXAMPLES)
        + [{"role": "user", "content": user_prompt}]
    )

    try:
        extraction_response: CortesResponse = instructor_client.chat.completions.create(
            model=MODEL_NAME,
            response_model=CortesResponse,
            messages=messages,
            max_tokens=LLM_MAX_COMPLETION_TOKENS,
            max_retries=2,
            # Instructor JSON_SCHEMA does not enable API strictness by default.
            extra_body={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": CortesResponse.__name__,
                        "strict": True,
                        "schema": openai.pydantic_function_tool(CortesResponse)["function"]["parameters"],
                    },
                },
            },
        )
    finally:
        raw_client.close()

    cortes: list[CorteVideo] = extraction_response.cortes
    logger.info("Extraction completed successfully: %d cuts validated.", len(cortes))
    for idx, corte in enumerate(cortes, start=1):
        logger.info(
            "  [%d] '%s' (%.2fs - %.2fs)",
            idx,
            corte.title,
            corte.start_time,
            corte.end_time,
        )

    return {"cortes_finais": [cut.model_dump() for cut in cortes]}


def preview_node(state: VideoState) -> dict:
    cuts = [CorteVideo.model_validate(cut) for cut in state.get("cortes_finais", [])]
    if not cuts:
        return {"review_directory": ""}
    directory = prepare_review(state["video_path"], cuts, OUTPUT_DIR, state.get("review_session", ""))
    return {"review_directory": directory}


def approval_node(state: VideoState) -> dict:
    cuts = state.get("cortes_finais", [])
    if not cuts:
        return {"approved_cut_ids": [], "approval_complete": True}
    decision = interrupt({"review_directory": state["review_directory"], "cut_count": len(cuts)})
    ids = validate_approval(decision, len(cuts))
    logger.info("User approved cuts: %s", ids)
    return {"approved_cut_ids": ids, "approval_complete": True}


def editor_node(state: VideoState) -> dict:
    """Renderiza apenas cortes explicitamente aprovados pelo usuário."""
    if state.get("approval_complete") is not True:
        raise ValueError("Cut approval is required before editing.")
    video_path = state.get("video_path", "")
    cortes = state.get("cortes_finais", [])
    word_timestamps = state.get("word_timestamps", [])
    approved_ids = validate_approval(
        {"approved_ids": state.get("approved_cut_ids", [])}, len(cortes)
    )
    cortes = [cortes[index - 1] for index in approved_ids]

    if not cortes:
        logger.info("No approved cuts. Skipping final editing.")
        return {}

    if not video_path or not os.path.exists(video_path):
        logger.error("Video file not found for editing: %s", video_path)
        raise FileNotFoundError(
            f"Arquivo de vídeo não encontrado para edição: {video_path}"
        )

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
    workflow.add_node("preview", preview_node)
    workflow.add_node("approval", approval_node)
    workflow.add_node("editor", editor_node)

    workflow.add_edge(START, "download")
    workflow.add_edge("download", "fatiamento")
    workflow.add_edge("fatiamento", "transcricao")
    workflow.add_edge("transcricao", "pensador")
    workflow.add_edge("pensador", "extrator")
    workflow.add_edge("extrator", "preview")
    workflow.add_edge("preview", "approval")
    workflow.add_edge("approval", "editor")
    workflow.add_edge("editor", END)

    return workflow


def run_with_review(app, initial_state: VideoState, graph_config: dict, restart: bool = False,
                    review_port: int = 8765):
    snapshot = app.get_state(graph_config)
    if restart or not snapshot.values:
        result = app.invoke(initial_state, config=graph_config)
    elif any(task.interrupts for task in snapshot.tasks):
        result = {"__interrupt__": True}
    elif snapshot.next:
        result = app.invoke(None, config=graph_config)
    else:
        logger.info("This run is already complete. Use --restart to process it again.")
        return snapshot.values
    while result.get("__interrupt__"):
        snapshot = app.get_state(graph_config)
        ids = wait_for_approval(snapshot.values["review_directory"], port=review_port)
        result = app.invoke(Command(resume={"approved_ids": ids}), config=graph_config)
    return result


def main():
    parser = argparse.ArgumentParser(description="Agent Clipper with cut approval")
    parser.add_argument("--restart", action="store_true", help="Start this video's pipeline again")
    parser.add_argument("--review-port", type=int, default=8765, help="Local review page port")
    args = parser.parse_args()
    validate_llm_config()
    video_url = YOUTUBE_URL
    if not video_url:
        logger.error("Environment variable 'YOUTUBE_URL' is not set.")
        raise ValueError("Environment variable 'YOUTUBE_URL' is required.")
    logger.info("==================================================")
    logger.info("AGENT-CLIPPER: Autonomous LangGraph Pipeline")
    logger.info("Target URL: %s", video_url)
    logger.info("Output Dir: %s", OUTPUT_DIR)
    logger.info("LLM Model: %s (%s)", MODEL_NAME, GEMINI_BASE_URL)
    logger.info("==================================================")

    initial_state: VideoState = {
        "video_url": video_url,
        "video_path": "",
        "audio_chunks": [],
        "transcript_grouped": "",
        "word_timestamps": [],
        "raciocinio_bruto": "",
        "cortes_finais": [],
        "review_directory": "",
        "review_session": uuid.uuid4().hex,
        "approved_cut_ids": [],
        "approval_complete": False,
    }

    thread_id = hashlib.md5(video_url.encode("utf-8")).hexdigest()[:12]
    config = {"configurable": {"thread_id": f"clipper_review_v1_{thread_id}"}}

    workflow = create_graph()

    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        checkpointer.setup()
        app = workflow.compile(checkpointer=checkpointer)

        logger.info(
            "Graph compiled. Starting execution (Thread: clipper_%s)...",
            thread_id,
        )
        try:
            run_with_review(app, initial_state, config, restart=args.restart, review_port=args.review_port)
        except KeyboardInterrupt:
            logger.info("Pipeline paused. Run the same URL again to resume the saved checkpoint.")
            return

    logger.info("Pipeline completed successfully!")


if __name__ == "__main__":
    main()
