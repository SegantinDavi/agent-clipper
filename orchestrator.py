import os
import re
import gc
import hashlib
from typing import TypedDict

import openai
import instructor
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from schemas import CorteVideo
from ingestion import download_video, transcribe_audio_chunk
from node_0 import node_0_preventive_slicing
from editor import cut_and_format_video

# =====================================================================
# Configurações de Ambiente e Hardware
# =====================================================================
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/app/output" if os.path.exists("/app") else "output")
DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", os.path.join(OUTPUT_DIR, "downloads"))
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
DB_PATH = os.path.join(OUTPUT_DIR, "estado.db")


# =====================================================================
# 1. Definição do Estado Global (TypedDict)
# State Isolation: Trafega apenas caminhos de arquivos e dados limpos
# =====================================================================
class VideoState(TypedDict):
    video_url: str
    video_path: str
    audio_chunks: list
    transcript_grouped: str
    word_timestamps: list
    raciocinio_bruto: str
    cortes_finais: list


# =====================================================================
# 2. Encapsulamento dos Nós de Infraestrutura
# =====================================================================
def download_node(state: VideoState) -> dict:
    """Nó 1: Download do vídeo fonte via yt-dlp."""
    video_url = state.get("video_url")
    if not video_url:
        raise ValueError("A chave 'video_url' não foi fornecida no estado.")

    print(f"\n[DOWNLOAD_NODE] Iniciando download do vídeo: {video_url}")
    result = download_video(url=video_url, output_dir=DOWNLOADS_DIR)

    if result.get("status") == "error":
        raise RuntimeError(f"Erro no download do vídeo: {result.get('message')}")

    video_path = result.get("video_path")
    print(f"[DOWNLOAD_NODE] Download concluído com sucesso: {video_path}")
    return {"video_path": video_path}


def fatiamento_node(state: VideoState) -> dict:
    """Nó 2: Fatiamento preventivo do áudio em silêncios para vídeos longos."""
    video_path = state.get("video_path")
    if not video_path or not os.path.exists(video_path):
        raise FileNotFoundError(f"Arquivo de vídeo não encontrado para fatiamento: {video_path}")

    print(f"\n[FATIAMENTO_NODE] Fatiando áudio por silêncios com FFmpeg: {video_path}")
    chunks = node_0_preventive_slicing(video_path=video_path, output_dir=OUTPUT_DIR, max_chunk_sec=600)
    print(f"[FATIAMENTO_NODE] Chunks de áudio gerados com sucesso: {len(chunks)}")
    return {"audio_chunks": chunks}


def transcription_node(state: VideoState) -> dict:
    """Nó 3: Transcrição local na CPU com faster-whisper iterando sobre os chunks."""
    audio_chunks = state.get("audio_chunks", [])
    if not audio_chunks:
        raise ValueError("Nenhum chunk de áudio encontrado no estado para transcrição.")

    print(f"\n[TRANSCRICAO_NODE] Transcrevendo {len(audio_chunks)} chunks via faster-whisper (CPU int8)...")

    aggregated_transcript_parts: list[str] = []
    aggregated_word_timestamps: list[dict] = []

    for index, chunk in enumerate(audio_chunks):
        if isinstance(chunk, dict):
            chunk_path = chunk.get("chunk_path", "")
            offset = float(chunk.get("offset", 0.0))
        else:
            chunk_path = str(chunk)
            offset = 0.0

        print(f"[TRANSCRICAO_NODE] Chunk {index + 1}/{len(audio_chunks)}: {chunk_path} (offset: {offset:.2f}s)")
        result = transcribe_audio_chunk(chunk_path)

        if result.get("status") == "error":
            raise RuntimeError(f"Erro na transcrição do chunk {chunk_path}: {result.get('message')}")

        chunk_transcript = result.get("transcript", "")
        # Ajusta os timestamps da frase/segmento com o offset do chunk
        if offset > 0:
            def adjust_timestamp(match: re.Match) -> str:
                start = float(match.group(1)) + offset
                end = float(match.group(2)) + offset
                return f"[{start:.2f} - {end:.2f}]"

            chunk_transcript = re.sub(r"\[([0-9.]+) - ([0-9.]+)\]", adjust_timestamp, chunk_transcript)

        if chunk_transcript.strip():
            aggregated_transcript_parts.append(chunk_transcript.strip())

        # Ajusta os timestamps individuais das palavras para o nó de edição
        for word_info in result.get("word_timestamps", []):
            aggregated_word_timestamps.append({
                "word": word_info.get("word", ""),
                "start": round(float(word_info.get("start", 0.0)) + offset, 2),
                "end": round(float(word_info.get("end", 0.0)) + offset, 2)
            })

        # Prevenção rigorosa de memory leak
        gc.collect()

    full_transcript = " ".join(aggregated_transcript_parts)
    print(f"[TRANSCRICAO_NODE] Concluído. Palavras registradas: {len(aggregated_word_timestamps)}")

    return {
        "transcript_grouped": full_transcript,
        "word_timestamps": aggregated_word_timestamps
    }


# =====================================================================
# 3. Cognitive Routing: Dois Nós Sequenciais de LLM (Pensador e Extrator)
# =====================================================================
def thinker_node(state: VideoState) -> dict:
    """
    Nó 4 (Pensador): Analisa a transcrição e 'pensa alto' em formato livre (Chain of Thought),
    identificando ganchos, quebras de padrão e momentos de retenção viral.
    Sem Pydantic/Instructor para máxima liberdade de raciocínio.
    """
    transcript = state.get("transcript_grouped", "")
    if not transcript:
        raise ValueError("Transcrição vazia ou ausente no estado para o nó pensador.")

    print("\n[THINKER_NODE] Analisando momentos de retenção e gerando raciocínio estratégico (Qwen2.5:14b)...")

    raw_client = openai.OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama"
    )

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
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )

    raciocinio = response.choices[0].message.content or ""
    print(f"[THINKER_NODE] Raciocínio gerado ({len(raciocinio)} caracteres).")
    return {"raciocinio_bruto": raciocinio}


