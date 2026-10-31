import os
import re
import gc
import hashlib
import inspect
import logging
import uuid
from typing import TypedDict

if __name__ == "__main__":
    from clipper.runtime.runtime_options import configure_runtime

    startup_args = configure_runtime()
    from clipper.runtime.config import validate_llm_config

    validate_llm_config()
    from clipper.video.pause_editing import PauseSettings

    PauseSettings()
    from clipper.runtime.cuda_runtime import prepare_cuda_environment, validate_cuda_runtime

    prepare_cuda_environment()
    validate_cuda_runtime()

import openai
import instructor

_OPENAI_SYNC_CLIENT_CLASS = openai.OpenAI
_OPENAI_ASYNC_CLIENT_CLASS = openai.AsyncOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt

from clipper.core.schemas import CorteVideo, CortesResponse
from clipper.core.prompts import (
    EXTRACTOR_FEW_SHOT_EXAMPLES,
    EXTRACTOR_SYSTEM_PROMPT_TEMPLATE,
    THINKER_SYSTEM_PROMPT,
)
from clipper.core.ingestion import (
    apply_chunk_offset,
    download_video,
    extract_video_id,
    transcribe_audio_chunk,
)
from clipper.core.node_0 import node_0_preventive_slicing
from clipper.core.style_loader import load_visual_identity
from clipper.video.editor import cut_and_format_video
from clipper.review.review import (
    load_approval_decision,
    load_review_plans,
    prepare_review,
    validate_approval,
    wait_for_approval,
)
from clipper.video.pause_editing import PauseSettings

from clipper.runtime.config import (
    DB_PATH,
    DOWNLOADS_DIR,
    LOG_FILE,
    MODEL_NAME,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_PROVIDER,
    LLM_MAX_COMPLETION_TOKENS,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    validate_llm_config,
    OUTPUT_DIR,
    YOUTUBE_URL,
    SILENCE_CUT_ENABLED,
    SILENCE_MIN_PAUSE,
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
    visual_identity: dict


def create_llm_client() -> openai.OpenAI:
    """Instantiates a strict synchronous openai.OpenAI client configured for the current profile."""
    validate_llm_config()
    client = openai.OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        timeout=180.0,
        max_retries=2,
    )
    if not isinstance(client, _OPENAI_SYNC_CLIENT_CLASS) or isinstance(client, _OPENAI_ASYNC_CLIENT_CLASS):
        raise TypeError(
            f"create_llm_client must return an instance of openai.OpenAI and not AsyncOpenAI, got {type(client).__name__}"
        )
    return client


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


def style_node(state: VideoState) -> dict:
    """Nó síncrono que carrega estilo.json e armazena em visual_identity no VideoState."""
    style_path = state.get("style_path") if isinstance(state, dict) else None
    identity = load_visual_identity(style_path)
    return {"visual_identity": identity}


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
        if not isinstance(chunk, dict):
            raise ValueError(
                f"Chunk at index {index} must be a dict, got {type(chunk).__name__}"
            )
        if "chunk_path" not in chunk or not chunk["chunk_path"]:
            raise ValueError(f"Chunk at index {index} is missing 'chunk_path'")
        if "offset" not in chunk:
            raise ValueError(f"Chunk at index {index} is missing 'offset'")
        try:
            offset = float(chunk["offset"])
        except (ValueError, TypeError) as err:
            raise ValueError(
                f"Chunk at index {index} has invalid 'offset': {chunk.get('offset')}"
            ) from err
        if offset < 0.0:
            raise ValueError(f"Chunk at index {index} has negative offset: {offset}")
        chunk_path = chunk["chunk_path"]

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

        remapped_words = apply_chunk_offset(
            result.get("word_timestamps", []),
            offset=offset,
            chunk_index=index,
        )
        aggregated_word_timestamps.extend(remapped_words)

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
    try:
        user_prompt = (
            f"Transcrição do vídeo com timestamps:\n\n"
            f"{transcript}\n\n"
            f"Identifique todos os momentos adequados com alto potencial editorial, sem quantidade predefinida. "
            f"Indique os intervalos de tempo exatos [INÍCIO - FIM] na transcrição e descreva a estratégia de retenção de cada corte."
        )

        response = raw_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": THINKER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=LLM_MAX_COMPLETION_TOKENS,
        )

        raciocinio = response.choices[0].message.content or ""
        if not raciocinio.strip():
            raise RuntimeError("The thinker returned no editorial recommendations.")
    finally:
        raw_client.close()

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
    try:
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
    """Nó 6 (Preview): Prepara previews dos cortes estruturados para revisão humana."""
    cuts = [CorteVideo.model_validate(cut) for cut in state.get("cortes_finais", [])]
    if not cuts:
        return {"review_directory": ""}
    directory = prepare_review(state["video_path"], cuts, OUTPUT_DIR, state.get("review_session", ""),
                               word_timestamps=state.get("word_timestamps", []))
    return {"review_directory": directory}


def approval_node(state: VideoState) -> dict:
    """Nó 7 (Aprovação): Realiza interrupção nativa HITL para aprovação de cortes pelo usuário."""
    cuts = state.get("cortes_finais", [])
    if not cuts:
        return {"approved_cut_ids": [], "approval_complete": True}
    review_directory = state.get("review_directory", "")
    decision = interrupt({"review_directory": review_directory, "cut_count": len(cuts)})
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
    all_cuts = [CorteVideo.model_validate(cut) for cut in cortes]
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
    plans = load_review_plans(state["review_directory"], all_cuts)
    visual_identity = state.get("visual_identity", {})
    arquivos_gerados = cut_and_format_video(
        video_path=video_path,
        cortes_validados=cortes_validados,
        word_timestamps=word_timestamps,
        output_dir=OUTPUT_DIR,
        pause_plans=[plans[index - 1] for index in approved_ids],
        visual_identity=visual_identity,
    )

    logger.info("Rendering completed! %d files created:", len(arquivos_gerados))
    for arq in arquivos_gerados:
        logger.info("  - %s", arq)

    return {}


# Aliases para máxima flexibilidade e compatibilidade
preventive_slicing_node = fatiamento_node
transcricao_node = transcription_node
estilo_node = style_node


def create_graph() -> StateGraph:
    """Constrói o Directed Acyclic Graph (DAG) sequencial do pipeline."""
    workflow = StateGraph(VideoState)

    workflow.add_node("download", download_node)
    workflow.add_node("fatiamento", fatiamento_node)
    workflow.add_node("style", style_node)
    workflow.add_node("transcricao", transcription_node)
    workflow.add_node("pensador", thinker_node)
    workflow.add_node("extrator", extractor_node)
    workflow.add_node("preview", preview_node)
    workflow.add_node("approval", approval_node)
    workflow.add_node("editor", editor_node)

    workflow.add_edge(START, "download")
    workflow.add_edge("download", "fatiamento")
    workflow.add_edge("fatiamento", "style")
    workflow.add_edge("style", "transcricao")
    workflow.add_edge("transcricao", "pensador")
    workflow.add_edge("pensador", "extrator")
    workflow.add_edge("extrator", "preview")
    workflow.add_edge("preview", "approval")
    workflow.add_edge("approval", "editor")
    workflow.add_edge("editor", END)

    # Architectural contract verification: 100% of nodes must be synchronous callables
    for node_name, node_spec in workflow.nodes.items():
        runnable = getattr(node_spec, "runnable", node_spec)
        fn = getattr(runnable, "func", None)
        if fn is None or inspect.iscoroutinefunction(fn):
            raise TypeError(f"Node '{node_name}' must be a synchronous function, got coroutine function.")

    return workflow


def run_with_review(app, initial_state: VideoState, graph_config: dict, restart: bool = False,
                    review_port: int = 8765):
    if restart:
        thread_id = (graph_config or {}).get("configurable", {}).get("thread_id")
        checkpointer = getattr(app, "checkpointer", None)
        if thread_id and checkpointer:
            purge_thread_checkpoints(checkpointer, thread_id)
            logger.info("Purged existing checkpoints for thread '%s' due to --restart.", thread_id)
        if isinstance(initial_state, dict):
            initial_state["review_session"] = uuid.uuid4().hex

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
    while isinstance(result, dict) and result.get("__interrupt__"):
        snapshot = app.get_state(graph_config)
        review_dir = snapshot.values.get("review_directory")
        cut_count = None
        if isinstance(snapshot.values.get("cortes_finais"), list):
            cut_count = len(snapshot.values["cortes_finais"])
        if not review_dir or cut_count is None:
            for task in snapshot.tasks:
                if task.interrupts and isinstance(task.interrupts[0].value, dict):
                    if not review_dir:
                        review_dir = task.interrupts[0].value.get("review_directory")
                    if cut_count is None:
                        cut_count = task.interrupts[0].value.get("cut_count")
                    if review_dir and cut_count is not None:
                        break
        if not review_dir:
            raise RuntimeError("Review directory not found in interrupted graph state.")
        ids = load_approval_decision(review_dir, cut_count=cut_count)
        if ids is not None:
            logger.info("Found existing valid decision in %s: %s. Resuming without starting review server.", review_dir, ids)
        else:
            ids = wait_for_approval(review_dir, port=review_port)
        result = app.invoke(Command(resume={"approved_ids": ids}), config=graph_config)
    return result