def extractor_node(state: VideoState) -> dict:
    """
    Nó 5 (Extrator): Lê o raciocínio livre do Pensador e a transcrição,
    forçando a saída estrita via Instructor (JSON Mode) com o schema CorteVideo.
    """
    transcript = state.get("transcript_grouped", "")
    raciocinio = state.get("raciocinio_bruto", "")

    if not raciocinio:
        raise ValueError("Raciocínio bruto ausente no estado para o nó extrator.")

    print("\n[EXTRACTOR_NODE] Formatando decisões finais em schema Pydantic via Instructor...")

    raw_client = openai.OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama"
    )
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
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1
    )

    print(f"[EXTRACTOR_NODE] Extração concluída com sucesso: {len(cortes)} cortes validados.")
    for idx, corte in enumerate(cortes, start=1):
        print(f"  [{idx}] '{corte.title}' ({corte.start_time:.2f}s - {corte.end_time:.2f}s)")

    return {"cortes_finais": cortes}


def editor_node(state: VideoState) -> dict:
    """Nó 6: Edição e renderização vertical com MoviePy e ImageMagick."""
    video_path = state.get("video_path", "")
    cortes = state.get("cortes_finais", [])
    word_timestamps = state.get("word_timestamps", [])

    if not video_path or not os.path.exists(video_path):
        raise FileNotFoundError(f"Arquivo de vídeo não encontrado para edição: {video_path}")

    if not cortes:
        print("[EDITOR_NODE] Nenhum corte estruturado para renderizar.")
        return {}

    # Garante instâncias de CorteVideo caso o estado venha deserializado do SQLite
    cortes_validados = [
        corte if isinstance(corte, CorteVideo) else CorteVideo(**corte)
        for corte in cortes
    ]

    print(f"\n[EDITOR_NODE] Renderizando {len(cortes_validados)} vídeos verticais (9:16)...")
    arquivos_gerados = cut_and_format_video(
        video_path=video_path,
        cortes_validados=cortes_validados,
        word_timestamps=word_timestamps,
        output_dir=OUTPUT_DIR
    )

    print(f"[EDITOR_NODE] Renderização concluída! {len(arquivos_gerados)} arquivos criados:")
    for arq in arquivos_gerados:
        print(f"  - {arq}")

    return {}


# Aliases para máxima flexibilidade e compatibilidade
preventive_slicing_node = fatiamento_node
transcricao_node = transcription_node


# =====================================================================
# 4. Construção e Compilação do Grafo (StateGraph)
# =====================================================================
def create_graph():
    """Constrói o Directed Acyclic Graph (DAG) sequencial do pipeline."""
    workflow = StateGraph(VideoState)

    # Registro de todos os nós
    workflow.add_node("download", download_node)
    workflow.add_node("fatiamento", fatiamento_node)
    workflow.add_node("transcricao", transcription_node)
    workflow.add_node("pensador", thinker_node)
    workflow.add_node("extrator", extractor_node)
    workflow.add_node("editor", editor_node)

    # Conexão sequencial determinística (Download -> Fatiamento -> Transcrição -> Pensador -> Extrator -> Editor)
    workflow.add_edge(START, "download")
    workflow.add_edge("download", "fatiamento")
    workflow.add_edge("fatiamento", "transcricao")
    workflow.add_edge("transcricao", "pensador")
    workflow.add_edge("pensador", "extrator")
    workflow.add_edge("extrator", "editor")
    workflow.add_edge("editor", END)

    return workflow


# =====================================================================
# Execução Principal com Checkpointer Persistente
# =====================================================================
if __name__ == "__main__":
    # Lê a URL da variável de ambiente com fallback para testes locais
    video_url = os.getenv("YOUTUBE_URL", "https://www.youtube.com/watch?v=jNQXAC9IVRw")
    print("==================================================")
    print("🚀 AGENT-CLIPPER: Pipeline Autônomo com LangGraph")
    print(f"URL Alvo: {video_url}")
    print(f"Output Dir: {OUTPUT_DIR}")
    print(f"Modelo LLM: {MODEL_NAME} ({OLLAMA_BASE_URL})")
    print("==================================================")

    # Estado inicial limpo
    initial_state: VideoState = {
        "video_url": video_url,
        "video_path": "",
        "audio_chunks": [],
        "transcript_grouped": "",
        "word_timestamps": [],
        "raciocinio_bruto": "",
        "cortes_finais": [],
    }

    # Thread ID determinístico baseado no hash da URL para permitir retomada pós-crash
    thread_id = hashlib.md5(video_url.encode("utf-8")).hexdigest()[:12]
    config = {"configurable": {"thread_id": f"clipper_{thread_id}"}}

    workflow = create_graph()

    # Configuração do Checkpointer SqliteSaver para persistência resiliente
    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        checkpointer.setup()
        app = workflow.compile(checkpointer=checkpointer)

        print(f"[ORCHESTRATOR] Grafo compilado. Iniciando execução (Thread: clipper_{thread_id})...")
        final_state = app.invoke(initial_state, config=config)

    print("\n🎉 Pipeline finalizado com sucesso!")