def purge_thread_checkpoints(conn_or_checkpointer, thread_id: str) -> None:
    """Deletes all checkpoints and write records for a given thread_id from SQLite.

    Accepts either an active sqlite3.Connection or an object with a .conn attribute
    (such as LangGraph's SqliteSaver or CompiledStateGraph.checkpointer).
    """
    conn = getattr(conn_or_checkpointer, "conn", conn_or_checkpointer)
    with conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('checkpoints', 'writes')")
        existing_tables = {row[0] for row in cursor.fetchall()}
        if "checkpoints" in existing_tables:
            conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
        if "writes" in existing_tables:
            conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))


# WARNING: Altering this function or its identity formula invalidates all existing
# checkpoints stored in estado.db.
def checkpoint_thread_id(
    video_id: str,
    llm_provider: str | None = None,
    model_name: str | None = None,
    llm_base_url: str | None = None,
    silence_cut_enabled: bool | str | None = None,
    silence_min_pause: float | str | None = None,
) -> str:
    """Derives a deterministic 16-character hexadecimal thread ID for LangGraph checkpointers.

    WARNING: Altering this function or its identity formula invalidates all existing
    checkpoints stored in estado.db.
    """
    clean_video_id = str(video_id).strip() if video_id is not None else ""

    clean_provider = str(llm_provider).strip().lower() if llm_provider is not None else ""
    if not clean_provider:
        clean_provider = str(LLM_PROVIDER).strip().lower() if LLM_PROVIDER else "gemini"

    clean_model = str(model_name).strip() if model_name is not None else ""
    if not clean_model:
        clean_model = str(MODEL_NAME).strip() if MODEL_NAME else ""

    clean_endpoint = str(llm_base_url).strip().rstrip("/") if llm_base_url is not None else ""
    if not clean_endpoint:
        clean_endpoint = str(LLM_BASE_URL).strip().rstrip("/") if LLM_BASE_URL else ""

    if silence_cut_enabled is None:
        try:
            silence_cut_enabled = PauseSettings().enabled
        except Exception:
            silence_cut_enabled = SILENCE_CUT_ENABLED

    if isinstance(silence_cut_enabled, bool):
        is_silence_enabled = silence_cut_enabled
    elif isinstance(silence_cut_enabled, (int, float)):
        is_silence_enabled = bool(silence_cut_enabled)
    elif isinstance(silence_cut_enabled, str):
        is_silence_enabled = silence_cut_enabled.strip().lower() in {"1", "true", "yes"}
    else:
        is_silence_enabled = False
    clean_silence_enabled = "true" if is_silence_enabled else "false"

    if silence_min_pause is None:
        try:
            silence_min_pause = PauseSettings().min_pause
        except Exception:
            silence_min_pause = SILENCE_MIN_PAUSE

    try:
        parsed_pause = float(silence_min_pause)
        clean_silence_min_pause = str(parsed_pause) if parsed_pause > 0 else "0.6"
    except (ValueError, TypeError):
        clean_silence_min_pause = "0.6"

    payload = (
        f"{clean_video_id}|{clean_provider}|{clean_model}|{clean_endpoint}|"
        f"{clean_silence_enabled}|{clean_silence_min_pause}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def main(args=None):
    if args is None:
        from clipper.runtime.runtime_options import create_parser

        args = create_parser().parse_args()
    validate_llm_config()
    video_url = getattr(args, "url", None) or os.getenv("YOUTUBE_URL", YOUTUBE_URL)
    if not video_url:
        logger.error("Environment variable 'YOUTUBE_URL' is not set.")
        raise ValueError("Environment variable 'YOUTUBE_URL' is required.")
    logger.info("==================================================")
    logger.info("AGENT-CLIPPER: Autonomous LangGraph Pipeline")
    logger.info("Target URL: %s", video_url)
    logger.info("Output Dir: %s", OUTPUT_DIR)
    logger.info("LLM Provider: %s; Model: %s", LLM_PROVIDER, MODEL_NAME)
    logger.info("Whisper profile: %s/%s", WHISPER_DEVICE, WHISPER_COMPUTE_TYPE)
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
        "visual_identity": {},
    }

    video_id = extract_video_id(video_url) or video_url
    thread_id = checkpoint_thread_id(video_id)
    logger.info("Calculated checkpoint thread_id: %s (video_id: %s)", thread_id, video_id)
    config = {"configurable": {"thread_id": thread_id}}

    workflow = create_graph()

    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        checkpointer.setup()
        app = workflow.compile(checkpointer=checkpointer)

        logger.info(
            "Graph compiled. Starting execution (Thread: %s)...",
            thread_id,
        )
        try:
            run_with_review(app, initial_state, config, restart=args.restart, review_port=args.review_port)
        except KeyboardInterrupt:
            logger.info("Pipeline paused. Run the same URL again to resume the saved checkpoint.")
            return

    logger.info("Pipeline completed successfully!")


if __name__ == "__main__":
    main(startup_args)
